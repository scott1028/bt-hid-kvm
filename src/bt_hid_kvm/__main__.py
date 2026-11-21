import argparse
import time
import tkinter as tk

from bt_hid_kvm.components.main_window import MainWindow
from bt_hid_kvm.constants.hid import KEYBOARD_MODIFIER_LEFT_SHIFT
from bt_hid_kvm.utils.bt_hid_link import (
    HidLink,
    get_adapter_path,
    get_is_paired,
    register_hid_profile,
)
from bt_hid_kvm.utils.hid_report import get_keyboard_report, get_mouse_report


def run_selftest(mac: str) -> None:
    """Draw a square on the host and tap Shift, to verify the HID link."""
    link = HidLink(
        on_disconnect=lambda reason: print(f"disconnected: {reason}", flush=True),
        on_accept=lambda host: print(f"{host} opened the HID channels", flush=True),
    )
    bus = register_hid_profile(link.accept)
    adapter_path = get_adapter_path(bus)
    print(f"HID profile registered; waiting until {mac} is paired", flush=True)
    while not get_is_paired(bus, adapter_path, mac):
        time.sleep(1)

    # Windows connects on its own after pairing; Linux hosts wait for this device to connect.
    for attempt in range(1, 11):
        if link.is_connected:
            break
        try:
            link.connect(mac)
        except OSError as error:
            print(f"connect attempt {attempt} failed: {error}", flush=True)
            time.sleep(3)
    if not link.is_connected:
        raise SystemExit("could not connect to host HID channels")

    print("connected; drawing a square", flush=True)
    time.sleep(1)
    for dx, dy in [(10, 0), (0, 10), (-10, 0), (0, -10)]:
        for _ in range(20):
            link.send(get_mouse_report(0, dx, dy))
            time.sleep(0.01)
    link.send(get_keyboard_report(KEYBOARD_MODIFIER_LEFT_SHIFT, []))
    link.send(get_keyboard_report(0, []))
    time.sleep(1)
    link.close()
    print("selftest done", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(prog="bt_hid_kvm")
    parser.add_argument("--mac", help="Bluetooth address of the host to control; the GUI defaults to a paired host")
    parser.add_argument("--selftest", action="store_true", help="draw a square on the host and exit")
    args = parser.parse_args()
    if args.selftest and args.mac is None:
        parser.error("--selftest needs --mac")
    if args.selftest:
        run_selftest(args.mac)
        return
    root = tk.Tk()
    MainWindow(root, args.mac)
    root.mainloop()


if __name__ == "__main__":
    main()
