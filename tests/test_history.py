import json
import os
import tempfile
import unittest
from pathlib import Path

import main


class AddToHistoryTests(unittest.TestCase):
    def test_new_folder_goes_to_front(self):
        result = main.add_to_history(["/a", "/b"], "/c")
        self.assertEqual(result[0], main._normalize_folder("/c"))

    def test_reopening_existing_folder_moves_it_to_front_without_duplicate(self):
        history = [main._normalize_folder(p) for p in ["/a", "/b", "/c"]]
        result = main.add_to_history(history, "/c")
        self.assertEqual(result[0], main._normalize_folder("/c"))
        self.assertEqual(result.count(main._normalize_folder("/c")), 1)
        self.assertEqual(len(result), 3)

    def test_respects_limit_dropping_oldest(self):
        history = [main._normalize_folder(f"/f{i}") for i in range(10)]
        result = main.add_to_history(history, "/new", limit=10)
        self.assertEqual(len(result), 10)
        self.assertEqual(result[0], main._normalize_folder("/new"))
        # the oldest (last) entry should have been dropped
        self.assertNotIn(main._normalize_folder("/f9"), result)

    def test_normalizes_so_trailing_slash_is_not_a_duplicate(self):
        history = [main._normalize_folder("/tmp/foo")]
        result = main.add_to_history(history, "/tmp/foo/")
        self.assertEqual(len(result), 1)


class PruneHistoryTests(unittest.TestCase):
    def test_drops_nonexistent_dirs_and_dedups_preserving_order(self):
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            history = [d1, "/definitely/does/not/exist/xyz", d2, d1]
            result = main.prune_history(history)
            self.assertEqual(
                result,
                [main._normalize_folder(d1), main._normalize_folder(d2)],
            )

    def test_drops_path_that_is_a_file_not_a_dir(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "afile.txt"
            f.write_text("x")
            result = main.prune_history([str(f), d])
            self.assertEqual(result, [main._normalize_folder(d)])


class LoadSaveHistoryTests(unittest.TestCase):
    def _tmp_session(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        return Path(path)

    def test_missing_file_returns_empty(self):
        path = Path(tempfile.gettempdir()) / "nope_session_missing.json"
        if path.exists():
            path.unlink()
        self.assertEqual(main.load_history(path), [])

    def test_corrupt_file_returns_empty(self):
        path = self._tmp_session()
        try:
            path.write_text("{ this is not json")
            self.assertEqual(main.load_history(path), [])
        finally:
            path.unlink()

    def test_save_then_load_round_trips(self):
        path = self._tmp_session()
        try:
            history = ["/a", "/b", "/c"]
            main.save_history(history, path)
            self.assertEqual(main.load_history(path), history)
        finally:
            path.unlink()

    def test_load_ignores_non_string_and_missing_key(self):
        path = self._tmp_session()
        try:
            path.write_text(json.dumps({"folder_history": ["/a", 5, None, "/b"]}))
            self.assertEqual(main.load_history(path), ["/a", "/b"])
            path.write_text(json.dumps({"something_else": 1}))
            self.assertEqual(main.load_history(path), [])
        finally:
            path.unlink()


if __name__ == "__main__":
    unittest.main()
