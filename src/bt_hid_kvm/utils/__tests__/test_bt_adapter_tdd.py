from bt_hid_kvm.utils.bt_hid_link import get_adapter_path_from_objects


def get_adapter(index: int) -> tuple[str, dict]:
    """One GetManagedObjects() entry for a BlueZ adapter."""
    return f"/org/bluez/hci{index}", {"org.bluez.Adapter1": {"Address": f"00:00:00:00:00:0{index}"}}


def test_first_adapter_is_picked_whatever_the_listing_order():
    objects = dict([get_adapter(10), get_adapter(2), get_adapter(1)])
    assert get_adapter_path_from_objects(objects) == "/org/bluez/hci1"


def test_no_adapter_gives_none():
    objects = {"/org/bluez": {"org.bluez.AgentManager1": {}}}
    assert get_adapter_path_from_objects(objects) is None
