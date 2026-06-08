"""Entry point: load config, build the window, run the Qt event loop."""

import sys

from PySide6.QtWidgets import QApplication

from config import load_config
from window import ReaderWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("EPUB Reader")

    cfg = load_config()
    window = ReaderWindow(cfg)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
