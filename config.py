"""Application configuration: the `config.toml` schema and loader."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

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
