import os
from pathlib import Path

from evdev import ecodes

# Hold this key to send keyboard and mouse to the host.
TRIGGER_KEY = ecodes.KEY_LEFTMETA
UINPUT_KEYBOARD_NAME = "bt_hid_kvm keyboard"

# UUIDs and paths below name this app to BlueZ, not any hardware: same on every machine and
# every version, so BlueZ refuses a second running instance.
# BlueZ rejects external profiles on the HID UUID (owned by its input plugin),
# so register under a private UUID; the SDP record itself still declares HID 0x1124.
PROFILE_UUID = "9d2b6c0e-6a8f-4f1e-9b7a-3c5d2e1f0a11"
PROFILE_PATH = "/org/bluez/bt_hid_kvm"
# Windows opens the HID channels itself, so bluetoothd also listens on them for this app.
# Listening fails while bluetoothd's input plugin holds PSM 17/19; separate profiles keep the HID record alive then.
CONTROL_PROFILE_UUID = "f3874a2d-2a3d-42ba-8c8d-95c73fa6a56c"
CONTROL_PROFILE_PATH = "/org/bluez/bt_hid_kvm/control"
INTERRUPT_PROFILE_UUID = "3d416b4f-f503-4fee-a13a-a3aafae6b3b5"
INTERRUPT_PROFILE_PATH = "/org/bluez/bt_hid_kvm/interrupt"
AGENT_PATH = "/org/bluez/bt_hid_kvm/agent"

# Paged only to make BlueZ create the device object before Pair()
PSM_SDP = 0x01
PSM_CONTROL = 0x11
PSM_INTERRUPT = 0x13

# Class of Device major class; the host list shows only computers.
COMPUTER_MAJOR_CLASS = 0x01

# Seconds
CONNECT_TIMEOUT = 10.0
SEND_TIMEOUT = 1.0
# Covers both users comparing passkeys; longer than BlueZ's own agent timeout
PAIR_TIMEOUT = 120.0
# About two Classic inquiry rounds
SCAN_DURATION = 20.0
# Kernel clamps this to its minimum (4608 bytes, about 4 reports), so stale motion cannot pile up.
INTERRUPT_SNDBUF = 1
# About 125 Hz, a typical Bluetooth mouse report rate
MOUSE_FLUSH_INTERVAL = 0.008
IDLE_POLL_INTERVAL = 0.1

UI_POLL_INTERVAL_MS = 50
SCAN_REFRESH_MS = 1000
MODE_COLOR_LOCAL = "#757575"
MODE_COLOR_REMOTE = "#2e7d32"
HINT_COLOR = "#757575"
# Remembered UI choices; a broken file is deleted and the defaults come back.
UI_STATE_PATH = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "bt-hid-kvm" / "ui_state.json"
