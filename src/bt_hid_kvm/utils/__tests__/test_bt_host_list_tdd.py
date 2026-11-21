import pytest

from bt_hid_kvm.utils.bt_pairing import Host, get_hosts_from_objects, get_mac_from_text


def get_device(mac: str, alias: str, device_class: int | None, is_paired: bool, adapter: str = "/org/bluez/hci0"):
    """One GetManagedObjects() entry for a BlueZ device."""
    properties = {"Address": mac, "Alias": alias, "Paired": is_paired, "Adapter": adapter}
    if device_class is not None:
        properties["Class"] = device_class
    return f"{adapter}/dev_{mac.replace(':', '_')}", {"org.bluez.Device1": properties}


def test_host_list_keeps_only_computers():
    objects = dict(
        [
            ("/org/bluez/hci0", {"org.bluez.Adapter1": {"Address": "E8:BF:B8:5A:FB:AD"}}),
            get_device("98:BD:80:A5:22:41", "scott-288V", 0x5A010C, True),  # major class 0x01: computer
            get_device("CC:98:8B:F5:28:5F", "WH-1000XM3", 0x240404, True),  # major class 0x04: audio
            get_device("53:E4:00:04:33:96", "53-E4-00-04-33-96", None, False),  # LE only, no class
        ]
    )
    assert get_hosts_from_objects(objects) == [Host("98:BD:80:A5:22:41", "scott-288V", True)]


def test_host_list_skips_other_adapters():
    # Pairing and connecting only use hci0.
    objects = dict([get_device("11:22:33:44:55:66", "other-pc", 0x5A010C, True, adapter="/org/bluez/hci1")])
    assert get_hosts_from_objects(objects) == []


def test_host_list_puts_paired_hosts_first_then_sorts_by_name():
    objects = dict(
        [
            get_device("11:11:11:11:11:11", "b-pc", 0x5A010C, False),
            get_device("22:22:22:22:22:22", "z-pc", 0x5A010C, True),
            get_device("33:33:33:33:33:33", "a-pc", 0x5A010C, False),
        ]
    )
    assert [host.name for host in get_hosts_from_objects(objects)] == ["z-pc", "a-pc", "b-pc"]


@pytest.mark.parametrize(
    ("text", "mac"),
    [
        ("scott-288V (98:BD:80:A5:22:41) 已配對", "98:BD:80:A5:22:41"),
        (" 98:bd:80:a5:22:41 ", "98:BD:80:A5:22:41"),
    ],
)
def test_target_text_gives_uppercase_mac(text, mac):
    assert get_mac_from_text(text) == mac


@pytest.mark.parametrize("text", ["", "scott-288V", "98:BD:80:A5:22"])
def test_target_text_without_mac_gives_none(text):
    assert get_mac_from_text(text) is None
