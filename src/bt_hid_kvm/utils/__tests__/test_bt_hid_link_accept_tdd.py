import threading

from bt_hid_kvm.constants import PSM_CONTROL, PSM_INTERRUPT
from bt_hid_kvm.utils.bt_hid_link import HidLink

HOST = "98:BD:80:A5:22:41"
OTHER_HOST = "E4:17:D8:85:62:81"


class FakeChannel:
    """A host-opened L2CAP socket from bluetoothd; recv blocks until it is shut down."""

    def __init__(self, mac: str, psm: int):
        # Python 3.14 reports L2CAP peers as (bdaddr, psm, cid).
        self._peer = (mac, psm, 0x40)
        self._is_closed = threading.Event()
        self.is_shut_down = False
        self.sent: list[bytes] = []
        self.has_sent = threading.Event()

    def getpeername(self) -> tuple[str, int, int]:
        return self._peer

    def settimeout(self, timeout: float | None) -> None:
        pass

    def setsockopt(self, *args) -> None:
        pass

    def recv(self, size: int) -> bytes:
        self._is_closed.wait()
        return b""

    def send(self, data: bytes) -> int:
        self.sent.append(data)
        self.has_sent.set()
        return len(data)

    def sendall(self, data: bytes) -> None:
        self.send(data)

    def shutdown(self, how: int) -> None:
        self.is_shut_down = True
        self._is_closed.set()

    def close(self) -> None:
        self._is_closed.set()


def get_link() -> tuple[HidLink, list[str]]:
    """A link with no real Bluetooth; returns it with the hosts it reported as connected."""
    accepted: list[str] = []
    link = HidLink(on_disconnect=lambda reason: None, on_accept=accepted.append)
    return link, accepted


def test_link_comes_up_when_host_opens_control_then_interrupt():
    link, accepted = get_link()
    control, interrupt = FakeChannel(HOST, PSM_CONTROL), FakeChannel(HOST, PSM_INTERRUPT)
    link.accept(control)
    assert not link.is_connected
    link.accept(interrupt)
    assert link.is_connected
    assert accepted == [HOST]
    link.send(b"report")
    assert interrupt.has_sent.wait(1)
    assert interrupt.sent == [b"report"]
    link.close()


def test_interrupt_without_control_is_dropped():
    link, accepted = get_link()
    interrupt = FakeChannel(HOST, PSM_INTERRUPT)
    link.accept(interrupt)
    assert not link.is_connected
    assert interrupt.is_shut_down
    assert accepted == []


def test_interrupt_from_another_host_drops_both_channels():
    link, accepted = get_link()
    control, interrupt = FakeChannel(HOST, PSM_CONTROL), FakeChannel(OTHER_HOST, PSM_INTERRUPT)
    link.accept(control)
    link.accept(interrupt)
    assert not link.is_connected
    assert control.is_shut_down and interrupt.is_shut_down
    assert accepted == []


def test_host_channels_are_dropped_while_a_link_is_up():
    link, accepted = get_link()
    first = FakeChannel(HOST, PSM_CONTROL), FakeChannel(HOST, PSM_INTERRUPT)
    second = FakeChannel(OTHER_HOST, PSM_CONTROL), FakeChannel(OTHER_HOST, PSM_INTERRUPT)
    for channel in (*first, *second):
        link.accept(channel)
    assert all(channel.is_shut_down for channel in second)
    assert not any(channel.is_shut_down for channel in first)
    assert link.is_connected
    assert accepted == [HOST]
    link.close()
