import pytest
from evdev import ecodes

from bt_hid_kvm.utils.hid_report import (
    MouseAccumulator,
    get_control_reply,
    get_keyboard_report,
    get_keyboard_report_from_keycodes,
    get_mouse_report,
)


def test_keyboard_report_pads_keys_to_six():
    # HIDP input header, report ID 1, Left Shift, reserved, 'a', 'b', then empty slots
    assert get_keyboard_report(0x02, [0x04, 0x05]) == bytes(
        [0xA1, 0x01, 0x02, 0x00, 0x04, 0x05, 0x00, 0x00, 0x00, 0x00]
    )


def test_keyboard_report_keeps_first_six_keys():
    assert get_keyboard_report(0, [4, 5, 6, 7, 8, 9, 10]) == bytes(
        [0xA1, 0x01, 0x00, 0x00, 4, 5, 6, 7, 8, 9]
    )


def test_mouse_report_packs_signed_little_endian():
    # header, report ID 2, left button, X=-2 (int16 LE), Y=300 (int16 LE), wheel=-1, pan=1
    assert get_mouse_report(0x01, -2, 300, -1, 1) == bytes(
        [0xA1, 0x02, 0x01, 0xFE, 0xFF, 0x2C, 0x01, 0xFF, 0x01]
    )


def test_mouse_report_clamps_to_descriptor_range():
    # X/Y limited to +-32767, wheel/pan limited to +-127
    assert get_mouse_report(0, 40000, -40000, 500, -500) == get_mouse_report(0, 32767, -32767, 127, -127)


@pytest.mark.parametrize("message", [b"\x52\x01\x00", b"\x71", b"\x90\x00"])
def test_control_reply_acks_set_requests(message):
    # SET_REPORT(output), SET_PROTOCOL(report), SET_IDLE -> HANDSHAKE success
    assert get_control_reply(message) == b"\x00"


def test_control_reply_reports_report_protocol():
    # GET_PROTOCOL -> DATA(other) with report protocol
    assert get_control_reply(b"\x60") == b"\xa0\x01"


def test_control_reply_rejects_get_report():
    # GET_REPORT(input, id 1) -> HANDSHAKE unsupported request
    assert get_control_reply(b"\x41\x01") == b"\x03"


def test_control_reply_ignores_hid_control():
    # HID_CONTROL(virtual cable unplug) needs no reply
    assert get_control_reply(b"\x15") is None


def test_keyboard_report_from_keycodes_splits_modifiers():
    # Left Ctrl + Right Shift + C; unknown keycode 0x2FF is skipped
    report = get_keyboard_report_from_keycodes(
        [ecodes.KEY_LEFTCTRL, ecodes.KEY_RIGHTSHIFT, ecodes.KEY_C, 0x2FF]
    )
    assert report == get_keyboard_report(0x01 | 0x20, [0x06])


def test_mouse_accumulator_sums_motion_until_popped():
    accumulator = MouseAccumulator()
    accumulator.add_event(ecodes.EV_REL, ecodes.REL_X, 3)
    accumulator.add_event(ecodes.EV_REL, ecodes.REL_X, 4)
    accumulator.add_event(ecodes.EV_REL, ecodes.REL_Y, -2)
    assert accumulator.has_motion
    assert accumulator.pop_report() == get_mouse_report(0, 7, -2)
    assert not accumulator.has_motion
    assert accumulator.pop_report() == get_mouse_report(0, 0, 0)


def test_mouse_accumulator_tracks_buttons_and_wheels():
    accumulator = MouseAccumulator()
    accumulator.add_event(ecodes.EV_KEY, ecodes.BTN_LEFT, 1)
    accumulator.add_event(ecodes.EV_KEY, ecodes.BTN_SIDE, 1)
    accumulator.add_event(ecodes.EV_REL, ecodes.REL_WHEEL, 1)
    accumulator.add_event(ecodes.EV_REL, ecodes.REL_WHEEL_HI_RES, 120)
    accumulator.add_event(ecodes.EV_REL, ecodes.REL_HWHEEL, -1)
    assert accumulator.pop_report() == get_mouse_report(0x01 | 0x08, 0, 0, 1, -1)
    accumulator.add_event(ecodes.EV_KEY, ecodes.BTN_LEFT, 0)
    assert accumulator.pop_report() == get_mouse_report(0x08, 0, 0)
