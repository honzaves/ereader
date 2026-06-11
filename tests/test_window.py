import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import unittest
from pathlib import Path

import history
from config import Config
from window import ReaderWindow
from PySide6.QtWidgets import QApplication

from test_epub import make_epub

_app = None


def setUpModule():
    global _app
    _app = QApplication.instance() or QApplication([])


class BookListRenderingTests(unittest.TestCase):
    """Exercises the real book-list render path (_make_book_widget, sizing)."""

    def setUp(self):
        self._orig_load = history.load_history
        self._orig_save = history.save_history
        history.load_history = lambda *a, **k: []
        history.save_history = lambda *a, **k: None  # don't touch the real file

    def tearDown(self):
        history.load_history = self._orig_load
        history.save_history = self._orig_save

    def test_folder_with_one_epub_renders_one_item_widget(self):
        with tempfile.TemporaryDirectory() as d:
            make_epub(Path(d) / "book.epub", title="Dune", author="Frank Herbert")
            w = ReaderWindow(Config())
            w._load_folder(d)
            self.assertEqual(w._book_list.count(), 1)
            item = w._book_list.item(0)
            self.assertIsNotNone(w._book_list.itemWidget(item))
            # _make_book_widget computed a real, positive row height.
            self.assertGreater(item.sizeHint().height(), 0)

    def test_empty_folder_shows_placeholder_row(self):
        with tempfile.TemporaryDirectory() as d:
            w = ReaderWindow(Config())
            w._load_folder(d)
            self.assertEqual(w._book_list.count(), 1)
            self.assertEqual(w._book_list.item(0).text(), "No EPUB files found")


if __name__ == "__main__":
    unittest.main()
