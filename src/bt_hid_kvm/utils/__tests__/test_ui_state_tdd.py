import pytest

from bt_hid_kvm.utils.ui_state import UiState, load_ui_state, save_ui_state


def test_saved_state_loads_back(tmp_path):
    path = tmp_path / "bt-hid-kvm" / "ui_state.json"
    save_ui_state(path, UiState(is_toggle_mode=True))
    assert load_ui_state(path) == UiState(is_toggle_mode=True)


def test_missing_file_loads_defaults(tmp_path):
    assert load_ui_state(tmp_path / "ui_state.json") == UiState(is_toggle_mode=False)


@pytest.mark.parametrize(
    "content",
    [b"{not json", b"\xff\xfe", b"[]", b"{}", b'{"is_toggle_mode": "yes"}'],
    ids=["broken json", "not utf-8", "list", "missing key", "wrong type"],
)
def test_broken_file_is_deleted_and_loads_defaults(tmp_path, content):
    path = tmp_path / "ui_state.json"
    path.write_bytes(content)
    assert load_ui_state(path) == UiState(is_toggle_mode=False)
    assert not path.exists()
