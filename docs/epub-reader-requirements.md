# EPUB Reader — Desktop App Requirements

## Overview

A desktop application built in Python using **Flet 0.80.x** (the 1.0 Beta release) that lets the user browse a folder of EPUB files and read them inside the app with a scrollable preview.

---

## Tech Stack

| Concern | Choice |
|---|---|
| UI framework | `flet==0.80.x` (latest stable, currently 0.80.5) |
| EPUB parsing | `ebooklib` |
| HTML stripping | stdlib `re` only — no extra deps |
| Python version | 3.10+ (Flet requirement) |

**Install command:**
```bash
pip install "flet[desktop]" ebooklib
```

> On Linux, `FilePicker` also requires `zenity` (`sudo apt install zenity`).

---

## Flet 0.80 API — Critical Notes

Flet 0.80 is a **breaking rewrite** from 0.28.x. Claude Code must use the new API:

- Entry point: `ft.run(main)` — NOT `ft.app(target=main)`
- Enums use **uppercase**: `ft.Colors.GREY_900`, `ft.Icons.FOLDER_OPEN`, `ft.FontWeight.BOLD`, `ft.ThemeMode.DARK`
- `FilePicker` is a **Service** — add it to `page.overlay`, not to the layout
- `get_directory_path()` is **async** and returns `str | None` directly (no callback needed)
- Event handlers can be `async def` and use `await`
- `ft.MainAxisAlignment`, `ft.CrossAxisAlignment`, `ft.ScrollMode` are all uppercase enums

**Minimal working skeleton:**
```python
import flet as ft

async def main(page: ft.Page):
    page.title = "My App"
    file_picker = ft.FilePicker()
    page.overlay.append(file_picker)

    async def pick(e):
        path = await file_picker.get_directory_path(dialog_title="Select folder")
        if path:
            print(path)

    page.add(ft.ElevatedButton("Open", on_click=pick))

ft.run(main)
```

---

## Application Layout

Two-panel layout, side by side, filling the window:

```
┌─────────────────────────────────────────────────────────────┐
│  SIDEBAR (fixed 280px)        │  READER PANEL (expand)      │
│                               │                             │
│  [📚 EPUB Reader  title]      │  Book Title                 │
│  [Open Folder  button]        │  ─────────────────          │
│  /path/to/folder  (label)     │                             │
│  ──────────────────────────   │  Chapter text scrolls       │
│                               │  here …                     │
│  📖 Book One          120 KB  │                             │
│  📖 Book Two           88 KB  │                             │
│  📖 Book Three        204 KB  │                             │
│  …                            │                             │
└─────────────────────────────────────────────────────────────┘
```

### Sidebar
- Background: `ft.Colors.GREY_900`
- Fixed `width=280`
- Top section (padded container):
  - App title text: `"📚 EPUB Reader"`, size 20, bold
  - `ElevatedButton("Open Folder", icon=ft.Icons.FOLDER_OPEN)` — triggers folder picker
  - Small label showing the selected folder path (grey, truncated)
- Divider
- Scrollable `ListView` of EPUB files — each entry is a `ListTile`:
  - Leading icon: `ft.Icons.MENU_BOOK`
  - Title: filename without extension
  - Subtitle: file size in KB
  - `on_click` loads the book into the reader panel
  - Highlight selected item

### Reader Panel
- `expand=True`, comfortable padding (`24px` horizontal, `16px` vertical)
- Book title at top, bold, size 20
- Thin `Divider`
- Scrollable `ListView` or `Column` with `scroll=ft.ScrollMode.AUTO` containing the book text
- Each chapter rendered as a `ft.Text` block, `size=15`, `selectable=True`
- A subtle `Divider` between chapters
- Default state (no book selected): centred placeholder text — `"Select a book from the sidebar"`

---

## EPUB Parsing Logic

```python
import ebooklib
from ebooklib import epub
import re

def html_to_text(raw: str) -> str:
    # 1. Drop <script> and <style> blocks
    raw = re.sub(r"<(script|style)[^>]*>.*?</(script|style)>", "", raw,
                 flags=re.DOTALL | re.IGNORECASE)
    # 2. Convert block elements to newlines
    raw = re.sub(r"<(br|p|h[1-6]|li|tr|div)[^>]*>", "\n", raw, flags=re.IGNORECASE)
    raw = re.sub(r"</(p|h[1-6]|li|tr|div)>", "\n", raw, flags=re.IGNORECASE)
    # 3. Strip remaining tags
    raw = re.sub(r"<[^>]+>", "", raw)
    # 4. Collapse excess blank lines
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    # 5. Decode common HTML entities
    for ent, ch in [("&amp;","&"),("&lt;","<"),("&gt;",">"),
                    ("&nbsp;"," "),("&quot;",'"'),("&#39;","'")]:
        raw = raw.replace(ent, ch)
    return raw.strip()

def epub_chapters(path: str) -> list[tuple[str, str]]:
    """Returns [(chapter_title, plain_text), ...]"""
    book = epub.read_epub(path, options={"ignore_ncx": True})
    chapters = []
    for item in book.get_items():
        if item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        raw_html = item.get_content().decode("utf-8", errors="ignore")
        text = html_to_text(raw_html)
        if len(text) < 30:          # skip near-empty pages/nav docs
            continue
        # Extract chapter title from first heading if present
        m = re.search(r"<h[1-3][^>]*>(.*?)</h[1-3]>",
                      raw_html, re.IGNORECASE | re.DOTALL)
        title = re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else item.get_name()
        chapters.append((title, text))
    return chapters
```

---

## App Behaviour

### Folder selection
1. User clicks **Open Folder**
2. `await file_picker.get_directory_path()` opens the OS folder dialog
3. On confirmation, scan the folder with `Path(folder).glob("*.epub")` (sorted alphabetically)
4. Populate the sidebar list; clear any currently displayed book
5. If no epubs found, show a "No EPUB files found" message in the list area

### Book loading
1. User clicks a list tile
2. Highlight the selected tile
3. Call `epub_chapters(path)` — may be slow for large books; consider running in a thread (`asyncio.to_thread`) and showing a `ProgressRing` while loading
4. Build reader panel: title + one `ft.Text` per chapter, separated by dividers
5. Scroll reader panel back to top

### Error handling
- Wrap `epub.read_epub` in `try/except` and display a red error text in the reader panel if parsing fails
- If the folder dialog is cancelled, do nothing

---

## Project File Structure

```
epub_reader/
├── main.py          # all app code (single-file is fine to start)
└── requirements.txt
```

**requirements.txt:**
```
flet[desktop]>=0.80.0
ebooklib
```

---

## Running the App

```bash
python main.py
# or via flet CLI:
flet run main.py
```

---

## Out of Scope (future ideas)
- Chapter navigation sidebar / TOC
- Font size controls
- Light/dark mode toggle
- Search within book
- Remember last opened folder / book
- Rendered HTML (would need `flet-webview` extension)
