from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox, QSplitter

from cytodraft.core.fcs_reader import choose_default_axes
from cytodraft.gui.panels import InspectorPanel, SamplePanel
from cytodraft.gui.plot_widget import CytometryPlotWidget
from cytodraft.models.sample import SampleData
from cytodraft.services.sample_service import SampleService


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("CytoDraft")
        self.resize(1400, 850)

        self.sample_service = SampleService()
        self.current_sample: SampleData | None = None

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
        self.inspector_panel.axes_changed.connect(self.on_axes_changed)
        self.inspector_panel.sampling_changed.connect(self.on_sampling_changed)

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

        self.load_sample(file_path)

    def load_sample(self, file_path: str) -> None:
        try:
            sample = self.sample_service.load_sample(file_path)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Failed to load FCS",
                f"Could not read file:\n{file_path}\n\nError:\n{exc}",
            )
            self.statusBar().showMessage("Failed to load FCS file", 5000)
            return

        self.current_sample = sample
        self.sample_panel.add_sample(sample.file_name)
        self._update_inspector(sample)
        self._configure_axis_selectors(sample)
        self._plot_default_view(sample)

        self.statusBar().showMessage(
            f"Loaded {sample.file_name} | {sample.event_count} events | {sample.channel_count} channels",
            6000,
        )

    def _update_inspector(self, sample: SampleData) -> None:
        self.inspector_panel.set_file_info(
            file_name=sample.file_name,
            events=str(sample.event_count),
            channels=str(sample.channel_count),
            active_gate="None",
        )
        self.inspector_panel.set_displayed_points(None, None)

    def _configure_axis_selectors(self, sample: SampleData) -> None:
        channel_names = [channel.display_name for channel in sample.channels]

        try:
            x_idx, y_idx = choose_default_axes(sample)
        except ValueError:
            self.inspector_panel.clear_channels()
            return

        self.inspector_panel.set_channels(channel_names, x_index=x_idx, y_index=y_idx)

    def _plot_default_view(self, sample: SampleData) -> None:
        try:
            x_idx, y_idx = choose_default_axes(sample)
        except ValueError:
            self.plot_panel.show_empty_message("Sample has fewer than two channels")
            return

        self.plot_axes(x_idx, y_idx)

    def plot_axes(self, x_idx: int, y_idx: int) -> None:
        if self.current_sample is None:
            return

        sample = self.current_sample

        if x_idx < 0 or y_idx < 0:
            return
        if x_idx >= sample.channel_count or y_idx >= sample.channel_count:
            return

        x = sample.events[:, x_idx]
        y = sample.events[:, y_idx]

        x_label = sample.channel_label(x_idx)
        y_label = sample.channel_label(y_idx)

        limit_enabled, max_points = self.inspector_panel.sampling_settings()
        display_limit = max_points if limit_enabled else None

        displayed_count, total_count = self.plot_panel.plot_scatter(
            x,
            y,
            x_label,
            y_label,
            title=f"{sample.file_name} | {y_label} vs {x_label}",
            max_points=display_limit,
        )

        self.inspector_panel.set_displayed_points(displayed_count, total_count)

        suffix = f"{displayed_count:,}/{total_count:,} displayed"
        self.statusBar().showMessage(
            f"Viewing {sample.file_name} | X: {x_label} | Y: {y_label} | {suffix}",
            4000,
        )

    def on_axes_changed(self, x_idx: int, y_idx: int) -> None:
        self.plot_axes(x_idx, y_idx)

    def on_sampling_changed(self, enabled: bool, max_points: int) -> None:
        del enabled, max_points
        x_idx, y_idx = self.inspector_panel.current_axes()
        self.plot_axes(x_idx, y_idx)

    def show_about_dialog(self) -> None:
        QMessageBox.about(
            self,
            "About CytoDraft",
            (
                "CytoDraft\n\n"
                "Open-source desktop application for cytometry data analysis.\n"
                "Current stage: local FCS loading + metadata + interactive axis selection."
            ),
        )
