import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import tempfile
import unittest

import main
from PySide6.QtWidgets import QApplication

_app = None


def setUpModule():
    global _app
    _app = QApplication.instance() or QApplication([])


class StartupResolutionTests(unittest.TestCase):
    """Verifies the restart behavior: last-opened wins, then default, then nothing."""

    def setUp(self):
        self._orig_load = main.load_history
        self._orig_save = main.save_history
        main.save_history = lambda *a, **k: None  # don't touch the real file

    def tearDown(self):
        main.load_history = self._orig_load
        main.save_history = self._orig_save

    def _window(self, history, starting_folder):
        main.load_history = lambda *a, **k: list(history)
        return main.ReaderWindow(main.Config(starting_folder=starting_folder))

    def test_last_opened_wins_over_a_different_default(self):
        with tempfile.TemporaryDirectory() as last, tempfile.TemporaryDirectory() as default:
            w = self._window([last], default)
            self.assertEqual(w._folder_label.text(), main._normalize_folder(last))

    def test_falls_back_to_default_when_no_history(self):
        with tempfile.TemporaryDirectory() as default:
            w = self._window([], default)
            self.assertEqual(w._folder_label.text(), default)

    def test_opens_nothing_when_no_history_and_no_default(self):
        w = self._window([], "")
        self.assertEqual(w._folder_label.text(), "")


if __name__ == "__main__":
    unittest.main()
