from bt_hid_kvm.components import main_window
from bt_hid_kvm.components.main_window import MainWindow
from bt_hid_kvm.utils.bt_pairing import Host

PAIRED_MAC = "98:BD:80:A5:22:41"
UNPAIRED_MAC = "11:22:33:44:55:66"


class FakeWidget:
    def __init__(self):
        self.options: dict = {}

    def configure(self, **options) -> None:
        self.options.update(options)


class FakeVar:
    def __init__(self, text: str):
        self._text = text

    def get(self) -> str:
        return self._text

    def set(self, text: str) -> None:
        self._text = text


def get_pair_controls(target_text: str, monkeypatch) -> tuple[str | None, str | None]:
    """Refresh the host list with this target; return the pair button text and the hint text."""
    hosts = [Host(PAIRED_MAC, "SCOTT-288V", True), Host(UNPAIRED_MAC, "OTHER-PC", False)]
    monkeypatch.setattr(main_window, "get_known_hosts", lambda bus, adapter_path: hosts)
    # BlueZ answers paired only for PAIRED_MAC.
    monkeypatch.setattr(main_window, "get_is_paired", lambda bus, adapter_path, mac: mac == PAIRED_MAC)
    window = object.__new__(MainWindow)
    window._bus = None
    window._adapter_path = "/org/bluez/hci0"
    window._target = FakeVar(target_text)
    window._target_box = FakeWidget()
    window._pair_button = FakeWidget()
    window._pair_hint = FakeWidget()
    window._refresh_hosts()
    return window._pair_button.options.get("text"), window._pair_hint.options.get("text")


def test_paired_target_shows_repair_button_and_hint(monkeypatch):
    button_text, hint_text = get_pair_controls(f"SCOTT-288V ({PAIRED_MAC}) 已配對", monkeypatch)
    assert button_text == "重新配對"
    assert hint_text == "已配對，不用再按「重新配對」；按了要重新核對配對碼"


def test_unpaired_or_unknown_target_shows_pair_button_without_hint(monkeypatch):
    assert get_pair_controls(f"OTHER-PC ({UNPAIRED_MAC})", monkeypatch) == ("配對", "")
    assert get_pair_controls("not a mac", monkeypatch) == ("配對", "")
