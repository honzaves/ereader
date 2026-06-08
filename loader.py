"""Background EPUB loading so the UI stays responsive while a book is parsed."""

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from config import Config
from epub_content import build_book_html


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
