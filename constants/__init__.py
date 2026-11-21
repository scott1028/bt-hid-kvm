from evdev import ecodes

TARGET_MAC = "98:BD:80:A5:22:41"

# Hold this key to send keyboard and mouse to the host.
TRIGGER_KEY = ecodes.KEY_LEFTMETA
UINPUT_KEYBOARD_NAME = "bt_hid_kvm keyboard"

# BlueZ rejects external profiles on the HID UUID (owned by its input plugin),
# so register under a private UUID; the SDP record itself still declares HID 0x1124.
PROFILE_UUID = "9d2b6c0e-6a8f-4f1e-9b7a-3c5d2e1f0a11"
PROFILE_PATH = "/org/bluez/bt_hid_kvm"
AGENT_PATH = "/org/bluez/bt_hid_kvm/agent"
ADAPTER_PATH = "/org/bluez/hci0"

# Paged only to make BlueZ create the device object before Pair()
PSM_SDP = 0x01
PSM_CONTROL = 0x11
PSM_INTERRUPT = 0x13

# Seconds
CONNECT_TIMEOUT = 10.0
SEND_TIMEOUT = 1.0
# Covers both users comparing passkeys; longer than BlueZ's own agent timeout
PAIR_TIMEOUT = 120.0
# Kernel clamps this to its minimum (4608 bytes, about 4 reports), so stale motion cannot pile up.
INTERRUPT_SNDBUF = 1
# About 125 Hz, a typical Bluetooth mouse report rate
MOUSE_FLUSH_INTERVAL = 0.008
IDLE_POLL_INTERVAL = 0.1

UI_POLL_INTERVAL_MS = 50
MODE_COLOR_LOCAL = "#757575"
MODE_COLOR_REMOTE = "#2e7d32"
