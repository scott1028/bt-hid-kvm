import pytest
from evdev import ecodes

from bt_hid_kvm.constants.hid import KEYCODE_TO_HID_USAGE


@pytest.mark.parametrize(
    ("keycode", "usage"),
    [
        (ecodes.KEY_A, 0x04),
        (ecodes.KEY_Z, 0x1D),
        (ecodes.KEY_1, 0x1E),
        (ecodes.KEY_0, 0x27),
        (ecodes.KEY_ENTER, 0x28),
        (ecodes.KEY_ESC, 0x29),
        (ecodes.KEY_BACKSLASH, 0x31),
        (ecodes.KEY_GRAVE, 0x35),
        (ecodes.KEY_F12, 0x45),
        (ecodes.KEY_DELETE, 0x4C),
        (ecodes.KEY_RIGHT, 0x4F),
        (ecodes.KEY_UP, 0x52),
        (ecodes.KEY_KPENTER, 0x58),
        (ecodes.KEY_COMPOSE, 0x65),
        (ecodes.KEY_MUTE, 0x7F),
        (ecodes.KEY_VOLUMEUP, 0x80),
        (ecodes.KEY_VOLUMEDOWN, 0x81),
    ],
)
def test_keycode_maps_to_hid_usage(keycode, usage):
    assert KEYCODE_TO_HID_USAGE.get(keycode) == usage
