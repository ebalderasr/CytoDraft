from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class SamplePanel(QWidget):
    """Left panel: loaded samples and gate tree placeholder."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.sample_list = QListWidget()
        self.sample_list.setAlternatingRowColors(True)

        self.gate_list = QListWidget()
        self.gate_list.setAlternatingRowColors(True)

        self.add_sample_button = QPushButton("Load sample")
        self.remove_sample_button = QPushButton("Remove selected")
        self.remove_sample_button.setEnabled(False)

        sample_box = QGroupBox("Samples")
        sample_layout = QVBoxLayout()
        sample_layout.addWidget(self.sample_list)
        sample_layout.addWidget(self.add_sample_button)
        sample_layout.addWidget(self.remove_sample_button)
        sample_box.setLayout(sample_layout)

        gate_box = QGroupBox("Gates")
        gate_layout = QVBoxLayout()
        gate_layout.addWidget(self.gate_list)
        gate_box.setLayout(gate_layout)

        layout = QVBoxLayout()
        layout.addWidget(sample_box, stretch=3)
        layout.addWidget(gate_box, stretch=2)
        self.setLayout(layout)

        self.sample_list.currentRowChanged.connect(self._on_sample_selection_changed)

    def add_sample(self, name: str) -> None:
        self.sample_list.addItem(name)
        self.sample_list.setCurrentRow(self.sample_list.count() - 1)

    def _on_sample_selection_changed(self, row: int) -> None:
        self.remove_sample_button.setEnabled(row >= 0)


class InspectorPanel(QWidget):
    """Right panel: metadata and plot controls."""

    axes_changed = Signal(int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.file_label = QLabel("—")
        self.events_label = QLabel("—")
        self.channels_label = QLabel("—")
        self.active_gate_label = QLabel("—")

        for label in (
            self.file_label,
            self.events_label,
            self.channels_label,
            self.active_gate_label,
        ):
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        info_box = QGroupBox("Inspector")
        info_form = QFormLayout()
        info_form.addRow("File:", self.file_label)
        info_form.addRow("Events:", self.events_label)
        info_form.addRow("Channels:", self.channels_label)
        info_form.addRow("Active gate:", self.active_gate_label)
        info_box.setLayout(info_form)

        self.x_axis_combo = QComboBox()
        self.y_axis_combo = QComboBox()
        self.x_axis_combo.setEnabled(False)
        self.y_axis_combo.setEnabled(False)

        plot_controls_box = QGroupBox("Plot controls")
        plot_form = QFormLayout()
        plot_form.addRow("X axis:", self.x_axis_combo)
        plot_form.addRow("Y axis:", self.y_axis_combo)
        plot_controls_box.setLayout(plot_form)

        hint_box = QGroupBox("Notes")
        hint_layout = QVBoxLayout()
        hint_layout.addWidget(QLabel("Use the axis selectors to inspect different channel pairs."))
        hint_box.setLayout(hint_layout)

        layout = QVBoxLayout()
        layout.addWidget(info_box)
        layout.addWidget(plot_controls_box)
        layout.addWidget(hint_box)
        layout.addStretch(1)
        self.setLayout(layout)

        self.x_axis_combo.currentIndexChanged.connect(self._emit_axes_changed)
        self.y_axis_combo.currentIndexChanged.connect(self._emit_axes_changed)

    def set_file_info(
        self,
        *,
        file_name: str = "—",
        events: str = "—",
        channels: str = "—",
        active_gate: str = "—",
    ) -> None:
        self.file_label.setText(file_name)
        self.events_label.setText(events)
        self.channels_label.setText(channels)
        self.active_gate_label.setText(active_gate)

    def set_channels(
        self,
        channel_names: list[str],
        *,
        x_index: int | None = None,
        y_index: int | None = None,
    ) -> None:
        with QSignalBlocker(self.x_axis_combo), QSignalBlocker(self.y_axis_combo):
            self.x_axis_combo.clear()
            self.y_axis_combo.clear()

            self.x_axis_combo.addItems(channel_names)
            self.y_axis_combo.addItems(channel_names)

            has_channels = len(channel_names) >= 2
            self.x_axis_combo.setEnabled(has_channels)
            self.y_axis_combo.setEnabled(has_channels)

            if not has_channels:
                return

            if x_index is None:
                x_index = 0
            if y_index is None:
                y_index = 1 if len(channel_names) > 1 else 0

            self.x_axis_combo.setCurrentIndex(x_index)
            self.y_axis_combo.setCurrentIndex(y_index)

    def clear_channels(self) -> None:
        with QSignalBlocker(self.x_axis_combo), QSignalBlocker(self.y_axis_combo):
            self.x_axis_combo.clear()
            self.y_axis_combo.clear()
            self.x_axis_combo.setEnabled(False)
            self.y_axis_combo.setEnabled(False)

    def _emit_axes_changed(self) -> None:
        x_index = self.x_axis_combo.currentIndex()
        y_index = self.y_axis_combo.currentIndex()

        if x_index < 0 or y_index < 0:
            return

        self.axes_changed.emit(x_index, y_index)
