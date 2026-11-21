import queue
import socket
import struct
import threading
from collections.abc import Callable

import dbus
import dbus.mainloop.glib
import dbus.service
from gi.repository import GLib

from bt_hid_kvm.constants import (
    CONNECT_TIMEOUT,
    CONTROL_PROFILE_PATH,
    CONTROL_PROFILE_UUID,
    INTERRUPT_PROFILE_PATH,
    INTERRUPT_PROFILE_UUID,
    INTERRUPT_SNDBUF,
    PROFILE_PATH,
    PROFILE_UUID,
    PSM_CONTROL,
    PSM_INTERRUPT,
    SEND_TIMEOUT,
)
from bt_hid_kvm.constants.hid import HIDP_CONTROL_VIRTUAL_CABLE_UNPLUG, SDP_RECORD_XML
from bt_hid_kvm.utils.hid_report import get_control_reply


class HidProfile(dbus.service.Object):
    """BlueZ Profile1 object; bluetoothd hands it the sockets a host opens on the profile's PSM."""

    def __init__(self, bus: dbus.SystemBus, path: str, on_connection: Callable[[socket.socket], None]):
        super().__init__(bus, path)
        self._on_connection = on_connection

    @dbus.service.method("org.bluez.Profile1", in_signature="", out_signature="")
    def Release(self):
        pass

    @dbus.service.method("org.bluez.Profile1", in_signature="oha{sv}", out_signature="")
    def NewConnection(self, device, fd, properties):
        self._on_connection(socket.socket(fileno=fd.take()))

    @dbus.service.method("org.bluez.Profile1", in_signature="o", out_signature="")
    def RequestDisconnection(self, device):
        pass


def register_hid_profile(on_connection: Callable[[socket.socket], None]) -> dbus.SystemBus:
    """Publish the HID SDP record and listen on PSM 17/19; on_connection runs on the GLib thread."""
    dbus.mainloop.glib.threads_init()
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    threading.Thread(target=GLib.MainLoop().run, daemon=True).start()
    manager = dbus.Interface(bus.get_object("org.bluez", "/org/bluez"), "org.bluez.ProfileManager1")
    server_options = {"Role": "server", "RequireAuthentication": True, "RequireAuthorization": False, "AutoConnect": False}
    profiles = [
        (PROFILE_PATH, PROFILE_UUID, {"ServiceRecord": SDP_RECORD_XML}),
        (CONTROL_PROFILE_PATH, CONTROL_PROFILE_UUID, {"PSM": dbus.UInt16(PSM_CONTROL), "Name": "bt_hid_kvm control"}),
        (INTERRUPT_PROFILE_PATH, INTERRUPT_PROFILE_UUID, {"PSM": dbus.UInt16(PSM_INTERRUPT), "Name": "bt_hid_kvm interrupt"}),
    ]
    for path, uuid, options in profiles:
        HidProfile(bus, path, on_connection)
        manager.RegisterProfile(path, uuid, {**options, **server_options})
    return bus


def get_adapter_path_from_objects(objects: dict) -> str | None:
    """Pick the first Bluetooth adapter (hci0 before hci1) from BlueZ GetManagedObjects() output."""
    paths = [str(path) for path, interfaces in objects.items() if "org.bluez.Adapter1" in interfaces]
    # Shorter first, so hci2 sorts before hci10.
    return min(paths, key=lambda path: (len(path), path), default=None)


def get_adapter_path(bus: dbus.SystemBus) -> str:
    manager = dbus.Interface(bus.get_object("org.bluez", "/"), "org.freedesktop.DBus.ObjectManager")
    adapter_path = get_adapter_path_from_objects(manager.GetManagedObjects())
    if adapter_path is None:
        raise SystemExit("no Bluetooth adapter found")
    return adapter_path


def get_device_path(adapter_path: str, mac: str) -> str:
    return f"{adapter_path}/dev_{mac.replace(':', '_')}"


def get_is_paired(bus: dbus.SystemBus, adapter_path: str, mac: str) -> bool:
    path = get_device_path(adapter_path, mac)
    try:
        properties = dbus.Interface(bus.get_object("org.bluez", path), "org.freedesktop.DBus.Properties")
        return bool(properties.Get("org.bluez.Device1", "Paired"))
    except dbus.DBusException:
        return False


def connect_l2cap(mac: str, psm: int) -> socket.socket:
    sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
    # Require an encrypted link with the bonded key.
    sock.setsockopt(socket.SOL_BLUETOOTH, socket.BT_SECURITY, struct.pack("BB", socket.BT_SECURITY_MEDIUM, 0))
    sock.settimeout(CONNECT_TIMEOUT)
    try:
        sock.connect((mac, psm))
    except OSError:
        sock.close()
        raise
    return sock


def close_channel(sock: socket.socket) -> None:
    # bluetoothd keeps its own copy of host-opened sockets, so close() alone leaves the channel up.
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    sock.close()


class HidLink:
    """Bluetooth HID connection (control PSM 17 + interrupt PSM 19), opened by either side."""

    def __init__(self, on_disconnect: Callable[[str], None], on_accept: Callable[[str], None]):
        self._on_disconnect = on_disconnect
        self._on_accept = on_accept
        self._reports: queue.Queue[bytes | None] = queue.Queue(maxsize=256)
        self._sockets: tuple[socket.socket, socket.socket] | None = None
        self._lock = threading.Lock()
        # Host-opened control channel waiting for its interrupt channel; GLib thread only.
        self._pending_control: tuple[str, socket.socket] | None = None
        self.is_connected = False

    def connect(self, mac: str) -> None:
        control = connect_l2cap(mac, PSM_CONTROL)
        try:
            interrupt = connect_l2cap(mac, PSM_INTERRUPT)
        except OSError:
            control.close()
            raise
        # If the host connected first, its link stays and these channels are dropped.
        self._start((control, interrupt))

    def accept(self, sock: socket.socket) -> None:
        """Take a channel the host opened (Windows does); called on the GLib thread."""
        # Python 3.14 reports L2CAP peers as (bdaddr, psm, cid).
        mac, psm = sock.getpeername()[:2]
        pending, self._pending_control = self._pending_control, None
        if psm == PSM_CONTROL:
            # A newer control channel replaces one whose interrupt never came.
            if pending is not None:
                close_channel(pending[1])
            self._pending_control = (mac, sock)
            return
        # Hosts open control first, then interrupt.
        if pending is None or pending[0] != mac:
            close_channel(sock)
            if pending is not None:
                close_channel(pending[1])
            return
        if self._start((pending[1], sock)):
            self._on_accept(mac)

    def _start(self, sockets: tuple[socket.socket, socket.socket]) -> bool:
        """Run the link on these channels; drops them and returns False if a link is already up."""
        control, interrupt = sockets
        control.settimeout(None)
        interrupt.settimeout(SEND_TIMEOUT)
        interrupt.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, INTERRUPT_SNDBUF)
        reports: queue.Queue[bytes | None] = queue.Queue(maxsize=256)
        with self._lock:
            is_started = not self.is_connected
            if is_started:
                self._sockets = sockets
                self._reports = reports
                self.is_connected = True
        if not is_started:
            for sock in sockets:
                close_channel(sock)
            return False
        for target in (self._read_control, self._read_interrupt, self._send_reports):
            threading.Thread(target=target, args=(sockets, reports), daemon=True).start()
        return True

    @property
    def has_queued_reports(self) -> bool:
        """True while the link is busy; callers merge mouse motion instead of queueing it."""
        return not self._reports.empty()

    def send(self, report: bytes) -> None:
        if not self.is_connected:
            return
        try:
            self._reports.put_nowait(report)
        except queue.Full:
            # A stalled link must not drop key-up reports; drop the link instead.
            self.close("send queue full")

    def close(self, reason: str = "closed") -> None:
        self._close_sockets(self._sockets, reason)

    def _close_sockets(self, sockets: tuple[socket.socket, socket.socket] | None, reason: str) -> None:
        # Threads of an older connection must not close a newer one.
        with self._lock:
            if not self.is_connected or sockets is not self._sockets:
                return
            self.is_connected = False
            reports = self._reports
        for sock in sockets:
            close_channel(sock)
        reports.put(None)
        self._on_disconnect(reason)

    def _read_control(self, sockets: tuple[socket.socket, socket.socket], reports: queue.Queue) -> None:
        control = sockets[0]
        try:
            while message := control.recv(64):
                if message[0] == HIDP_CONTROL_VIRTUAL_CABLE_UNPLUG:
                    self._close_sockets(sockets, "host unplugged virtual cable")
                    return
                reply = get_control_reply(message)
                if reply is not None:
                    control.sendall(reply)
        except OSError:
            pass
        self._close_sockets(sockets, "host closed control channel")

    def _read_interrupt(self, sockets: tuple[socket.socket, socket.socket], reports: queue.Queue) -> None:
        # Output reports (keyboard LEDs) are read and dropped.
        interrupt = sockets[1]
        while True:
            try:
                if not interrupt.recv(64):
                    break
            except TimeoutError:
                continue
            except OSError:
                break
        self._close_sockets(sockets, "host closed interrupt channel")

    def _send_reports(self, sockets: tuple[socket.socket, socket.socket], reports: queue.Queue) -> None:
        while (report := reports.get()) is not None:
            try:
                sockets[1].send(report)
            except OSError as error:
                self._close_sockets(sockets, f"send failed: {error}")
                return
