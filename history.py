"""Folder history: which folders have been opened, persisted across restarts."""

import json
from pathlib import Path

SESSION_PATH = Path(__file__).parent / ".last_session.json"
HISTORY_LIMIT = 10


def normalize_folder(path: str) -> str:
    """Canonicalise a folder path so the same folder can't appear twice."""
    return str(Path(path).resolve())


def add_to_history(history: list[str], folder: str,
                   limit: int = HISTORY_LIMIT) -> list[str]:
    """Return history with `folder` moved/inserted at the front, deduped and capped."""
    norm = normalize_folder(folder)
    result = [norm]
    result.extend(p for p in history if normalize_folder(p) != norm)
    return result[:limit]


def prune_history(history: list[str]) -> list[str]:
    """Normalise, drop duplicates, and drop entries that aren't existing dirs."""
    seen: set[str] = set()
    result: list[str] = []
    for p in history:
        norm = normalize_folder(p)
        if norm in seen:
            continue
        seen.add(norm)
        if Path(norm).is_dir():
            result.append(norm)
    return result


def load_history(session_path: Path = SESSION_PATH) -> list[str]:
    """Read the persisted folder history; return [] if missing/unreadable/corrupt."""
    try:
        data = json.loads(Path(session_path).read_text())
    except (OSError, ValueError):
        return []
    hist = data.get("folder_history", []) if isinstance(data, dict) else []
    return [p for p in hist if isinstance(p, str)]


def save_history(history: list[str], session_path: Path = SESSION_PATH) -> None:
    """Persist the folder history as JSON; silently no-op on write errors."""
    try:
        Path(session_path).write_text(
            json.dumps({"folder_history": history}, indent=2))
    except OSError:
        pass
