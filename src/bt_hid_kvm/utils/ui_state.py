import json
from pathlib import Path
from typing import NamedTuple


class UiState(NamedTuple):
    is_toggle_mode: bool = False


def load_ui_state(path: Path) -> UiState:
    try:
        text = path.read_bytes()
    except OSError:
        # Missing or unreadable: start from the defaults.
        return UiState()
    try:
        is_toggle_mode = json.loads(text)["is_toggle_mode"]
    except (ValueError, TypeError, KeyError):
        is_toggle_mode = None
    if not isinstance(is_toggle_mode, bool):
        # Broken format: delete it, so the next save starts clean.
        try:
            path.unlink()
        except OSError:
            pass
        return UiState()
    return UiState(is_toggle_mode=is_toggle_mode)


def save_ui_state(path: Path, state: UiState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write then rename, so a crash mid-write cannot leave a broken file.
    temp_path = path.with_name(path.name + ".tmp")
    temp_path.write_text(json.dumps(state._asdict()), encoding="utf-8")
    temp_path.replace(path)
