import evdev
from evdev import ecodes

from bt_hid_kvm.constants import TRIGGER_KEY
from bt_hid_kvm.utils.hid_report import (
    get_keyboard_report_from_keycodes,
    get_mouse_report,
)
from bt_hid_kvm.utils.input_capture import InputCapture


class FakeLink:
    is_connected = True
    has_queued_reports = False

    def __init__(self):
        self.reports: list[bytes] = []

    def send(self, report: bytes) -> None:
        self.reports.append(report)


class FakeUInput:
    def __init__(self):
        self.keys: list[tuple[int, int]] = []

    def write(self, event_type: int, code: int, value: int) -> None:
        self.keys.append((code, value))

    def syn(self) -> None:
        pass


def get_capture() -> tuple[InputCapture, list[bool], FakeUInput, FakeLink]:
    """A connected capture with no real devices; returns it with what it sends each way."""
    modes: list[bool] = []
    link = FakeLink()
    uinput = FakeUInput()
    capture = InputCapture(link, on_mode_change=modes.append, on_log=lambda message: None)
    capture._uinput = uinput
    return capture, modes, uinput, link


def tap(capture: InputCapture, code: int) -> None:
    for value in (1, 0):
        capture._handle_keyboard_event(evdev.InputEvent(0, 0, ecodes.EV_KEY, code, value))


def test_toggle_mode_switches_host_on_each_trigger_tap():
    capture, modes, uinput, link = get_capture()
    capture.is_toggle_mode = True
    tap(capture, TRIGGER_KEY)
    assert capture.is_remote
    tap(capture, TRIGGER_KEY)
    assert not capture.is_remote
    assert modes == [True, False]
    # The trigger itself reaches neither side; the host only gets the all-released reports.
    assert uinput.keys == []
    assert link.reports == [get_keyboard_report_from_keycodes([]), get_mouse_report(0, 0, 0)]


def test_toggle_mode_ignores_trigger_autorepeat():
    # Holding the key in toggle mode sends repeats (value 2); they must not flip the mode.
    capture, modes, _, _ = get_capture()
    capture.is_toggle_mode = True
    for value in (1, 2, 2, 2, 0):
        capture._handle_keyboard_event(evdev.InputEvent(0, 0, ecodes.EV_KEY, TRIGGER_KEY, value))
    assert (capture.is_remote, modes) == (True, [True])


def test_hold_mode_stays_the_default():
    capture, modes, _, _ = get_capture()
    capture._handle_keyboard_event(evdev.InputEvent(0, 0, ecodes.EV_KEY, TRIGGER_KEY, 1))
    assert capture.is_remote
    capture._handle_keyboard_event(evdev.InputEvent(0, 0, ecodes.EV_KEY, TRIGGER_KEY, 0))
    assert (capture.is_remote, modes) == (False, [True, False])
