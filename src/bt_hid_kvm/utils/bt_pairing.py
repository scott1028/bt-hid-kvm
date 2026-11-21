import queue
import re
import socket
import time
from collections.abc import Callable
from typing import NamedTuple

import dbus
import dbus.service
from gi.repository import GLib

from bt_hid_kvm.constants import (
    ADAPTER_PATH,
    AGENT_PATH,
    COMPUTER_MAJOR_CLASS,
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


class Host(NamedTuple):
    mac: str
    name: str
    is_paired: bool


def get_hosts_from_objects(objects: dict) -> list[Host]:
    """Pick computers on our adapter from BlueZ GetManagedObjects() output; paired ones first."""
    hosts = []
    for interfaces in objects.values():
        properties = interfaces.get("org.bluez.Device1")
        if properties is None or properties["Adapter"] != ADAPTER_PATH:
            continue
        # Bits 12-8 of the Class of Device are the major class.
        if (properties.get("Class", 0) >> 8) & 0x1F != COMPUTER_MAJOR_CLASS:
            continue
        hosts.append(Host(str(properties["Address"]), str(properties["Alias"]), bool(properties["Paired"])))
    return sorted(hosts, key=lambda host: (not host.is_paired, host.name))


def get_known_hosts(bus: dbus.SystemBus) -> list[Host]:
    manager = dbus.Interface(bus.get_object("org.bluez", "/"), "org.freedesktop.DBus.ObjectManager")
    return get_hosts_from_objects(manager.GetManagedObjects())


def start_host_scan(bus: dbus.SystemBus) -> None:
    """Scan until stop_host_scan(); found hosts show up in get_known_hosts()."""
    adapter = dbus.Interface(bus.get_object("org.bluez", ADAPTER_PATH), "org.bluez.Adapter1")
    # Classic only: hosts pair over BR/EDR, and skipping LE keeps the scan from sharing time with it.
    adapter.SetDiscoveryFilter({"Transport": "bredr"})
    adapter.StartDiscovery()


def stop_host_scan(bus: dbus.SystemBus) -> None:
    adapter = dbus.Interface(bus.get_object("org.bluez", ADAPTER_PATH), "org.bluez.Adapter1")
    adapter.StopDiscovery()


def get_mac_from_text(text: str) -> str | None:
    """Return the Bluetooth address in a typed MAC or a host list label."""
    match = re.search(r"(?:[0-9A-F]{2}:){5}[0-9A-F]{2}", text, re.IGNORECASE)
    return match.group().upper() if match else None
