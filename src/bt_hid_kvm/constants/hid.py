from evdev import ecodes

REPORT_ID_KEYBOARD = 0x01
REPORT_ID_MOUSE = 0x02

# HIDP transaction headers (Bluetooth HID profile)
HIDP_DATA_INPUT = 0xA1
HIDP_DATA_OTHER = 0xA0
HIDP_HANDSHAKE_SUCCESS = 0x00
HIDP_HANDSHAKE_ERR_UNSUPPORTED = 0x03
HIDP_TYPE_HID_CONTROL = 0x1
HIDP_TYPE_SET_REPORT = 0x5
HIDP_TYPE_GET_PROTOCOL = 0x6
HIDP_TYPE_SET_PROTOCOL = 0x7
HIDP_TYPE_SET_IDLE = 0x9
HIDP_CONTROL_VIRTUAL_CABLE_UNPLUG = 0x15
HIDP_PROTOCOL_REPORT = 0x01

MAX_KEYS = 6
KEYBOARD_MODIFIER_LEFT_SHIFT = 0x02

# Linux keycode -> HID modifier bit (usages 0xE0-0xE7)
MODIFIER_BITS = {
    ecodes.KEY_LEFTCTRL: 0x01,
    ecodes.KEY_LEFTSHIFT: 0x02,
    ecodes.KEY_LEFTALT: 0x04,
    ecodes.KEY_LEFTMETA: 0x08,
    ecodes.KEY_RIGHTCTRL: 0x10,
    ecodes.KEY_RIGHTSHIFT: 0x20,
    ecodes.KEY_RIGHTALT: 0x40,
    ecodes.KEY_RIGHTMETA: 0x80,
}

# Linux button code -> HID button bit (buttons 1-5)
MOUSE_BUTTON_BITS = {
    ecodes.BTN_LEFT: 0x01,
    ecodes.BTN_RIGHT: 0x02,
    ecodes.BTN_MIDDLE: 0x04,
    ecodes.BTN_SIDE: 0x08,
    ecodes.BTN_EXTRA: 0x10,
}

# HID usage (index) -> Linux keycode, from kernel drivers/hid/hid-input.c hid_keyboard[], usages 0x00-0x81.
HID_USAGE_TO_KEYCODE = [
    0, 0, 0, 0, 30, 48, 46, 32, 18, 33, 34, 35, 23, 36, 37, 38,
    50, 49, 24, 25, 16, 19, 31, 20, 22, 47, 17, 45, 21, 44, 2, 3,
    4, 5, 6, 7, 8, 9, 10, 11, 28, 1, 14, 15, 57, 12, 13, 26,
    27, 43, 43, 39, 40, 41, 51, 52, 53, 58, 59, 60, 61, 62, 63, 64,
    65, 66, 67, 68, 87, 88, 99, 70, 119, 110, 102, 104, 111, 107, 109, 106,
    105, 108, 103, 69, 98, 55, 74, 78, 96, 79, 80, 81, 75, 76, 77, 71,
    72, 73, 82, 83, 86, 127, 116, 117, 183, 184, 185, 186, 187, 188, 189, 190,
    191, 192, 193, 194, 134, 138, 130, 132, 128, 129, 131, 137, 133, 135, 136, 113,
    115, 114,
]

# Reversed so the lowest usage wins for duplicated keycodes (e.g. backslash).
KEYCODE_TO_HID_USAGE = {
    keycode: usage for usage, keycode in reversed(list(enumerate(HID_USAGE_TO_KEYCODE))) if keycode
}

REPORT_DESCRIPTOR = bytes([
    # Keyboard, report ID 1
    0x05, 0x01,        # Usage Page (Generic Desktop)
    0x09, 0x06,        # Usage (Keyboard)
    0xA1, 0x01,        # Collection (Application)
    0x85, 0x01,        #   Report ID (1)
    0x05, 0x07,        #   Usage Page (Key Codes)
    0x19, 0xE0,        #   Usage Minimum (224)
    0x29, 0xE7,        #   Usage Maximum (231)
    0x15, 0x00,        #   Logical Minimum (0)
    0x25, 0x01,        #   Logical Maximum (1)
    0x75, 0x01,        #   Report Size (1)
    0x95, 0x08,        #   Report Count (8)
    0x81, 0x02,        #   Input (Data, Var, Abs) - modifiers
    0x95, 0x01,        #   Report Count (1)
    0x75, 0x08,        #   Report Size (8)
    0x81, 0x01,        #   Input (Const) - reserved
    0x95, 0x05,        #   Report Count (5)
    0x75, 0x01,        #   Report Size (1)
    0x05, 0x08,        #   Usage Page (LEDs)
    0x19, 0x01,        #   Usage Minimum (1)
    0x29, 0x05,        #   Usage Maximum (5)
    0x91, 0x02,        #   Output (Data, Var, Abs) - LEDs
    0x95, 0x01,        #   Report Count (1)
    0x75, 0x03,        #   Report Size (3)
    0x91, 0x01,        #   Output (Const) - padding
    0x95, 0x06,        #   Report Count (6)
    0x75, 0x08,        #   Report Size (8)
    0x15, 0x00,        #   Logical Minimum (0)
    0x26, 0xFF, 0x00,  #   Logical Maximum (255)
    0x05, 0x07,        #   Usage Page (Key Codes)
    0x19, 0x00,        #   Usage Minimum (0)
    0x29, 0xFF,        #   Usage Maximum (255)
    0x81, 0x00,        #   Input (Data, Array) - keys
    0xC0,              # End Collection
    # Mouse, report ID 2
    0x05, 0x01,        # Usage Page (Generic Desktop)
    0x09, 0x02,        # Usage (Mouse)
    0xA1, 0x01,        # Collection (Application)
    0x85, 0x02,        #   Report ID (2)
    0x09, 0x01,        #   Usage (Pointer)
    0xA1, 0x00,        #   Collection (Physical)
    0x05, 0x09,        #     Usage Page (Buttons)
    0x19, 0x01,        #     Usage Minimum (1)
    0x29, 0x05,        #     Usage Maximum (5)
    0x15, 0x00,        #     Logical Minimum (0)
    0x25, 0x01,        #     Logical Maximum (1)
    0x95, 0x05,        #     Report Count (5)
    0x75, 0x01,        #     Report Size (1)
    0x81, 0x02,        #     Input (Data, Var, Abs) - buttons
    0x95, 0x01,        #     Report Count (1)
    0x75, 0x03,        #     Report Size (3)
    0x81, 0x01,        #     Input (Const) - padding
    0x05, 0x01,        #     Usage Page (Generic Desktop)
    0x09, 0x30,        #     Usage (X)
    0x09, 0x31,        #     Usage (Y)
    0x16, 0x01, 0x80,  #     Logical Minimum (-32767)
    0x26, 0xFF, 0x7F,  #     Logical Maximum (32767)
    0x75, 0x10,        #     Report Size (16)
    0x95, 0x02,        #     Report Count (2)
    0x81, 0x06,        #     Input (Data, Var, Rel) - X, Y
    0x09, 0x38,        #     Usage (Wheel)
    0x15, 0x81,        #     Logical Minimum (-127)
    0x25, 0x7F,        #     Logical Maximum (127)
    0x75, 0x08,        #     Report Size (8)
    0x95, 0x01,        #     Report Count (1)
    0x81, 0x06,        #     Input (Data, Var, Rel) - wheel
    0x05, 0x0C,        #     Usage Page (Consumer)
    0x0A, 0x38, 0x02,  #     Usage (AC Pan)
    0x95, 0x01,        #     Report Count (1)
    0x81, 0x06,        #     Input (Data, Var, Rel) - horizontal wheel
    0xC0,              #   End Collection
    0xC0,              # End Collection
])

# HIDReconnectInitiate=true + HIDNormallyConnectable=false: this device opens the connection.
SDP_RECORD_XML = f"""<?xml version="1.0" encoding="UTF-8" ?>
<record>
  <attribute id="0x0001">
    <sequence><uuid value="0x1124" /></sequence>
  </attribute>
  <attribute id="0x0004">
    <sequence>
      <sequence><uuid value="0x0100" /><uint16 value="0x0011" /></sequence>
      <sequence><uuid value="0x0011" /></sequence>
    </sequence>
  </attribute>
  <attribute id="0x0005">
    <sequence><uuid value="0x1002" /></sequence>
  </attribute>
  <attribute id="0x0006">
    <sequence><uint16 value="0x656e" /><uint16 value="0x006a" /><uint16 value="0x0100" /></sequence>
  </attribute>
  <attribute id="0x0009">
    <sequence><sequence><uuid value="0x1124" /><uint16 value="0x0101" /></sequence></sequence>
  </attribute>
  <attribute id="0x000d">
    <sequence><sequence>
      <sequence><uuid value="0x0100" /><uint16 value="0x0013" /></sequence>
      <sequence><uuid value="0x0011" /></sequence>
    </sequence></sequence>
  </attribute>
  <attribute id="0x0100"><text value="bt_hid_kvm" /></attribute>
  <attribute id="0x0101"><text value="Keyboard and Mouse" /></attribute>
  <attribute id="0x0102"><text value="bt_hid_kvm" /></attribute>
  <attribute id="0x0201"><uint16 value="0x0111" /></attribute>
  <attribute id="0x0202"><uint8 value="0xc0" /></attribute>
  <attribute id="0x0203"><uint8 value="0x00" /></attribute>
  <attribute id="0x0204"><boolean value="false" /></attribute>
  <attribute id="0x0205"><boolean value="true" /></attribute>
  <attribute id="0x0206">
    <sequence><sequence>
      <uint8 value="0x22" />
      <text encoding="hex" value="{REPORT_DESCRIPTOR.hex()}" />
    </sequence></sequence>
  </attribute>
  <attribute id="0x0207">
    <sequence><sequence><uint16 value="0x0409" /><uint16 value="0x0100" /></sequence></sequence>
  </attribute>
  <attribute id="0x020b"><uint16 value="0x0100" /></attribute>
  <attribute id="0x020c"><uint16 value="0x0c80" /></attribute>
  <attribute id="0x020d"><boolean value="false" /></attribute>
  <attribute id="0x020e"><boolean value="false" /></attribute>
</record>
"""
