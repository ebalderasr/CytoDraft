from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from cytodraft.gui.main_window import MainWindow
from cytodraft.gui.theme import APP_STYLESHEET


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("CytoDraft")
    app.setOrganizationName("CytoDraft")
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLESHEET)

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
