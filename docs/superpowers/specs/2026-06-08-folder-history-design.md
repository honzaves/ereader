# Design: Default-directory button + clickable folder history

**Date:** 2026-06-08
**Component:** `main.py` (EPUB reader sidebar / folder loading)

## Summary

Two related features for the sidebar:

1. **"Open Default" button** — a one-click jump to the folder configured in
   `config.toml`'s existing `starting_folder` setting.
2. **Folder history** — the app remembers the folders you open (persisted in the
   project folder) and exposes them as a clickable "Recent:" dropdown. On
   restart it reopens the most recently opened folder.

Both build on the existing `_load_folder` / `_pick_folder` flow and the existing
`starting_folder` config key. No new user-facing config keys are introduced.

## Decisions

- **"Open Default" target:** the configured `starting_folder`. No new config key.
- **Button state when `starting_folder` is empty or missing:** visible but
  **disabled (greyed out)**.
- **Startup precedence:** **last-opened wins.** Fall back to `starting_folder`
  only when there is no valid remembered folder (e.g. first run).
- **History storage:** a **separate app-managed state file** in the project
  folder, distinct from the hand-edited `config.toml`.
- **History UI:** a **compact dropdown** (`QComboBox`), most-recent first.
- **History size:** **max 10 unique folders.** Re-opening a folder already in the
  list moves it to the front.
- **Entry label:** the **folder name**, with the **full path as a tooltip**.
- **Stale entries:** **pruned at startup** (and as a safety net, when a click
  fails — see Error Handling).

## State file

A JSON file `.last_session.json` next to `config.toml` (i.e. in the project
folder, alongside `main.py`):

```json
{ "folder_history": ["/most/recent/folder", "/next/folder", "..."] }
```

- Order is **most-recent-first**; `folder_history[0]` is the "last opened" folder.
- **JSON, not TOML:** the standard library's `tomllib` is read-only, so writing
  TOML would require a dependency or hand-rolled serialization. `json` reads and
  writes from the standard library, and a JSON object leaves room to remember
  more session state later without a format change. This is app-managed state,
  not hand-edited config, so a second format alongside `config.toml` is
  appropriate.
- If a future `git init` happens, this file is runtime state and should **not**
  be committed (add to `.gitignore` at that point).

### Helpers (module-level)

- `load_history() -> list[str]` — read and parse the file; return `[]` if the
  file is missing, unreadable, or corrupt (never raises).
- `save_history(history: list[str]) -> None` — write the list back as JSON.

The in-memory copy lives on the window as `self._history: list[str]`.

### Path normalization (dedup correctness)

Before comparing or storing a path, **normalize it** (`Path(p).resolve()` /
`os.path.normpath`). Without this, `/Users/jan/Books`, `/Users/jan/Books/`, and a
symlinked equivalent are the same folder but distinct strings, which would defeat
the "no duplicates / move-to-front" requirement (macOS paths are also
case-insensitive). All history entries are stored normalized, and dedup compares
normalized paths.

## Behavior

### Startup resolution (replaces the current `__init__` auto-open block)

Current code:

```python
if cfg.starting_folder and Path(cfg.starting_folder).is_dir():
    self._load_folder(cfg.starting_folder)
```

New order:

1. Load history; **prune any folders that no longer exist**; save the pruned list
   back to the state file.
2. If history is non-empty → open `history[0]`.
3. Else if `starting_folder` is a valid directory → open it.
4. Else → open nothing (the current "Select a book from the sidebar" state).

### Recording an opened folder

In `_load_folder`, after a directory has been **successfully listed** (i.e. not
the error path below): normalize the path, remove any existing equal entry,
insert it at the front of `self._history`, truncate to 10, `save_history(...)`,
and refresh the dropdown. This single hook covers every way a folder gets
opened — the "Open Folder" dialog, the "Open Default" button, a history-dropdown
click, and the startup auto-open.

A folder that exists but errors on open (e.g. permission denied) is **not**
recorded.

## UI changes (sidebar)

- **"Open Default" button:** added next to "Open Folder" in a side-by-side row.
  Same styling as the existing button. Enabled only when `starting_folder` is a
  valid directory; otherwise `setEnabled(False)` (greyed out). Click →
  `_load_folder(self._cfg.starting_folder)`.
- **"Recent:" dropdown (`QComboBox`)**, placed below the buttons and above the
  folder label:
  - Each entry's display text is the folder name (`Path(p).name`), tooltip is the
    full path, and the full path is stored as item data.
  - Most-recent first; the currently-open folder is shown as the selected entry.
  - When history is empty, the dropdown is disabled with placeholder text
    ("No recent folders").
  - Selecting an entry uses the `activated` signal (fires on **user action
    only**, so reselecting/rebuilding does not re-trigger a load). The handler
    reads the item's path data and calls `_load_folder(path)`.
  - The dropdown is rebuilt (cleared and repopulated) with its signals blocked
    after each open, so programmatic updates never trigger `activated`.

## Error handling

- **Corrupt/unreadable state file** → treated as empty history, silently. The app
  always starts.
- **Stale folders at startup** → pruned (see Startup resolution).
- **A history/default target deleted or unmounted mid-session** → the dropdown
  may still list it. The current `_load_folder` only catches `PermissionError`
  around `iterdir()`; opening a now-missing path would otherwise raise
  `FileNotFoundError` / `NotADirectoryError` and crash. The history feature makes
  this a live path (it increases how often a possibly-stale folder is opened), so
  `_load_folder` must handle a missing / non-directory target gracefully: guard
  with `is_dir()` (or broaden the `except` to `OSError`), show a message in the
  book list, and drop the dead entry from history + refresh the dropdown. This
  extends the user's "drop on startup" choice to the click path as a safety net.

## Out of scope (YAGNI)

- No per-folder timestamps, pinning/favorites, or manual "remove from history" UI.
- No recent-files (book-level) history — folders only.
- Same-name folders look identical in the dropdown (full path is in the tooltip).
  This tradeoff was accepted when choosing "folder name + path tooltip."

## Notes / logistics

- This project is **not currently a git repository**, so this spec is saved but
  not committed. Run `git init` if you want it (and future work) versioned.
