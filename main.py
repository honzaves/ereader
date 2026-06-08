import hashlib
import json
import re
import sys
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

import ebooklib
from ebooklib import epub
from PySide6.QtCore import QSize, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QColor
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QStyle,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


# ── Config ────────────────────────────────────────────────────────────────────

SIDEBAR_WIDTH = 280

CONFIG_PATH = Path(__file__).parent / "config.toml"

_CONFIG_TEMPLATE = """\
# EPUB Reader settings — edit and restart the app to apply changes.

font_family = ""        # system font name, e.g. "Georgia". Leave empty for default.
font_size = 15          # body text size in points
sidebar_bg   = "#1a1a1e"  # sidebar background colour (hex)
sidebar_text = "#e0e0e0"  # sidebar text colour (hex)
reader_bg    = "#121212"  # status/loading panel background colour (hex)
book_bg      = "#f8f4e8"  # book page background colour (hex)
text_color   = "#1a1a1a"  # book body text colour (hex)
starting_folder = ""    # auto-open this folder on startup (full path)
"""


@dataclass
class Config:
    font_family: str = ""
    font_size: int = 15
    sidebar_bg: str = "#1a1a1e"
    sidebar_text: str = "#e0e0e0"
    reader_bg: str = "#121212"
    book_bg: str = "#f8f4e8"
    text_color: str = "#1a1a1a"
    starting_folder: str = ""


def load_config() -> Config:
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(_CONFIG_TEMPLATE)
        return Config()
    with CONFIG_PATH.open("rb") as f:
        data = tomllib.load(f)
    return Config(
        font_family=data.get("font_family", ""),
        font_size=int(data.get("font_size", 15)),
        sidebar_bg=data.get("sidebar_bg", "#1a1a1e"),
        sidebar_text=data.get("sidebar_text", "#e0e0e0"),
        reader_bg=data.get("reader_bg", "#121212"),
        book_bg=data.get("book_bg", "#f8f4e8"),
        text_color=data.get("text_color", "#1a1a1a"),
        starting_folder=data.get("starting_folder", ""),
    )


# ── Session state (folder history) ──────────────────────────────────────────

SESSION_PATH = Path(__file__).parent / ".last_session.json"
HISTORY_LIMIT = 10


def _normalize_folder(path: str) -> str:
    """Canonicalise a folder path so the same folder can't appear twice."""
    return str(Path(path).resolve())


def add_to_history(history: list[str], folder: str,
                   limit: int = HISTORY_LIMIT) -> list[str]:
    """Return history with `folder` moved/inserted at the front, deduped and capped."""
    norm = _normalize_folder(folder)
    result = [norm]
    result.extend(p for p in history if _normalize_folder(p) != norm)
    return result[:limit]


def prune_history(history: list[str]) -> list[str]:
    """Normalise, drop duplicates, and drop entries that aren't existing dirs."""
    seen: set[str] = set()
    result: list[str] = []
    for p in history:
        norm = _normalize_folder(p)
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


# ── Book metadata ─────────────────────────────────────────────────────────────

@dataclass
class BookMeta:
    path: Path
    title: str
    author: str
    sort_key: tuple[str, str]


def _read_epub_meta(path: Path) -> BookMeta:
    try:
        book = epub.read_epub(str(path), options={"ignore_ncx": True})
        raw_titles = book.get_metadata("DC", "title")
        raw_creators = book.get_metadata("DC", "creator")
        title = raw_titles[0][0].strip() if raw_titles else ""
        author = raw_creators[0][0].strip() if raw_creators else ""
    except Exception:
        title, author = "", ""
    display_title = title or path.stem  # fall back to filename when no title
    sort_author = author.lower() if author else "\xff"  # no-author sorts to end
    # Sort by the title actually shown in the list; author breaks ties.
    return BookMeta(path=path, title=display_title, author=author,
                    sort_key=(display_title.lower(), sort_author))


# ── TOC ───────────────────────────────────────────────────────────────────────

@dataclass
class TocEntry:
    title: str
    anchor: str                        # in-page "#id", empty if unresolvable
    children: list["TocEntry"] = field(default_factory=list)


def _resolve_toc_href(href: str, doc_id_map: dict[str, str]) -> str:
    if not href:
        return ""
    if href.startswith("#"):
        return href
    path_part, _, fragment = href.partition("#")
    canonical = _resolve_epub_href(path_part, "")  # TOC hrefs are root-relative
    if fragment:
        return f"#{fragment}"
    sid = doc_id_map.get(canonical, "")
    return f"#{sid}" if sid else ""


def _extract_toc(items, doc_id_map: dict[str, str]) -> list[TocEntry]:
    result = []
    for item in items:
        if isinstance(item, tuple):
            section, children = item
            title = getattr(section, "title", "") or ""
            href = getattr(section, "href", "") or ""
            anchor = _resolve_toc_href(href, doc_id_map)
            result.append(TocEntry(
                title=title,
                anchor=anchor,
                children=_extract_toc(children, doc_id_map),
            ))
        else:
            title = getattr(item, "title", "") or ""
            href = getattr(item, "href", "") or ""
            result.append(TocEntry(
                title=title,
                anchor=_resolve_toc_href(href, doc_id_map),
            ))
    return result


# ── EPUB → HTML ───────────────────────────────────────────────────────────────

def _resolve_epub_href(src: str, doc_name: str) -> str:
    src = unquote(src)
    parts: list[str] = []
    for part in (Path(doc_name).parent / src).as_posix().split("/"):
        if part == "..":
            if parts:
                parts.pop()
        elif part not in (".", ""):
            parts.append(part)
    return "/".join(parts)


def build_book_html(path: str, img_dir: Path, cfg: Config) -> tuple[str, list[TocEntry]]:
    book = epub.read_epub(path, options={"ignore_ncx": True})

    img_map: dict[str, str] = {}
    img_cache: dict[str, str] = {}
    for item in book.get_items():
        if item.get_type() != ebooklib.ITEM_IMAGE:
            continue
        data = item.get_content()
        if not data:
            continue
        key = hashlib.md5(data).hexdigest()
        if key not in img_cache:
            ext = (item.media_type or "image/jpeg").split("/")[-1].replace("jpeg", "jpg")
            (img_dir / f"{key}.{ext}").write_bytes(data)
            img_cache[key] = f"img/{key}.{ext}"
        img_map[item.get_name()] = img_cache[key]

    css_parts: list[str] = []
    for item in book.get_items():
        if item.get_type() != ebooklib.ITEM_STYLE:
            continue
        css_text = item.get_content().decode("utf-8", errors="ignore")
        doc_name = item.get_name()

        def rewrite_css_url(m, dn=doc_name):
            url = m.group(1).strip("'\" ")
            if url.startswith(("data:", "http", "file:")):
                return m.group(0)
            rel = img_map.get(_resolve_epub_href(url, dn))
            return f"url('{rel}')" if rel else m.group(0)

        css_parts.append(re.sub(r"url\(([^)]+)\)", rewrite_css_url, css_text))

    # Build a map from canonical epub href → section id so cross-doc links resolve.
    spine_items = []
    doc_id_map: dict[str, str] = {}
    for i, (item_id, _) in enumerate(book.spine):
        item = book.get_item_with_id(item_id)
        if item is None or item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        section_id = f"epub-s{i}"
        doc_id_map[item.get_name()] = section_id
        spine_items.append((item, section_id))

    body_parts: list[str] = []
    for item, section_id in spine_items:
        raw_html = item.get_content().decode("utf-8", errors="ignore")
        doc_name = item.get_name()

        body_m = re.search(r"<body[^>]*>(.*?)</body>", raw_html,
                           re.IGNORECASE | re.DOTALL)
        body_html = body_m.group(1) if body_m else raw_html

        def rewrite_img_src(m, dn=doc_name):
            src = m.group(1)
            if src.startswith(("data:", "http", "file:")):
                return m.group(0)
            rel = img_map.get(_resolve_epub_href(src, dn))
            return f'src="{rel}"' if rel else m.group(0)

        def rewrite_href(m, dn=doc_name):
            href = m.group(1)
            if href.startswith(("#", "http", "mailto:", "data:", "file:")):
                return m.group(0)
            path_part, _, fragment = href.partition("#")
            if path_part:
                canonical = _resolve_epub_href(path_part, dn)
                sid = doc_id_map.get(canonical, "")
            else:
                sid = doc_id_map.get(dn, "")
            if fragment:
                return f'href="#{fragment}"'
            if sid:
                return f'href="#{sid}"'
            return m.group(0)

        body_html = re.sub(r'src=["\']([^"\']+)["\']', rewrite_img_src,
                           body_html, flags=re.IGNORECASE)
        body_html = re.sub(r'href=["\']([^"\']+)["\']', rewrite_href,
                           body_html, flags=re.IGNORECASE)
        body_parts.append(f'<section class="epub-ch" id="{section_id}">{body_html}</section>')

    font_css = f"font-family: {cfg.font_family};" if cfg.font_family else ""
    default_css = f"""
        * {{ box-sizing: border-box; }}
        html, body {{
            background-color: {cfg.book_bg};
            color: {cfg.text_color};
            font-size: {cfg.font_size}px;
            {font_css}
            margin: 0; padding: 0;
        }}
        body {{
            max-width: 800px;
            margin: 0 auto;
            padding: 24px;
            line-height: 1.6;
        }}
        img {{ max-width: 100%; height: auto; display: block; margin: 1em auto; }}
        .epub-ch {{
            margin-bottom: 2em;
            padding-bottom: 2em;
            border-bottom: 1px solid #333;
        }}
        .epub-ch:last-child {{ border-bottom: none; margin-bottom: 0; }}
    """
    book_css = "".join(f"<style>{css}</style>" for css in css_parts)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>{default_css}</style>
{book_css}
</head>
<body>{"".join(body_parts)}</body>
</html>"""

    toc = _extract_toc(book.toc, doc_id_map)
    return html, toc


def _status_html(body: str, cfg: Config) -> str:
    return (
        f'<!DOCTYPE html><html><head><meta charset="utf-8"><style>'
        f'body{{background:{cfg.reader_bg};color:{cfg.sidebar_text};'
        f'display:flex;align-items:center;justify-content:center;'
        f'height:100vh;margin:0;font-family:system-ui;font-size:16px;}}'
        f'</style></head><body>{body}</body></html>'
    )


# ── Background loader ─────────────────────────────────────────────────────────

class BookLoader(QThread):
    loaded = Signal(str, object)   # (html_file_path, toc: list[TocEntry])
    failed = Signal(str)

    def __init__(self, epub_path: str, img_dir: Path, session_dir: Path,
                 cfg: Config, counter: list[int]):
        super().__init__()
        self._epub_path = epub_path
        self._img_dir = img_dir
        self._session_dir = session_dir
        self._cfg = cfg
        self._counter = counter

    def run(self):
        try:
            html, toc = build_book_html(self._epub_path, self._img_dir, self._cfg)
            self._counter[0] += 1
            p = self._session_dir / f"p{self._counter[0]}.html"
            p.write_text(html, encoding="utf-8")
            self.loaded.emit(str(p), toc)
        except Exception as exc:
            self.failed.emit(str(exc))


# ── Main window ───────────────────────────────────────────────────────────────

class ReaderWindow(QMainWindow):
    def __init__(self, cfg: Config):
        super().__init__()
        self._cfg = cfg
        self._loader: BookLoader | None = None
        self._session_dir = Path(tempfile.mkdtemp(prefix="ereader_"))
        self._img_dir = self._session_dir / "img"
        self._img_dir.mkdir()
        self._page_counter = [0]

        # Load folder history and drop folders that no longer exist.
        self._history = prune_history(load_history())
        save_history(self._history)

        self.setWindowTitle("EPUB Reader")
        self.resize(1400, 800)

        self._build_ui()
        self._apply_styles()
        self._refresh_recent_combo()

        # Startup: last-opened wins, then the configured default folder.
        if self._history:
            self._load_folder(self._history[0])
        elif self._has_valid_default():
            self._load_folder(cfg.starting_folder)

    def _build_ui(self):
        cfg = self._cfg

        # ── WebView ───────────────────────────────────────────────────────────
        self._view = QWebEngineView()
        self._view.page().setBackgroundColor(QColor(cfg.book_bg))
        self._show_status("<p>Select a book from the sidebar</p>")

        # ── Sidebar ───────────────────────────────────────────────────────────
        sidebar = QWidget()
        sidebar.setFixedWidth(SIDEBAR_WIDTH)
        sidebar.setObjectName("sidebar")

        title = QLabel("📚 EPUB Reader")
        title.setObjectName("sidebarTitle")

        self._folder_label = QLabel("")
        self._folder_label.setObjectName("folderLabel")
        self._folder_label.setWordWrap(True)

        open_btn = QPushButton("Open Folder")
        open_btn.setObjectName("openBtn")
        open_btn.clicked.connect(self._pick_folder)

        self._default_btn = QPushButton("Open Default")
        self._default_btn.setObjectName("openBtn")
        self._default_btn.clicked.connect(self._open_default_folder)
        self._default_btn.setEnabled(self._has_valid_default())

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addWidget(open_btn)
        btn_row.addWidget(self._default_btn)

        self._recent_combo = QComboBox()
        self._recent_combo.setObjectName("recentCombo")
        self._recent_combo.activated.connect(self._on_recent_selected)

        self._book_list = QListWidget()
        self._book_list.setObjectName("bookList")
        self._book_list.itemClicked.connect(self._on_book_clicked)

        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 12, 12, 12)
        sidebar_layout.setSpacing(8)
        sidebar_layout.addWidget(title)
        sidebar_layout.addLayout(btn_row)
        sidebar_layout.addWidget(self._recent_combo)
        sidebar_layout.addWidget(self._folder_label)
        sidebar_layout.addWidget(self._book_list)

        # ── TOC panel ─────────────────────────────────────────────────────────
        self._toc_panel = QWidget()
        self._toc_panel.setFixedWidth(240)
        self._toc_panel.setObjectName("tocPanel")
        self._toc_panel.setVisible(False)

        toc_header = QLabel("Contents")
        toc_header.setObjectName("tocHeader")

        self._toc_tree = QTreeWidget()
        self._toc_tree.setObjectName("tocTree")
        self._toc_tree.setHeaderHidden(True)
        self._toc_tree.setIndentation(14)
        self._toc_tree.setAnimated(True)
        self._toc_tree.itemClicked.connect(self._on_toc_item_clicked)

        toc_layout = QVBoxLayout(self._toc_panel)
        toc_layout.setContentsMargins(10, 12, 10, 12)
        toc_layout.setSpacing(8)
        toc_layout.addWidget(toc_header)
        toc_layout.addWidget(self._toc_tree)

        # ── Root layout ───────────────────────────────────────────────────────
        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(sidebar)
        root_layout.addWidget(self._toc_panel)
        root_layout.addWidget(self._view, stretch=1)
        self.setCentralWidget(root)

    def _apply_styles(self):
        cfg = self._cfg

        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background-color: {cfg.sidebar_bg};
                color: {cfg.sidebar_text};
            }}
            QWidget#sidebar {{
                background-color: {cfg.sidebar_bg};
                border-right: 1px solid #2a2a2e;
            }}
            QLabel#sidebarTitle {{
                font-size: 18px;
                font-weight: bold;
                color: {cfg.sidebar_text};
                padding: 4px 0;
            }}
            QLabel#folderLabel {{
                font-size: 11px;
                color: #888;
            }}
            QPushButton#openBtn {{
                background-color: #2a2a2e;
                color: {cfg.sidebar_text};
                border: 1px solid #3a3a3e;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 13px;
            }}
            QPushButton#openBtn:hover {{
                background-color: #3a3a3e;
            }}
            QPushButton#openBtn:pressed {{
                background-color: #4a4a4e;
            }}
            QPushButton#openBtn:disabled {{
                background-color: #232327;
                color: #666;
                border-color: #2a2a2e;
            }}
            QComboBox#recentCombo {{
                background-color: #2a2a2e;
                color: {cfg.sidebar_text};
                border: 1px solid #3a3a3e;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 12px;
            }}
            QComboBox#recentCombo:disabled {{
                background-color: #232327;
                color: #666;
            }}
            QComboBox#recentCombo QAbstractItemView {{
                background-color: {cfg.sidebar_bg};
                color: {cfg.sidebar_text};
                selection-background-color: #2d3748;
            }}
            QListWidget#bookList {{
                background-color: {cfg.sidebar_bg};
                border: none;
                font-size: 13px;
                color: {cfg.sidebar_text};
            }}
            QListWidget#bookList::item {{
                /* No padding: it would inset the embedded widget and clip it.
                   Spacing is owned by the item widget's own margins; only the
                   1px border below remains as item chrome (see _ITEM_BORDER). */
                padding: 0px;
                border-bottom: 1px solid #2a2a2e;
            }}
            QListWidget#bookList::item:selected {{
                background-color: #2d3748;
                color: white;
            }}
            QListWidget#bookList::item:hover {{
                background-color: #252530;
            }}
            QWidget#bookItemWidget {{
                background-color: transparent;
            }}
            QLabel#bookItemTitle {{
                background-color: transparent;
                color: {cfg.sidebar_text};
            }}
            QLabel#bookItemAuthor {{
                background-color: transparent;
                color: #999;
            }}
            QWidget#tocPanel {{
                background-color: {cfg.sidebar_bg};
                border-right: 1px solid #2a2a2e;
            }}
            QLabel#tocHeader {{
                font-size: 14px;
                font-weight: bold;
                color: {cfg.sidebar_text};
                padding: 2px 0 6px 0;
                border-bottom: 1px solid #2a2a2e;
            }}
            QTreeWidget#tocTree {{
                background-color: {cfg.sidebar_bg};
                color: {cfg.sidebar_text};
                border: none;
                font-size: 12px;
            }}
            QTreeWidget#tocTree::item {{
                padding: 4px 2px;
                border-radius: 3px;
            }}
            QTreeWidget#tocTree::item:selected {{
                background-color: #2d3748;
                color: white;
            }}
            QTreeWidget#tocTree::item:hover {{
                background-color: #252530;
            }}
            QTreeWidget#tocTree::branch {{
                background-color: {cfg.sidebar_bg};
            }}
            QTreeWidget#tocTree::branch:has-children:closed {{
                image: none;
                border-image: none;
                color: {cfg.sidebar_text};
            }}
        """)

    # ── Folder loading ────────────────────────────────────────────────────────

    # Font sizes (px) are the single source of truth for both rendering and
    # height measurement — keep them off the stylesheet so the two can't drift.
    _TITLE_PX = 13
    _AUTHOR_PX = 11
    _ITEM_BORDER = 1   # bookList ::item border-bottom; insets the widget by 1px

    def _book_item_width(self) -> int:
        """Usable width for an item widget inside the fixed-width sidebar."""
        list_w = SIDEBAR_WIDTH - 24       # sidebar layout margins (12 + 12)
        scrollbar = self._book_list.style().pixelMetric(
            QStyle.PixelMetric.PM_ScrollBarExtent)
        return list_w - scrollbar         # bias narrower → wraps earlier → never clips

    def _make_book_widget(self, title: str, author: str, width: int) -> tuple[QWidget, QSize]:
        h_margin, v_margin, spacing = 6, 8, 2
        inner = width - 2 * h_margin

        widget = QWidget()
        widget.setObjectName("bookItemWidget")
        widget.setFixedWidth(width)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(h_margin, v_margin, h_margin, v_margin)
        layout.setSpacing(spacing)

        title_lbl = QLabel(title)
        title_lbl.setObjectName("bookItemTitle")
        title_lbl.setWordWrap(True)
        tf = title_lbl.font()
        tf.setPixelSize(self._TITLE_PX)
        title_lbl.setFont(tf)
        layout.addWidget(title_lbl)

        total_h = 2 * v_margin + title_lbl.heightForWidth(inner)

        if author:
            author_lbl = QLabel(author)
            author_lbl.setObjectName("bookItemAuthor")
            author_lbl.setWordWrap(True)
            af = author_lbl.font()
            af.setPixelSize(self._AUTHOR_PX)
            author_lbl.setFont(af)
            layout.addWidget(author_lbl)
            total_h += spacing + author_lbl.heightForWidth(inner)

        # The row height (this size hint) must also cover the item's border,
        # which otherwise insets and clips the widget.
        return widget, QSize(width, total_h + self._ITEM_BORDER)

    def _has_valid_default(self) -> bool:
        return bool(self._cfg.starting_folder) and \
            Path(self._cfg.starting_folder).is_dir()

    def _open_default_folder(self):
        if self._has_valid_default():
            self._load_folder(self._cfg.starting_folder)

    def _on_recent_selected(self, index: int):
        path = self._recent_combo.itemData(index)
        if path:
            self._load_folder(path)

    def _record_history(self, folder: str):
        self._history = add_to_history(self._history, folder)
        save_history(self._history)
        self._refresh_recent_combo(current=folder)

    def _drop_from_history(self, folder: str):
        norm = _normalize_folder(folder)
        self._history = [p for p in self._history
                         if _normalize_folder(p) != norm]
        save_history(self._history)
        self._refresh_recent_combo()

    def _refresh_recent_combo(self, current: str | None = None):
        # Rebuilt with signals blocked so programmatic changes don't fire
        # `activated` (which is user-action only) and re-trigger a load.
        combo = self._recent_combo
        combo.blockSignals(True)
        combo.clear()
        if self._history:
            combo.setEnabled(True)
            for p in self._history:
                combo.addItem(Path(p).name, p)
                combo.setItemData(combo.count() - 1, p, Qt.ItemDataRole.ToolTipRole)
            idx = 0
            if current is not None:
                norm = _normalize_folder(current)
                idx = next((i for i, p in enumerate(self._history)
                            if _normalize_folder(p) == norm), 0)
            combo.setCurrentIndex(idx)
        else:
            combo.setEnabled(False)
            combo.addItem("No recent folders")
        combo.blockSignals(False)

    def _pick_folder(self):
        initial = (self._cfg.starting_folder
                   if self._cfg.starting_folder and Path(self._cfg.starting_folder).is_dir()
                   else "")
        folder = QFileDialog.getExistingDirectory(
            self, "Select EPUB folder", initial
        )
        if folder:
            self._load_folder(folder)

    def _load_folder(self, folder: str):
        self._folder_label.setText(folder)
        self._toc_panel.setVisible(False)
        self._toc_tree.clear()
        folder_path = Path(folder)

        # The folder may have been moved/deleted/unmounted since it was recorded.
        if not folder_path.is_dir():
            self._book_list.clear()
            self._book_list.addItem(QListWidgetItem(
                "Folder not found — it may have been moved or deleted"))
            self._drop_from_history(folder)
            return

        try:
            epubs = sorted(p for p in folder_path.iterdir()
                           if p.suffix.lower() == ".epub")
        except OSError as exc:
            self._book_list.clear()
            self._book_list.addItem(QListWidgetItem(
                f"Could not open folder: {exc.strerror or exc}"))
            return

        # Folder opened successfully — remember it in the history.
        self._record_history(folder)

        self._book_list.clear()
        self._show_status("<p>Select a book from the sidebar</p>")

        if not epubs:
            self._book_list.addItem(QListWidgetItem("No EPUB files found"))
            return

        metas = sorted((_read_epub_meta(ep) for ep in epubs), key=lambda m: m.sort_key)
        item_width = self._book_item_width()
        for meta in metas:
            size_kb = meta.path.stat().st_size // 1024
            item = QListWidgetItem()
            item.setToolTip(f"{meta.path.name}  •  {size_kb} KB")
            item.setData(256, str(meta.path))
            self._book_list.addItem(item)
            widget, hint = self._make_book_widget(meta.title, meta.author, item_width)
            item.setSizeHint(hint)
            self._book_list.setItemWidget(item, widget)

    # ── Book loading ──────────────────────────────────────────────────────────

    def _on_book_clicked(self, item: QListWidgetItem):
        path = item.data(256)
        if not path:
            return
        self._show_status("<p>Loading…</p>")
        self._toc_panel.setVisible(False)

        if self._loader and self._loader.isRunning():
            self._loader.quit()
            self._loader.wait()
        self._loader = BookLoader(
            path, self._img_dir, self._session_dir, self._cfg, self._page_counter
        )
        self._loader.loaded.connect(self._on_book_loaded)
        self._loader.failed.connect(self._on_book_failed)
        self._loader.start()

    def _on_book_loaded(self, file_path: str, toc: list):
        self._view.load(QUrl.fromLocalFile(file_path))
        self._populate_toc(toc)
        self._toc_panel.setVisible(bool(toc))

    def _on_book_failed(self, error: str):
        self._show_status(f'<p style="color:#f88">Failed to load: {error}</p>')

    # ── TOC ───────────────────────────────────────────────────────────────────

    def _populate_toc(self, entries: list):
        self._toc_tree.clear()

        def add_items(parent, items):
            for entry in items:
                if isinstance(parent, QTreeWidget):
                    node = QTreeWidgetItem(parent)
                else:
                    node = QTreeWidgetItem(parent)
                node.setText(0, entry.title)
                node.setData(0, Qt.ItemDataRole.UserRole, entry.anchor)
                node.setToolTip(0, entry.title)
                if entry.children:
                    add_items(node, entry.children)
                    node.setExpanded(False)

        add_items(self._toc_tree, entries)

    def _on_toc_item_clicked(self, item: QTreeWidgetItem, _column: int):
        if item.childCount() and not item.isExpanded():
            # First click on a collapsed parent: expand it
            item.setExpanded(True)
            return
        anchor = item.data(0, Qt.ItemDataRole.UserRole)
        if not anchor:
            return
        frag = anchor.lstrip("#")
        self._view.page().runJavaScript(
            f"(function(){{"
            f"  var el = document.getElementById('{frag}');"
            f"  if (el) el.scrollIntoView({{behavior: 'smooth', block: 'start'}});"
            f"}})();"
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _show_status(self, body: str):
        self._view.setHtml(_status_html(body, self._cfg))


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("EPUB Reader")

    cfg = load_config()
    window = ReaderWindow(cfg)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
