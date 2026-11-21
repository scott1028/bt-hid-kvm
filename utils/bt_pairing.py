import queue
import socket
import time
from collections.abc import Callable

import dbus
import dbus.service
from gi.repository import GLib

from bt_hid_kvm.constants import (
    ADAPTER_PATH,
    AGENT_PATH,
    CONNECT_TIMEOUT,
    PAIR_TIMEOUT,
    PSM_SDP,
)
from bt_hid_kvm.utils.bt_hid_link import get_device_path


class RejectedError(dbus.DBusException):
    _dbus_error_name = "org.bluez.Error.Rejected"


class PairingAgent(dbus.service.Object):
    """BlueZ Agent1 for this app's own Pair() calls; asks the user to compare passkeys."""

    def __init__(
        self,
        bus: dbus.SystemBus | None,
        path: str | None,
        on_request_confirmation: Callable[[int, Callable[[bool], None]], None],
        on_cancel: Callable[[], None],
    ):
        super().__init__(bus, path)
        self._on_request_confirmation = on_request_confirmation
        self._on_cancel = on_cancel

    @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
    def Release(self):
        pass

    @dbus.service.method(
        "org.bluez.Agent1", in_signature="ou", out_signature="", async_callbacks=("reply", "error")
    )
    def RequestConfirmation(self, device, passkey, reply, error):
        def answer(is_accepted: bool) -> None:
            # The UI answers from the Tk thread; reply on the GLib thread, which owns D-Bus dispatch.
            if is_accepted:
                GLib.idle_add(reply)
            else:
                GLib.idle_add(error, RejectedError("passkey rejected by user"))

        self._on_request_confirmation(int(passkey), answer)

    @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
    def Cancel(self):
        self._on_cancel()


def register_pairing_agent(
    bus: dbus.SystemBus,
    on_request_confirmation: Callable[[int, Callable[[bool], None]], None],
    on_cancel: Callable[[], None],
) -> None:
    PairingAgent(bus, AGENT_PATH, on_request_confirmation, on_cancel)
    manager = dbus.Interface(bus.get_object("org.bluez", "/org/bluez"), "org.bluez.AgentManager1")
    # Not the default agent: BlueZ routes only this app's own Pair() requests here,
    # so the desktop agent keeps handling everything else.
    manager.RegisterAgent(AGENT_PATH, "DisplayYesNo")


def pair_device(bus: dbus.SystemBus, mac: str) -> None:
    """Pair with a known address without discovery; blocks until pairing ends."""
    path = get_device_path(mac)
    adapter = dbus.Interface(bus.get_object("org.bluez", ADAPTER_PATH), "org.bluez.Adapter1")
    try:
        # Pair() fails with AlreadyExists on a bonded device, so drop the old bond first.
        adapter.RemoveDevice(path)
    except dbus.DBusException as error:
        if error.get_dbus_name() != "org.bluez.Error.DoesNotExist":
            raise
    properties = dbus.Interface(
        bus.get_object("org.bluez", path, introspect=False), "org.freedesktop.DBus.Properties"
    )
    device = dbus.Interface(bus.get_object("org.bluez", path, introspect=False), "org.bluez.Device1")
    outcome: queue.Queue[dbus.DBusException | None] = queue.Queue()
    # Paging by address makes BlueZ create the device object, so the host need not be discoverable.
    # The SDP channel needs no security, so the kernel does not start pairing on its own.
    page = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
    page.settimeout(CONNECT_TIMEOUT)
    try:
        page.connect((mac, PSM_SDP))
        # BlueZ adds the object shortly after the link comes up.
        deadline = time.monotonic() + CONNECT_TIMEOUT
        while True:
            try:
                properties.Get("org.bluez.Device1", "Address")
                break
            except dbus.DBusException:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.1)
        # Async call: its reply and the agent's passkey request are both dispatched on the GLib thread.
        device.Pair(reply_handler=lambda: outcome.put(None), error_handler=outcome.put, timeout=PAIR_TIMEOUT)
        # Keep the page link up until pairing ends, so Pair() does not race its idle disconnect.
        error = outcome.get()
    finally:
        page.close()
    if error is not None:
        raise error
    properties.Set("org.bluez.Device1", "Trusted", dbus.Boolean(True, variant_level=1))
