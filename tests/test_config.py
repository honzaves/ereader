import tempfile
import unittest
from pathlib import Path

import config


class LoadConfigTests(unittest.TestCase):
    def setUp(self):
        self._orig = config.CONFIG_PATH

    def tearDown(self):
        config.CONFIG_PATH = self._orig

    def _use(self, path):
        config.CONFIG_PATH = path

    def test_writes_template_and_returns_defaults_when_missing(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "config.toml"
            self._use(p)
            cfg = config.load_config()
            self.assertTrue(p.exists())
            self.assertEqual(cfg, config.Config())

    def test_parses_provided_values(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "config.toml"
            p.write_text(
                'font_family = "Georgia"\n'
                'font_size = 20\n'
                'starting_folder = "/books"\n'
            )
            self._use(p)
            cfg = config.load_config()
            self.assertEqual(cfg.font_family, "Georgia")
            self.assertEqual(cfg.font_size, 20)
            self.assertEqual(cfg.starting_folder, "/books")

    def test_applies_defaults_for_missing_keys(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "config.toml"
            p.write_text('font_size = 18\n')
            self._use(p)
            cfg = config.load_config()
            self.assertEqual(cfg.font_size, 18)
            self.assertEqual(cfg.sidebar_bg, "#1a1a1e")  # untouched default

    def test_coerces_font_size_to_int(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "config.toml"
            p.write_text('font_size = 16.5\n')
            self._use(p)
            cfg = config.load_config()
            self.assertEqual(cfg.font_size, 16)


if __name__ == "__main__":
    unittest.main()
