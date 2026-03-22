from PySide6.QtWidgets import QApplication, QLabel, QMainWindow
import sys


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("CytoDraft")
        self.resize(1000, 700)
        self.setCentralWidget(QLabel("CytoDraft scaffold is running."))


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
