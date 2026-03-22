from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QListWidget,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class SamplePanel(QWidget):
    """Left panel: loaded samples and gate list."""

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

    def add_gate(self, label: str) -> None:
        self.gate_list.addItem(label)
        self.gate_list.setCurrentRow(self.gate_list.count() - 1)

    def clear_gates(self) -> None:
        self.gate_list.clear()

    def _on_sample_selection_changed(self, row: int) -> None:
        self.remove_sample_button.setEnabled(row >= 0)


class InspectorPanel(QWidget):
    """Right panel: metadata and plot controls."""

    axes_changed = Signal(int, int)
    sampling_changed = Signal(bool, int)
    create_rectangle_gate_requested = Signal()
    apply_gate_requested = Signal()
    clear_gate_requested = Signal()
    export_gate_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.file_label = QLabel("—")
        self.events_label = QLabel("—")
        self.channels_label = QLabel("—")
        self.active_gate_label = QLabel("—")
        self.displayed_points_label = QLabel("—")

        for label in (
            self.file_label,
            self.events_label,
            self.channels_label,
            self.active_gate_label,
            self.displayed_points_label,
        ):
            label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        info_box = QGroupBox("Inspector")
        info_form = QFormLayout()
        info_form.addRow("File:", self.file_label)
        info_form.addRow("Events:", self.events_label)
        info_form.addRow("Channels:", self.channels_label)
        info_form.addRow("Active gate:", self.active_gate_label)
        info_form.addRow("Displayed:", self.displayed_points_label)
        info_box.setLayout(info_form)

        self.x_axis_combo = QComboBox()
        self.y_axis_combo = QComboBox()
        self.x_axis_combo.setEnabled(False)
        self.y_axis_combo.setEnabled(False)

        self.limit_points_checkbox = QCheckBox("Limit displayed points")
        self.limit_points_checkbox.setChecked(True)

        self.max_points_spin = QSpinBox()
        self.max_points_spin.setRange(1000, 200000)
        self.max_points_spin.setSingleStep(1000)
        self.max_points_spin.setValue(30000)

        plot_controls_box = QGroupBox("Plot controls")
        plot_form = QFormLayout()
        plot_form.addRow("X axis:", self.x_axis_combo)
        plot_form.addRow("Y axis:", self.y_axis_combo)
        plot_form.addRow("", self.limit_points_checkbox)
        plot_form.addRow("Max points:", self.max_points_spin)
        plot_controls_box.setLayout(plot_form)

        self.create_rect_gate_button = QPushButton("Create rectangle gate")
        self.apply_gate_button = QPushButton("Apply gate")
        self.clear_gate_button = QPushButton("Clear draft gate")
        self.export_gate_button = QPushButton("Export active gate to CSV")

        gate_controls_box = QGroupBox("Gate controls")
        gate_layout = QVBoxLayout()
        gate_layout.addWidget(self.create_rect_gate_button)
        gate_layout.addWidget(self.apply_gate_button)
        gate_layout.addWidget(self.clear_gate_button)
        gate_layout.addWidget(self.export_gate_button)
        gate_controls_box.setLayout(gate_layout)

        hint_box = QGroupBox("Notes")
        hint_layout = QVBoxLayout()
        hint_layout.addWidget(
            QLabel(
                "Downsampling only affects display. Gates are applied to the full loaded dataset."
            )
        )
        hint_box.setLayout(hint_layout)

        layout = QVBoxLayout()
        layout.addWidget(info_box)
        layout.addWidget(plot_controls_box)
        layout.addWidget(gate_controls_box)
        layout.addWidget(hint_box)
        layout.addStretch(1)
        self.setLayout(layout)

        self.x_axis_combo.currentIndexChanged.connect(self._emit_axes_changed)
        self.y_axis_combo.currentIndexChanged.connect(self._emit_axes_changed)
        self.limit_points_checkbox.toggled.connect(self._emit_sampling_changed)
        self.max_points_spin.valueChanged.connect(self._emit_sampling_changed)

        self.create_rect_gate_button.clicked.connect(self.create_rectangle_gate_requested.emit)
        self.apply_gate_button.clicked.connect(self.apply_gate_requested.emit)
        self.clear_gate_button.clicked.connect(self.clear_gate_requested.emit)
        self.export_gate_button.clicked.connect(self.export_gate_requested.emit)

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

    def set_active_gate(self, gate_name: str) -> None:
        self.active_gate_label.setText(gate_name)

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

    def current_axes(self) -> tuple[int, int]:
        return self.x_axis_combo.currentIndex(), self.y_axis_combo.currentIndex()

    def sampling_settings(self) -> tuple[bool, int]:
        return self.limit_points_checkbox.isChecked(), self.max_points_spin.value()

    def set_displayed_points(self, displayed: int | None, total: int | None) -> None:
        if displayed is None or total is None:
            self.displayed_points_label.setText("—")
            return
        self.displayed_points_label.setText(f"{displayed:,} / {total:,}")

    def _emit_axes_changed(self) -> None:
        x_index = self.x_axis_combo.currentIndex()
        y_index = self.y_axis_combo.currentIndex()

        if x_index < 0 or y_index < 0:
            return

        self.axes_changed.emit(x_index, y_index)

    def _emit_sampling_changed(self) -> None:
        self.sampling_changed.emit(
            self.limit_points_checkbox.isChecked(),
            self.max_points_spin.value(),
        )
