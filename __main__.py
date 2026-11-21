import argparse
import time
import tkinter as tk

from bt_hid_kvm.components.main_window import MainWindow
from bt_hid_kvm.constants import TARGET_MAC
from bt_hid_kvm.constants.hid import KEYBOARD_MODIFIER_LEFT_SHIFT
from bt_hid_kvm.utils.bt_hid_link import HidLink, get_is_paired, register_hid_profile
from bt_hid_kvm.utils.hid_report import get_keyboard_report, get_mouse_report


def run_selftest(mac: str) -> None:
    """Draw a square on the host and tap Shift, to verify the HID link."""
    bus = register_hid_profile()
    print(f"HID profile registered; waiting until {mac} is paired", flush=True)
    while not get_is_paired(bus, mac):
        time.sleep(1)

    link = HidLink(on_disconnect=lambda reason: print(f"disconnected: {reason}", flush=True))
    for attempt in range(1, 11):
        try:
            link.connect(mac)
            break
        except OSError as error:
            print(f"connect attempt {attempt} failed: {error}", flush=True)
            time.sleep(3)
    else:
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
    parser.add_argument("--mac", default=TARGET_MAC, help="Bluetooth address of the host to control")
    parser.add_argument("--selftest", action="store_true", help="draw a square on the host and exit")
    args = parser.parse_args()
    if args.selftest:
        run_selftest(args.mac)
        return
    bus = register_hid_profile()
    root = tk.Tk()
    MainWindow(root, args.mac, bus)
    root.mainloop()


main()
