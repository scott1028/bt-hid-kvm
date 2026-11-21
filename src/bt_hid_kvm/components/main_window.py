import queue
import threading
import time
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

import dbus

from bt_hid_kvm.constants import (
    HINT_COLOR,
    MODE_COLOR_LOCAL,
    MODE_COLOR_REMOTE,
    SCAN_DURATION,
    SCAN_REFRESH_MS,
    UI_POLL_INTERVAL_MS,
    UI_STATE_PATH,
)
from bt_hid_kvm.utils.bt_hid_link import (
    HidLink,
    get_adapter_path,
    get_is_paired,
    register_hid_profile,
)
from bt_hid_kvm.utils.bt_pairing import (
    get_known_hosts,
    get_mac_from_text,
    pair_device,
    register_pairing_agent,
    start_host_scan,
    stop_host_scan,
)
from bt_hid_kvm.utils.input_capture import InputCapture
from bt_hid_kvm.utils.ui_state import UiState, load_ui_state, save_ui_state


class MainWindow:
    """Tk window; worker threads talk to it only through a queue."""

    def __init__(self, root: tk.Tk, mac: str | None):
        self._root = root
        self._events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._link = HidLink(
            on_disconnect=lambda reason: self._events.put(("disconnected", reason)),
            on_accept=lambda host: self._events.put(("connected", host)),
        )
        self._bus = register_hid_profile(self._link.accept)
        self._adapter_path = get_adapter_path(self._bus)
        self._capture = InputCapture(
            self._link,
            on_mode_change=lambda is_remote: self._events.put(("mode", is_remote)),
            on_log=lambda message: self._events.put(("log", message)),
        )
        register_pairing_agent(
            self._bus,
            on_request_confirmation=lambda passkey, answer: self._events.put(("passkey", (passkey, answer))),
            on_cancel=lambda: self._events.put(("passkey_cancel", None)),
        )
        self._is_connecting = False
        self._is_pairing = False
        self._is_scanning = False
        self._scan_deadline = 0.0
        self._scan_job: str | None = None
        self._answer_passkey: Callable[[bool], None] | None = None
        self._host_names: dict[str, str] = {}
        self._remote_name = ""

        root.title("BT HID KVM")
        root.minsize(420, 0)
        frame = ttk.Frame(root, padding=12)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="目標").grid(row=0, column=0, sticky="w")
        # Pick a known or scanned host, or type a MAC.
        self._target = tk.StringVar(value=mac or "")
        self._target_box = ttk.Combobox(frame, textvariable=self._target, width=34)
        self._target_box.grid(row=0, column=1, sticky="we", padx=8)
        buttons = ttk.Frame(frame)
        buttons.grid(row=0, column=2)
        self._scan_button = ttk.Button(buttons, text="掃描", command=self._handle_scan_click)
        self._scan_button.pack(side="left", padx=(0, 4))
        self._pair_button = ttk.Button(buttons, text="配對", command=self._handle_pair_click)
        self._pair_button.pack(side="left", padx=(0, 4))
        self._connect_button = ttk.Button(buttons, text="連線", command=self._handle_connect_click)
        self._connect_button.pack(side="left")

        status_row = ttk.Frame(frame)
        status_row.grid(row=1, column=0, columnspan=3, sticky="we", pady=(8, 0))
        self._status = ttk.Label(status_row, text="狀態：未連線")
        self._status.pack(side="left")
        # Says that 重新配對 drops the bond, so both sides compare passkeys again.
        self._pair_hint = ttk.Label(status_row, foreground=HINT_COLOR, font="TkSmallCaptionFont")
        self._pair_hint.pack(side="left", padx=(16, 0))
        self._target.trace_add("write", lambda *_: self._update_pair_controls())

        # Shown only while BlueZ waits for the user to compare passkeys.
        self._passkey = ttk.Frame(frame)
        self._passkey.grid(row=2, column=0, columnspan=3, sticky="we", pady=(8, 0))
        self._passkey_label = ttk.Label(self._passkey, font=("TkDefaultFont", 14, "bold"))
        self._passkey_label.pack(side="left")
        ttk.Button(self._passkey, text="相同", command=lambda: self._handle_passkey_answer(True)).pack(side="right")
        ttk.Button(self._passkey, text="不同", command=lambda: self._handle_passkey_answer(False)).pack(
            side="right", padx=4
        )
        self._passkey.grid_remove()

        self._mode = tk.Label(
            frame, text="本機", bg=MODE_COLOR_LOCAL, fg="white", font=("TkDefaultFont", 20, "bold"), pady=12
        )
        self._mode.grid(row=3, column=0, columnspan=3, sticky="we", pady=8)
        # Boxed section, so the switch does not blend into the text around it.
        trigger = ttk.LabelFrame(frame, text="觸發鍵", padding=(10, 6))
        trigger.grid(row=4, column=0, columnspan=3, sticky="we", pady=(4, 4))
        # The theme's box is tiny; a bigger one makes the checked state easy to see.
        ttk.Style(root).configure("TCheckbutton", indicatordiameter=18, indicatormargin=(0, 0, 8, 0))
        self._is_toggle_mode = tk.BooleanVar(value=load_ui_state(UI_STATE_PATH).is_toggle_mode)
        # Fires on clicks only, not on the initial value.
        self._is_toggle_mode.trace_add("write", lambda *_: self._save_ui_state())
        ttk.Checkbutton(
            trigger,
            text="切換模式：按一下左 Win 切換，不用按住",
            variable=self._is_toggle_mode,
            command=self._handle_toggle_mode_change,
        ).pack(anchor="w")
        self._hint = ttk.Label(trigger)
        self._hint.pack(anchor="w", pady=(6, 0))
        self._handle_toggle_mode_change()

        self._devices = ttk.Label(frame, text="", justify="left")
        self._devices.grid(row=5, column=0, columnspan=3, sticky="w", pady=(8, 0))

        self._log = tk.Text(frame, height=8, width=60, state="disabled")
        self._log.grid(row=6, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(6, weight=1)

        self._capture.start()
        keyboards = ", ".join(device.name.strip() for device in self._capture.keyboards) or "（無）"
        mice = ", ".join(device.name.strip() for device in self._capture.mice) or "（無）"
        self._devices.configure(text=f"鍵盤：{keyboards}\n滑鼠：{mice}")
        self._refresh_hosts()

        root.protocol("WM_DELETE_WINDOW", self._handle_close)
        root.after(UI_POLL_INTERVAL_MS, self._poll_events)

    def _handle_connect_click(self) -> None:
        if self._link.is_connected:
            self._link.close("使用者中斷")
            return
        if self._is_connecting:
            return
        mac = get_mac_from_text(self._target.get())
        if mac is None:
            self._status.configure(text="狀態：目標裡找不到 MAC")
            return
        self._stop_scan()
        self._is_connecting = True
        self._connect_button.configure(state="disabled")
        self._pair_button.configure(state="disabled")
        self._scan_button.configure(state="disabled")
        self._status.configure(text="狀態：連線中…")
        threading.Thread(target=self._connect, args=(mac,), daemon=True).start()

    def _connect(self, mac: str) -> None:
        try:
            self._link.connect(mac)
            self._events.put(("connected", mac))
        except OSError as error:
            self._events.put(("connect_failed", error))

    def _handle_pair_click(self) -> None:
        if self._is_pairing:
            return
        mac = get_mac_from_text(self._target.get())
        if mac is None:
            self._status.configure(text="狀態：目標裡找不到 MAC")
            return
        # BlueZ pairs more reliably when no scan is running.
        self._stop_scan()
        self._is_pairing = True
        self._pair_button.configure(state="disabled")
        self._connect_button.configure(state="disabled")
        self._scan_button.configure(state="disabled")
        self._status.configure(text="狀態：配對中…")
        self._pair_hint.configure(text="")
        threading.Thread(target=self._pair, args=(mac,), daemon=True).start()

    def _pair(self, mac: str) -> None:
        try:
            pair_device(self._bus, self._adapter_path, mac)
            self._events.put(("paired", mac))
        except (OSError, dbus.DBusException) as error:
            self._events.put(("pair_failed", error))

    def _handle_passkey_answer(self, is_accepted: bool) -> None:
        if self._answer_passkey is not None:
            self._answer_passkey(is_accepted)
        self._answer_passkey = None
        self._passkey.grid_remove()

    def _handle_toggle_mode_change(self) -> None:
        is_toggle_mode = self._is_toggle_mode.get()
        self._capture.is_toggle_mode = is_toggle_mode
        if is_toggle_mode:
            self._hint.configure(text="連線後按一下左 Win（Keychron Mac 模式為 Command 位置）切到對方電腦，再按一下切回本機")
        else:
            self._hint.configure(text="連線後按住左 Win（Keychron Mac 模式為 Command 位置）控制對方電腦")

    def _save_ui_state(self) -> None:
        try:
            save_ui_state(UI_STATE_PATH, UiState(is_toggle_mode=self._is_toggle_mode.get()))
        except OSError as error:
            self._append_log(f"save UI state failed: {error}")

    def _handle_scan_click(self) -> None:
        try:
            start_host_scan(self._bus, self._adapter_path)
        except dbus.DBusException as error:
            self._append_log(f"scan failed: {error}")
            return
        self._is_scanning = True
        self._scan_deadline = time.monotonic() + SCAN_DURATION
        self._scan_button.configure(state="disabled")
        self._status.configure(text="狀態：掃描中…（對方電腦要開啟可被搜尋）")
        self._scan_job = self._root.after(SCAN_REFRESH_MS, self._refresh_scan)

    def _refresh_scan(self) -> None:
        if time.monotonic() < self._scan_deadline:
            self._refresh_hosts()
            self._scan_job = self._root.after(SCAN_REFRESH_MS, self._refresh_scan)
            return
        self._stop_scan()
        self._scan_button.configure(state="normal")
        self._status.configure(text=f"狀態：掃描結束，清單裡有 {len(self._target_box.cget('values'))} 台電腦")

    def _stop_scan(self) -> None:
        if not self._is_scanning:
            return
        self._is_scanning = False
        self._root.after_cancel(self._scan_job)
        try:
            stop_host_scan(self._bus, self._adapter_path)
        except dbus.DBusException as error:
            self._append_log(f"stop scan failed: {error}")
        self._refresh_hosts()

    def _refresh_hosts(self) -> None:
        try:
            hosts = get_known_hosts(self._bus, self._adapter_path)
        except dbus.DBusException as error:
            # Keep the event loop alive if bluetoothd restarts.
            self._append_log(f"list hosts failed: {error}")
            return
        labels = [f"{host.name} ({host.mac})" + (" 已配對" if host.is_paired else "") for host in hosts]
        self._target_box.configure(values=labels)
        self._host_names = {host.mac: host.name for host in hosts}
        # Hosts are sorted paired first; start on one that can connect right away.
        if not self._target.get() and hosts and hosts[0].is_paired:
            self._target.set(labels[0])
        self._update_pair_controls()

    def _update_pair_controls(self) -> None:
        # Ask BlueZ each time: a failed Pair() has already dropped the old bond.
        mac = get_mac_from_text(self._target.get())
        is_paired = mac is not None and get_is_paired(self._bus, self._adapter_path, mac)
        self._pair_button.configure(text="重新配對" if is_paired else "配對")
        self._pair_hint.configure(text="已配對，不用再按「重新配對」；按了要重新核對配對碼" if is_paired else "")

    def _poll_events(self) -> None:
        while not self._events.empty():
            kind, payload = self._events.get_nowait()
            if kind == "log":
                self._append_log(str(payload))
            elif kind == "mode":
                is_remote = bool(payload)
                self._mode.configure(
                    text=self._remote_name if is_remote else "本機",
                    bg=MODE_COLOR_REMOTE if is_remote else MODE_COLOR_LOCAL,
                )
            elif kind == "connected":
                self._is_connecting = False
                self._remote_name = self._host_names.get(str(payload), str(payload))
                # The host may connect on its own, without a 連線 click.
                self._stop_scan()
                self._pair_button.configure(state="disabled")
                self._scan_button.configure(state="disabled")
                self._connect_button.configure(state="normal", text="中斷")
                self._status.configure(text=f"狀態：已連線 {payload}")
                self._append_log(f"connected to {payload}")
            elif kind == "connect_failed":
                self._is_connecting = False
                self._connect_button.configure(state="normal", text="連線")
                self._pair_button.configure(state="normal")
                self._scan_button.configure(state="normal")
                self._status.configure(text="狀態：連線失敗")
                self._append_log(f"connect failed: {payload}")
            elif kind == "disconnected":
                self._connect_button.configure(text="連線")
                self._pair_button.configure(state="normal")
                self._scan_button.configure(state="normal")
                self._status.configure(text="狀態：未連線")
                self._append_log(f"disconnected: {payload}")
            elif kind == "passkey":
                passkey, self._answer_passkey = payload
                self._passkey_label.configure(text=f"配對碼 {passkey:06d}：對方電腦顯示的數字一樣嗎？")
                self._passkey.grid()
            elif kind == "passkey_cancel":
                self._answer_passkey = None
                self._passkey.grid_remove()
            elif kind == "paired":
                self._is_pairing = False
                self._pair_button.configure(state="normal")
                self._connect_button.configure(state="normal")
                self._scan_button.configure(state="normal")
                self._status.configure(text=f"狀態：已配對 {payload}，可以連線")
                self._append_log(f"paired with {payload}")
                self._refresh_hosts()
            elif kind == "pair_failed":
                self._is_pairing = False
                self._pair_button.configure(state="normal")
                self._connect_button.configure(state="normal")
                self._scan_button.configure(state="normal")
                self._status.configure(text="狀態：配對失敗")
                self._append_log(f"pair failed: {payload}")
                self._update_pair_controls()
        self._root.after(UI_POLL_INTERVAL_MS, self._poll_events)

    def _append_log(self, message: str) -> None:
        self._log.configure(state="normal")
        self._log.insert("end", message + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _handle_close(self) -> None:
        self._capture.stop()
        self._link.close("視窗關閉")
        self._root.destroy()
