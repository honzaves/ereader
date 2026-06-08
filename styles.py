"""The Qt stylesheet for the reader window, kept apart from the widget logic."""

from config import Config


def sidebar_stylesheet(cfg: Config) -> str:
    return f"""
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
    """
