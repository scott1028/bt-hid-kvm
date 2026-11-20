import struct
from collections.abc import Sequence

from evdev import ecodes

from bt_hid_kvm.constants.hid import (
    HIDP_DATA_INPUT,
    HIDP_DATA_OTHER,
    HIDP_HANDSHAKE_ERR_UNSUPPORTED,
    HIDP_HANDSHAKE_SUCCESS,
    HIDP_PROTOCOL_REPORT,
    HIDP_TYPE_GET_PROTOCOL,
    HIDP_TYPE_HID_CONTROL,
    HIDP_TYPE_SET_IDLE,
    HIDP_TYPE_SET_PROTOCOL,
    HIDP_TYPE_SET_REPORT,
    KEYCODE_TO_HID_USAGE,
    MAX_KEYS,
    MODIFIER_BITS,
    MOUSE_BUTTON_BITS,
    REPORT_ID_KEYBOARD,
    REPORT_ID_MOUSE,
)


def get_keyboard_report(modifiers: int, keys: Sequence[int]) -> bytes:
    pressed = list(keys)[:MAX_KEYS]
    slots = pressed + [0] * (MAX_KEYS - len(pressed))
    return bytes([HIDP_DATA_INPUT, REPORT_ID_KEYBOARD, modifiers, 0x00, *slots])


def get_control_reply(message: bytes) -> bytes | None:
    """Reply to a host request on the HID control channel."""
    transaction_type = message[0] >> 4
    if transaction_type in (HIDP_TYPE_SET_REPORT, HIDP_TYPE_SET_PROTOCOL, HIDP_TYPE_SET_IDLE):
        return bytes([HIDP_HANDSHAKE_SUCCESS])
    if transaction_type == HIDP_TYPE_GET_PROTOCOL:
        return bytes([HIDP_DATA_OTHER, HIDP_PROTOCOL_REPORT])
    if transaction_type == HIDP_TYPE_HID_CONTROL:
        return None
    return bytes([HIDP_HANDSHAKE_ERR_UNSUPPORTED])


def clamp(number: int, limit: int) -> int:
    return max(-limit, min(limit, number))


def get_mouse_report(buttons: int, dx: int, dy: int, wheel: int = 0, pan: int = 0) -> bytes:
    return struct.pack(
        "<BBBhhbb",
        HIDP_DATA_INPUT,
        REPORT_ID_MOUSE,
        buttons,
        clamp(dx, 32767),
        clamp(dy, 32767),
        clamp(wheel, 127),
        clamp(pan, 127),
    )


def get_keyboard_report_from_keycodes(keycodes: Sequence[int]) -> bytes:
    modifiers = 0
    usages = []
    for keycode in keycodes:
        if keycode in MODIFIER_BITS:
            modifiers |= MODIFIER_BITS[keycode]
        elif keycode in KEYCODE_TO_HID_USAGE:
            usages.append(KEYCODE_TO_HID_USAGE[keycode])
    return get_keyboard_report(modifiers, usages)


class MouseAccumulator:
    """Merges evdev mouse events into one HID mouse report."""

    def __init__(self):
        self.buttons = 0
        self._motion = {ecodes.REL_X: 0, ecodes.REL_Y: 0, ecodes.REL_WHEEL: 0, ecodes.REL_HWHEEL: 0}

    @property
    def has_motion(self) -> bool:
        return any(self._motion.values())

    def add_event(self, event_type: int, code: int, value: int) -> None:
        # *_HI_RES wheel events are skipped because the plain wheel events carry the same scroll.
        if event_type == ecodes.EV_REL and code in self._motion:
            self._motion[code] += value
        elif event_type == ecodes.EV_KEY and code in MOUSE_BUTTON_BITS:
            if value:
                self.buttons |= MOUSE_BUTTON_BITS[code]
            else:
                self.buttons &= ~MOUSE_BUTTON_BITS[code]

    def pop_report(self) -> bytes:
        report = get_mouse_report(
            self.buttons,
            self._motion[ecodes.REL_X],
            self._motion[ecodes.REL_Y],
            self._motion[ecodes.REL_WHEEL],
            self._motion[ecodes.REL_HWHEEL],
        )
        self._motion = dict.fromkeys(self._motion, 0)
        return report
