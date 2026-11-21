import os
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
    ADAPTER_PATH,
    CONNECT_TIMEOUT,
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
    """BlueZ Profile1 object; it only exists to publish the HID SDP record."""

    @dbus.service.method("org.bluez.Profile1", in_signature="", out_signature="")
    def Release(self):
        pass

    @dbus.service.method("org.bluez.Profile1", in_signature="oha{sv}", out_signature="")
    def NewConnection(self, device, fd, properties):
        # This device always connects out, so incoming sockets are dropped.
        os.close(fd.take())

    @dbus.service.method("org.bluez.Profile1", in_signature="o", out_signature="")
    def RequestDisconnection(self, device):
        pass


def register_hid_profile() -> dbus.SystemBus:
    dbus.mainloop.glib.threads_init()
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    HidProfile(bus, PROFILE_PATH)
    threading.Thread(target=GLib.MainLoop().run, daemon=True).start()
    manager = dbus.Interface(bus.get_object("org.bluez", "/org/bluez"), "org.bluez.ProfileManager1")
    manager.RegisterProfile(
        PROFILE_PATH,
        PROFILE_UUID,
        {
            "ServiceRecord": SDP_RECORD_XML,
            "Role": "server",
            "RequireAuthentication": True,
            "RequireAuthorization": False,
            "AutoConnect": False,
        },
    )
    return bus


def get_device_path(mac: str) -> str:
    return f"{ADAPTER_PATH}/dev_{mac.replace(':', '_')}"


def get_is_paired(bus: dbus.SystemBus, mac: str) -> bool:
    path = get_device_path(mac)
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


class HidLink:
    """Device-initiated Bluetooth HID connection (control PSM 17 + interrupt PSM 19)."""

    def __init__(self, on_disconnect: Callable[[str], None]):
        self._on_disconnect = on_disconnect
        self._reports: queue.Queue[bytes | None] = queue.Queue(maxsize=256)
        self._sockets: tuple[socket.socket, socket.socket] | None = None
        self._lock = threading.Lock()
        self.is_connected = False

    def connect(self, mac: str) -> None:
        control = connect_l2cap(mac, PSM_CONTROL)
        try:
            interrupt = connect_l2cap(mac, PSM_INTERRUPT)
        except OSError:
            control.close()
            raise
        control.settimeout(None)
        interrupt.settimeout(SEND_TIMEOUT)
        interrupt.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, INTERRUPT_SNDBUF)
        sockets = (control, interrupt)
        reports: queue.Queue[bytes | None] = queue.Queue(maxsize=256)
        with self._lock:
            self._sockets = sockets
            self._reports = reports
            self.is_connected = True
        for target in (self._read_control, self._read_interrupt, self._send_reports):
            threading.Thread(target=target, args=(sockets, reports), daemon=True).start()

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
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()
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
