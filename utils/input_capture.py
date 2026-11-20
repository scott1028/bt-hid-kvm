import select
import threading
import time
from collections.abc import Callable

import evdev
from evdev import InputDevice, UInput, ecodes

from bt_hid_kvm.constants import (
    IDLE_POLL_INTERVAL,
    MOUSE_FLUSH_INTERVAL,
    TRIGGER_KEY,
    UINPUT_KEYBOARD_NAME,
)
from bt_hid_kvm.constants.hid import MOUSE_BUTTON_BITS
from bt_hid_kvm.utils.bt_hid_link import HidLink
from bt_hid_kvm.utils.hid_report import (
    MouseAccumulator,
    get_keyboard_report_from_keycodes,
    get_mouse_report,
)


def find_input_devices() -> tuple[list[InputDevice], list[InputDevice]]:
    """Return physical (keyboards, mice); virtual devices have an empty phys."""
    keyboards, mice = [], []
    for path in evdev.list_devices():
        device = InputDevice(path)
        capabilities = device.capabilities()
        keys = capabilities.get(ecodes.EV_KEY, [])
        relatives = capabilities.get(ecodes.EV_REL, [])
        if device.phys and ecodes.KEY_A in keys and ecodes.KEY_Z in keys:
            keyboards.append(device)
        elif device.phys and ecodes.REL_X in relatives and ecodes.REL_Y in relatives and ecodes.BTN_LEFT in keys:
            mice.append(device)
        else:
            device.close()
    return keyboards, mice


class InputCapture:
    """Routes physical keyboard/mouse events to this machine or to the HID host.

    Keyboards stay grabbed and are re-injected locally through uinput, so the
    trigger key never reaches the compositor. Mice are grabbed only in remote mode.
    """

    def __init__(
        self,
        link: HidLink,
        on_mode_change: Callable[[bool], None],
        on_log: Callable[[str], None],
    ):
        self._link = link
        self._on_mode_change = on_mode_change
        self._on_log = on_log
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._uinput: UInput | None = None
        self.keyboards: list[InputDevice] = []
        self.mice: list[InputDevice] = []
        self.is_remote = False
        self._is_mouse_grabbed = False
        self._local_keys: set[int] = set()
        self._remote_keys: list[int] = []
        self._mouse = MouseAccumulator()
        self._last_mouse_flush = 0.0

    def start(self) -> None:
        self.keyboards, self.mice = find_input_devices()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        try:
            # Grabbing while a key is down would leave that key stuck locally.
            while any(keyboard.active_keys() for keyboard in self.keyboards):
                if self._stop_event.wait(0.05):
                    return
            self._uinput = UInput.from_device(*self.keyboards, name=UINPUT_KEYBOARD_NAME)
            for keyboard in self.keyboards:
                keyboard.grab()
            self._on_log(f"grabbed {len(self.keyboards)} keyboard(s), watching {len(self.mice)} mouse/mice")
            self._loop()
        except OSError as error:
            self._on_log(f"input capture stopped: {error}")
        finally:
            self._leave_remote()
            for device in self.keyboards + self.mice:
                try:
                    device.ungrab()
                except OSError:
                    pass
                device.close()
            if self._uinput:
                self._uinput.close()
            self._on_log("input released")

    def _loop(self) -> None:
        devices = {device.fd: device for device in self.keyboards + self.mice}
        keyboard_fds = {keyboard.fd for keyboard in self.keyboards}
        while not self._stop_event.is_set():
            timeout = MOUSE_FLUSH_INTERVAL if self._mouse.has_motion else IDLE_POLL_INTERVAL
            readable, _, _ = select.select(list(devices), [], [], timeout)
            for fd in readable:
                try:
                    events = list(devices[fd].read())
                except OSError:
                    self._on_log(f"device removed: {devices.pop(fd).name}")
                    continue
                for event in events:
                    if fd in keyboard_fds:
                        self._handle_keyboard_event(event)
                    else:
                        self._handle_mouse_event(event)
            if self.is_remote and not self._link.is_connected:
                self._on_log("link lost, back to local")
                self._leave_remote()
            if self.is_remote and not self._is_mouse_grabbed:
                self._grab_mice_when_released()
            is_flush_due = time.monotonic() - self._last_mouse_flush >= MOUSE_FLUSH_INTERVAL
            if self.is_remote and self._mouse.has_motion and is_flush_due:
                self._flush_mouse()

    def _handle_keyboard_event(self, event: evdev.InputEvent) -> None:
        if event.type != ecodes.EV_KEY:
            if not self.is_remote:
                self._uinput.write_event(event)
            return
        # A trigger pressed while disconnected stays a normal local key until released.
        is_trigger = event.code == TRIGGER_KEY and TRIGGER_KEY not in self._local_keys
        if is_trigger and (self._link.is_connected or self.is_remote):
            if event.value == 1:
                self._enter_remote()
            elif event.value == 0:
                self._leave_remote()
        elif self.is_remote:
            self._send_remote_key(event.code, event.value)
        else:
            self._write_local_key(event.code, event.value)

    def _write_local_key(self, code: int, value: int) -> None:
        if value == 1:
            self._local_keys.add(code)
        elif code not in self._local_keys:
            # Release or repeat of a key that was pressed in remote mode
            return
        elif value == 0:
            self._local_keys.discard(code)
        self._uinput.write(ecodes.EV_KEY, code, value)

    def _send_remote_key(self, code: int, value: int) -> None:
        if value == 1 and code not in self._remote_keys:
            self._remote_keys.append(code)
        elif value == 0 and code in self._remote_keys:
            self._remote_keys.remove(code)
        else:
            # Autorepeat: the host repeats on its own
            return
        self._link.send(get_keyboard_report_from_keycodes(self._remote_keys))

    def _handle_mouse_event(self, event: evdev.InputEvent) -> None:
        if not (self.is_remote and self._is_mouse_grabbed):
            return
        self._mouse.add_event(event.type, event.code, event.value)
        if event.type == ecodes.EV_KEY:
            self._flush_mouse()

    def _flush_mouse(self) -> None:
        self._link.send(self._mouse.pop_report())
        self._last_mouse_flush = time.monotonic()

    def _enter_remote(self) -> None:
        self.is_remote = True
        for code in self._local_keys:
            self._uinput.write(ecodes.EV_KEY, code, 0)
        self._local_keys.clear()
        self._uinput.syn()
        self._mouse = MouseAccumulator()
        self._grab_mice_when_released()
        self._on_mode_change(True)

    def _grab_mice_when_released(self) -> None:
        # Grabbing mid-drag would leave the local button stuck, so wait for release.
        if any(set(mouse.active_keys()) & MOUSE_BUTTON_BITS.keys() for mouse in self.mice):
            return
        for mouse in self.mice:
            try:
                mouse.grab()
            except OSError as error:
                self._on_log(f"cannot grab {mouse.name}: {error}")
        self._is_mouse_grabbed = True

    def _leave_remote(self) -> None:
        if not self.is_remote:
            return
        self.is_remote = False
        self._remote_keys.clear()
        self._link.send(get_keyboard_report_from_keycodes([]))
        self._link.send(get_mouse_report(0, 0, 0))
        self._mouse = MouseAccumulator()
        if self._is_mouse_grabbed:
            for mouse in self.mice:
                try:
                    mouse.ungrab()
                except OSError:
                    pass
            self._is_mouse_grabbed = False
        self._on_mode_change(False)
