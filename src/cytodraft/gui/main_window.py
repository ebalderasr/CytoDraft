from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox, QSplitter

from cytodraft.gui.panels import InspectorPanel, SamplePanel
from cytodraft.gui.plot_widget import CytometryPlotWidget


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("CytoDraft")
        self.resize(1400, 850)

        self.sample_panel = SamplePanel()
        self.plot_panel = CytometryPlotWidget()
        self.inspector_panel = InspectorPanel()

        self._build_ui()
        self._connect_signals()

        self.statusBar().showMessage("Ready")

    def _build_ui(self) -> None:
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.sample_panel)
        splitter.addWidget(self.plot_panel)
        splitter.addWidget(self.inspector_panel)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 7)
        splitter.setStretchFactor(2, 3)
        splitter.setSizes([260, 800, 340])

        self.setCentralWidget(splitter)
        self._create_menu()

    def _create_menu(self) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("&File")

        self.open_action = QAction("Open FCS...", self)
        self.open_action.setShortcut("Ctrl+O")

        self.exit_action = QAction("Exit", self)
        self.exit_action.setShortcut("Ctrl+Q")

        file_menu.addAction(self.open_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)

        help_menu = menu_bar.addMenu("&Help")
        self.about_action = QAction("About CytoDraft", self)
        help_menu.addAction(self.about_action)

    def _connect_signals(self) -> None:
        self.open_action.triggered.connect(self.open_fcs_dialog)
        self.exit_action.triggered.connect(self.close)
        self.about_action.triggered.connect(self.show_about_dialog)
        self.sample_panel.add_sample_button.clicked.connect(self.open_fcs_dialog)

    def open_fcs_dialog(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open FCS file",
            "",
            "FCS files (*.fcs);;All files (*)",
        )

        if not file_path:
            self.statusBar().showMessage("Open file cancelled", 3000)
            return

        file_name = Path(file_path).name
        self.sample_panel.add_sample(file_name)
        self.inspector_panel.set_file_info(
            file_name=file_name,
            events="pending",
            channels="pending",
            active_gate="None",
        )
        self.statusBar().showMessage(f"Selected file: {file_name}", 5000)

    def show_about_dialog(self) -> None:
        QMessageBox.about(
            self,
            "About CytoDraft",
            (
                "CytoDraft\n\n"
                "Open-source desktop application for cytometry data analysis.\n"
                "This is the initial GUI scaffold."
            ),
        )
