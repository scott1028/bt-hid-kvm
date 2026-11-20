import queue
import threading
import tkinter as tk
from tkinter import ttk

from bt_hid_kvm.constants import (
    MODE_COLOR_LOCAL,
    MODE_COLOR_REMOTE,
    UI_POLL_INTERVAL_MS,
)
from bt_hid_kvm.utils.bt_hid_link import HidLink
from bt_hid_kvm.utils.input_capture import InputCapture


class MainWindow:
    """Tk window; worker threads talk to it only through a queue."""

    def __init__(self, root: tk.Tk, mac: str):
        self._root = root
        self._events: queue.Queue[tuple[str, object]] = queue.Queue()
        self._link = HidLink(on_disconnect=lambda reason: self._events.put(("disconnected", reason)))
        self._capture = InputCapture(
            self._link,
            on_mode_change=lambda is_remote: self._events.put(("mode", is_remote)),
            on_log=lambda message: self._events.put(("log", message)),
        )
        self._is_connecting = False

        root.title("BT HID KVM")
        root.minsize(420, 0)
        frame = ttk.Frame(root, padding=12)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="目標 MAC").grid(row=0, column=0, sticky="w")
        self._mac = tk.StringVar(value=mac)
        ttk.Entry(frame, textvariable=self._mac, width=20).grid(row=0, column=1, sticky="we", padx=8)
        self._connect_button = ttk.Button(frame, text="連線", command=self._handle_connect_click)
        self._connect_button.grid(row=0, column=2)

        self._status = ttk.Label(frame, text="狀態：未連線")
        self._status.grid(row=1, column=0, columnspan=3, sticky="w", pady=(8, 0))

        self._mode = tk.Label(
            frame, text="本機", bg=MODE_COLOR_LOCAL, fg="white", font=("TkDefaultFont", 20, "bold"), pady=12
        )
        self._mode.grid(row=2, column=0, columnspan=3, sticky="we", pady=8)
        ttk.Label(frame, text="連線後按住左 Win（Keychron Mac 模式為 Command 位置）控制 288V").grid(
            row=3, column=0, columnspan=3, sticky="w"
        )

        self._devices = ttk.Label(frame, text="", justify="left")
        self._devices.grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 0))

        self._log = tk.Text(frame, height=8, width=60, state="disabled")
        self._log.grid(row=5, column=0, columnspan=3, sticky="nsew", pady=(8, 0))
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(5, weight=1)

        self._capture.start()
        keyboards = ", ".join(device.name.strip() for device in self._capture.keyboards) or "（無）"
        mice = ", ".join(device.name.strip() for device in self._capture.mice) or "（無）"
        self._devices.configure(text=f"鍵盤：{keyboards}\n滑鼠：{mice}")

        root.protocol("WM_DELETE_WINDOW", self._handle_close)
        root.after(UI_POLL_INTERVAL_MS, self._poll_events)

    def _handle_connect_click(self) -> None:
        if self._link.is_connected:
            self._link.close("使用者中斷")
            return
        if self._is_connecting:
            return
        self._is_connecting = True
        self._connect_button.configure(state="disabled")
        self._status.configure(text="狀態：連線中…")
        threading.Thread(target=self._connect, args=(self._mac.get().strip(),), daemon=True).start()

    def _connect(self, mac: str) -> None:
        try:
            self._link.connect(mac)
            self._events.put(("connected", mac))
        except OSError as error:
            self._events.put(("connect_failed", error))

    def _poll_events(self) -> None:
        while not self._events.empty():
            kind, payload = self._events.get_nowait()
            if kind == "log":
                self._append_log(str(payload))
            elif kind == "mode":
                is_remote = bool(payload)
                self._mode.configure(
                    text="288V" if is_remote else "本機",
                    bg=MODE_COLOR_REMOTE if is_remote else MODE_COLOR_LOCAL,
                )
            elif kind == "connected":
                self._is_connecting = False
                self._connect_button.configure(state="normal", text="中斷")
                self._status.configure(text=f"狀態：已連線 {payload}")
                self._append_log(f"connected to {payload}")
            elif kind == "connect_failed":
                self._is_connecting = False
                self._connect_button.configure(state="normal", text="連線")
                self._status.configure(text="狀態：連線失敗")
                self._append_log(f"connect failed: {payload}")
            elif kind == "disconnected":
                self._connect_button.configure(text="連線")
                self._status.configure(text="狀態：未連線")
                self._append_log(f"disconnected: {payload}")
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
