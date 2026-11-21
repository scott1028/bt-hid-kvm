import dbus
from gi.repository import GLib

from bt_hid_kvm.utils.bt_pairing import PairingAgent

DEVICE_PATH = "/org/bluez/hci0/dev_98_BD_80_A5_22_41"


def get_bluez_answer(is_accepted: bool) -> tuple[list[int], list[bool], list[dbus.DBusException]]:
    """Answer one passkey request; return the passkeys shown, and the replies and errors BlueZ gets."""
    passkeys, replies, errors = [], [], []

    def handle_request_confirmation(passkey, answer):
        passkeys.append(passkey)
        answer(is_accepted)

    agent = PairingAgent(None, None, on_request_confirmation=handle_request_confirmation, on_cancel=lambda: None)
    agent.RequestConfirmation(DEVICE_PATH, dbus.UInt32(123456), lambda: replies.append(True), errors.append)
    # Answers are sent from the GLib thread; run its pending callbacks.
    context = GLib.MainContext.default()
    while context.pending():
        context.iteration(False)
    return passkeys, replies, errors


def test_agent_replies_when_user_confirms_passkey():
    passkeys, replies, errors = get_bluez_answer(True)
    assert passkeys == [123456]
    assert (replies, errors) == ([True], [])


def test_agent_rejects_when_user_denies_passkey():
    _, replies, errors = get_bluez_answer(False)
    assert replies == []
    assert [error.get_dbus_name() for error in errors] == ["org.bluez.Error.Rejected"]


def test_agent_tells_ui_when_bluez_cancels():
    cancels = []
    agent = PairingAgent(
        None, None, on_request_confirmation=lambda passkey, answer: None, on_cancel=lambda: cancels.append(True)
    )
    agent.Cancel()
    assert cancels == [True]
