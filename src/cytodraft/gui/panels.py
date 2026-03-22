from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QColor, QDoubleValidator
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class SamplePanel(QWidget):
    """Left panel: loaded samples and gate list."""

    sample_selection_changed = Signal(int)
    gate_selection_changed = Signal(int)
    rename_gate_context_requested = Signal(int)
    recolor_gate_context_requested = Signal(int)
    delete_gate_context_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._plot_mode = "scatter"

        self.sample_list = QListWidget()
        self.sample_list.setAlternatingRowColors(True)
        self.sample_list.setSpacing(2)

        self.gate_list = QListWidget()
        self.gate_list.setAlternatingRowColors(True)
        self.gate_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.gate_list.setSpacing(2)

        self.add_sample_button = QPushButton("Open FCS")
        self.add_sample_button.setProperty("variant", "primary")
        self.remove_sample_button = QPushButton("Remove sample")
        self.remove_sample_button.setProperty("variant", "danger")
        self.remove_sample_button.setEnabled(False)

        sample_box = QGroupBox("Samples")
        sample_layout = QVBoxLayout()
        sample_layout.addWidget(self.sample_list)
        sample_layout.addWidget(self.add_sample_button)
        sample_layout.addWidget(self.remove_sample_button)
        sample_box.setLayout(sample_layout)

        gate_box = QGroupBox("Gates / populations")
        gate_layout = QVBoxLayout()
        gate_layout.addWidget(self.gate_list)
        gate_box.setLayout(gate_layout)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.addWidget(sample_box, stretch=3)
        layout.addWidget(gate_box, stretch=2)
        self.setLayout(layout)

        self.sample_list.currentRowChanged.connect(self._on_sample_selection_changed)
        self.gate_list.currentRowChanged.connect(self.gate_selection_changed.emit)
        self.gate_list.customContextMenuRequested.connect(self._on_gate_context_menu_requested)

        self.reset_gates()

    def add_sample(self, name: str) -> None:
        self.sample_list.addItem(name)
        self.sample_list.setCurrentRow(self.sample_list.count() - 1)

    def reset_gates(self) -> None:
        self.gate_list.clear()
        self.gate_list.addItem("All events")
        self.gate_list.setCurrentRow(0)

    def reset_samples(self) -> None:
        self.sample_list.clear()
        self.remove_sample_button.setEnabled(False)

    def add_gate(self, label: str, *, select: bool = True) -> None:
        self.gate_list.addItem(label)
        if select:
            self.gate_list.setCurrentRow(self.gate_list.count() - 1)

    def update_gate(self, gate_index: int, label: str, color_hex: str) -> None:
        item = self.gate_item(gate_index)
        if item is None:
            return

        item.setText(label)
        item.setForeground(QColor(color_hex))

    def gate_item(self, gate_index: int) -> QListWidgetItem | None:
        row = gate_index + 1
        if row < 1 or row >= self.gate_list.count():
            return None
        return self.gate_list.item(row)

    def select_gate_row(self, row: int) -> None:
        if 0 <= row < self.gate_list.count():
            self.gate_list.setCurrentRow(row)

    def _on_sample_selection_changed(self, row: int) -> None:
        self.remove_sample_button.setEnabled(row >= 0)
        self.sample_selection_changed.emit(row)

    def _on_gate_context_menu_requested(self, pos) -> None:
        item = self.gate_list.itemAt(pos)
        if item is None:
            return

        row = self.gate_list.row(item)
        if row <= 0:
            return

        menu = QMenu(self)
        rename_action = menu.addAction("Rename gate")
        recolor_action = menu.addAction("Change color")
        delete_action = menu.addAction("Delete gate")
        chosen_action = menu.exec(self.gate_list.mapToGlobal(pos))
        if chosen_action is None:
            return

        self.gate_list.setCurrentRow(row)
        gate_index = row - 1
        if chosen_action is rename_action:
            self.rename_gate_context_requested.emit(gate_index)
        elif chosen_action is recolor_action:
            self.recolor_gate_context_requested.emit(gate_index)
        elif chosen_action is delete_action:
            self.delete_gate_context_requested.emit(gate_index)


class InspectorPanel(QWidget):
    """Right panel: metadata and plot controls."""

    axes_changed = Signal(int, int)
    plot_mode_changed = Signal(str)
    sampling_changed = Signal(bool, int)
    view_settings_changed = Signal()
    auto_range_requested = Signal()
    create_gate_requested = Signal()
    apply_gate_requested = Signal()
    clear_gate_requested = Signal()
    export_gate_requested = Signal()
    rename_gate_requested = Signal(str)
    recolor_gate_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

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
        info_form.addRow("Active population:", self.active_gate_label)
        info_form.addRow("Displayed:", self.displayed_points_label)
        info_box.setLayout(info_form)

        self.plot_mode_combo = QComboBox()
        self.plot_mode_combo.addItem("Scatter (2D)", "scatter")
        self.plot_mode_combo.addItem("Histogram (1D)", "histogram")

        self.rectangle_gate_button = QPushButton("Rectangle")
        self.rectangle_gate_button.setCheckable(True)
        self.polygon_gate_button = QPushButton("Polygon")
        self.polygon_gate_button.setCheckable(True)
        self.circle_gate_button = QPushButton("Circle")
        self.circle_gate_button.setCheckable(True)

        self.scatter_gate_group = QButtonGroup(self)
        self.scatter_gate_group.setExclusive(True)
        self.scatter_gate_group.addButton(self.rectangle_gate_button)
        self.scatter_gate_group.addButton(self.polygon_gate_button)
        self.scatter_gate_group.addButton(self.circle_gate_button)
        self.rectangle_gate_button.setChecked(True)

        self.histogram_range_button = QPushButton("Range")
        self.histogram_range_button.setCheckable(True)
        self.histogram_range_button.setChecked(True)

        self.x_axis_combo = QComboBox()
        self.y_axis_combo = QComboBox()
        self.x_axis_combo.setEnabled(False)
        self.y_axis_combo.setEnabled(False)

        self.x_scale_combo = QComboBox()
        self.x_scale_combo.addItem("Linear", "linear")
        self.x_scale_combo.addItem("Log10", "log10")
        self.x_scale_combo.addItem("Asinh", "asinh")

        self.y_scale_combo = QComboBox()
        self.y_scale_combo.addItem("Linear", "linear")
        self.y_scale_combo.addItem("Log10", "log10")
        self.y_scale_combo.addItem("Asinh", "asinh")

        self.limit_points_checkbox = QCheckBox("Limit displayed points")
        self.limit_points_checkbox.setChecked(True)

        self.max_points_spin = QSpinBox()
        self.max_points_spin.setRange(1000, 200000)
        self.max_points_spin.setSingleStep(1000)
        self.max_points_spin.setValue(30000)

        validator = QDoubleValidator(self)

        self.x_min_edit = QLineEdit()
        self.x_max_edit = QLineEdit()
        self.y_min_edit = QLineEdit()
        self.y_max_edit = QLineEdit()

        for edit in (self.x_min_edit, self.x_max_edit, self.y_min_edit, self.y_max_edit):
            edit.setValidator(validator)
            edit.setPlaceholderText("auto")

        self.apply_view_button = QPushButton("Apply view")
        self.apply_view_button.setProperty("variant", "subtle")
        self.auto_range_button = QPushButton("Reset zoom")
        self.auto_range_button.setProperty("variant", "subtle")

        for button in (
            self.rectangle_gate_button,
            self.polygon_gate_button,
            self.circle_gate_button,
            self.histogram_range_button,
            self.apply_view_button,
            self.auto_range_button,
        ):
            button.setMinimumHeight(38)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        scatter_gate_buttons_widget = QWidget()
        scatter_gate_button_layout = QVBoxLayout()
        scatter_gate_button_layout.setContentsMargins(0, 0, 0, 0)
        scatter_gate_button_layout.setSpacing(8)
        scatter_gate_button_layout.addWidget(self.rectangle_gate_button)
        scatter_gate_button_layout.addWidget(self.polygon_gate_button)
        scatter_gate_button_layout.addWidget(self.circle_gate_button)
        scatter_gate_buttons_widget.setLayout(scatter_gate_button_layout)

        histogram_gate_button_widget = QWidget()
        histogram_gate_button_layout = QVBoxLayout()
        histogram_gate_button_layout.setContentsMargins(0, 0, 0, 0)
        histogram_gate_button_layout.setSpacing(8)
        histogram_gate_button_layout.addWidget(self.histogram_range_button)
        histogram_gate_button_widget.setLayout(histogram_gate_button_layout)

        visualization_box = QGroupBox("Visualizacion")
        visualization_form = QFormLayout()
        visualization_form.addRow("Plot mode:", self.plot_mode_combo)
        visualization_form.addRow("X axis:", self.x_axis_combo)
        visualization_form.addRow("Y axis:", self.y_axis_combo)
        visualization_box.setLayout(visualization_form)

        plot_adjustments_box = QGroupBox("Ajustes de grafica")
        plot_adjustments_form = QFormLayout()
        plot_adjustments_form.addRow("X scale:", self.x_scale_combo)
        plot_adjustments_form.addRow("Y scale:", self.y_scale_combo)
        plot_adjustments_form.addRow("X min:", self.x_min_edit)
        plot_adjustments_form.addRow("X max:", self.x_max_edit)
        plot_adjustments_form.addRow("Y min:", self.y_min_edit)
        plot_adjustments_form.addRow("Y max:", self.y_max_edit)
        plot_adjustments_form.addRow("", self.apply_view_button)
        plot_adjustments_form.addRow("", self.auto_range_button)
        plot_adjustments_form.addRow("", self.limit_points_checkbox)
        plot_adjustments_form.addRow("Max points:", self.max_points_spin)
        plot_adjustments_box.setLayout(plot_adjustments_form)

        self.create_gate_button = QPushButton("Create gate")
        self.create_gate_button.setProperty("variant", "subtle")
        self.apply_gate_button = QPushButton("Apply gate")
        self.apply_gate_button.setProperty("variant", "primary")
        self.clear_gate_button = QPushButton("Clear draft")
        self.clear_gate_button.setProperty("variant", "danger")
        self.export_gate_button = QPushButton("Export gate")
        self.export_gate_button.setProperty("variant", "subtle")
        self.gate_name_edit = QLineEdit()
        self.gate_name_edit.setPlaceholderText("Select a gate")
        self.gate_color_button = QPushButton("Gate color")
        self.gate_color_button.setProperty("variant", "subtle")

        for button in (
            self.create_gate_button,
            self.apply_gate_button,
            self.clear_gate_button,
            self.export_gate_button,
            self.gate_color_button,
        ):
            button.setMinimumHeight(38)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        gate_controls_box = QWidget()
        gate_layout = QVBoxLayout()
        gate_layout.setContentsMargins(0, 0, 0, 0)
        gate_layout.setSpacing(12)
        scatter_gate_box = QGroupBox("Scatter gate type")
        scatter_gate_layout = QVBoxLayout()
        scatter_gate_layout.setContentsMargins(0, 0, 0, 0)
        scatter_gate_layout.setSpacing(8)
        scatter_gate_layout.addWidget(scatter_gate_buttons_widget)
        scatter_gate_box.setLayout(scatter_gate_layout)

        histogram_gate_box = QGroupBox("Histogram gate type")
        histogram_gate_layout = QVBoxLayout()
        histogram_gate_layout.setContentsMargins(0, 0, 0, 0)
        histogram_gate_layout.setSpacing(8)
        histogram_gate_layout.addWidget(histogram_gate_button_widget)
        histogram_gate_box.setLayout(histogram_gate_layout)

        gate_actions_box = QGroupBox("Gate actions")
        gate_actions_layout = QVBoxLayout()
        gate_actions_layout.setSpacing(10)
        gate_actions_layout.addWidget(self.create_gate_button)
        gate_actions_layout.addWidget(self.apply_gate_button)
        gate_actions_layout.addWidget(self.clear_gate_button)
        gate_actions_box.setLayout(gate_actions_layout)

        gate_form = QFormLayout()
        gate_form.setVerticalSpacing(10)
        gate_form.addRow("Gate name:", self.gate_name_edit)
        gate_form.addRow("Gate color:", self.gate_color_button)
        gate_layout.addWidget(visualization_box)
        gate_layout.addWidget(gate_actions_box)
        gate_layout.addWidget(scatter_gate_box)
        gate_layout.addWidget(histogram_gate_box)
        gate_layout.addLayout(gate_form)
        gate_layout.addWidget(self.export_gate_button)
        gate_layout.addStretch(1)
        gate_controls_box.setLayout(gate_layout)

        gate_scroll_area = QScrollArea()
        gate_scroll_area.setWidgetResizable(True)
        gate_scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        gate_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        gate_scroll_area.setWidget(gate_controls_box)

        self.mode_hint_label = QLabel(
            "Gate concentra la visualizacion, los ejes y la edicion del gate activo."
        )
        self.mode_hint_label.setWordWrap(True)

        self.controls_tabs = QTabWidget()
        self.controls_tabs.addTab(gate_scroll_area, "Gate")
        self.controls_tabs.addTab(plot_adjustments_box, "Ajustes de grafica")

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(info_box)
        layout.addWidget(self.controls_tabs, stretch=1)
        layout.addWidget(self.mode_hint_label)
        layout.addStretch(1)
        self.setLayout(layout)

        self.plot_mode_combo.currentIndexChanged.connect(self._emit_plot_mode_changed)
        self.x_axis_combo.currentIndexChanged.connect(self._emit_axes_changed)
        self.y_axis_combo.currentIndexChanged.connect(self._emit_axes_changed)
        self.x_scale_combo.currentIndexChanged.connect(self._emit_view_settings_changed)
        self.y_scale_combo.currentIndexChanged.connect(self._emit_view_settings_changed)
        self.limit_points_checkbox.toggled.connect(self._emit_sampling_changed)
        self.max_points_spin.valueChanged.connect(self._emit_sampling_changed)

        self.x_min_edit.editingFinished.connect(self._emit_view_settings_changed)
        self.x_max_edit.editingFinished.connect(self._emit_view_settings_changed)
        self.y_min_edit.editingFinished.connect(self._emit_view_settings_changed)
        self.y_max_edit.editingFinished.connect(self._emit_view_settings_changed)

        self.apply_view_button.clicked.connect(self._emit_view_settings_changed)
        self.auto_range_button.clicked.connect(self._emit_auto_range_requested)

        self.create_gate_button.clicked.connect(self.create_gate_requested.emit)
        self.apply_gate_button.clicked.connect(self.apply_gate_requested.emit)
        self.clear_gate_button.clicked.connect(self.clear_gate_requested.emit)
        self.export_gate_button.clicked.connect(self.export_gate_requested.emit)
        self.gate_name_edit.editingFinished.connect(self._emit_rename_gate_requested)
        self.gate_color_button.clicked.connect(self.recolor_gate_requested.emit)
        self.set_plot_mode("scatter")
        self.set_gate_editor_state(None, None)

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

    def set_gate_editor_state(self, gate_name: str | None, color_hex: str | None) -> None:
        is_enabled = gate_name is not None and color_hex is not None
        with QSignalBlocker(self.gate_name_edit):
            self.gate_name_edit.setText(gate_name or "")
        self.gate_name_edit.setEnabled(is_enabled)
        self.gate_color_button.setEnabled(is_enabled)

        if color_hex is None:
            self.gate_color_button.setStyleSheet("")
            return

        self.gate_color_button.setStyleSheet(
            f"background-color: {color_hex}; color: white; font-weight: 600;"
        )

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

            has_channels = len(channel_names) >= 1
            self.x_axis_combo.setEnabled(has_channels)
            self.y_axis_combo.setEnabled(len(channel_names) >= 2)

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

    def current_plot_mode(self) -> str:
        return self._plot_mode

    def current_scatter_gate_type(self) -> str:
        if self.polygon_gate_button.isChecked():
            return "polygon"
        if self.circle_gate_button.isChecked():
            return "circle"
        return "rectangle"

    def set_plot_mode(self, mode: str) -> None:
        combo_index = self.plot_mode_combo.findData(mode)
        if combo_index >= 0 and self.plot_mode_combo.currentIndex() != combo_index:
            with QSignalBlocker(self.plot_mode_combo):
                self.plot_mode_combo.setCurrentIndex(combo_index)
        self._plot_mode = mode
        if mode == "histogram":
            self.rectangle_gate_button.setEnabled(False)
            self.polygon_gate_button.setEnabled(False)
            self.circle_gate_button.setEnabled(False)
            self.histogram_range_button.setEnabled(True)
            self.histogram_range_button.setChecked(True)
            self.y_axis_combo.setEnabled(False)
            self.y_scale_combo.setEnabled(False)
            self.mode_hint_label.setText("Histogram mode enables only the 1D range gate.")
        else:
            self.rectangle_gate_button.setEnabled(True)
            self.polygon_gate_button.setEnabled(True)
            self.circle_gate_button.setEnabled(True)
            self.histogram_range_button.setEnabled(False)
            self.y_axis_combo.setEnabled(self.y_axis_combo.count() >= 2)
            self.y_scale_combo.setEnabled(True)
            self.mode_hint_label.setText(
                "Scatter mode enables rectangle, polygon and circle gates."
            )
    def current_scales(self) -> tuple[str, str]:
        x_mode = str(self.x_scale_combo.currentData())
        y_mode = str(self.y_scale_combo.currentData())
        return x_mode, y_mode

    def current_view_limits(self) -> tuple[float | None, float | None, float | None, float | None]:
        return (
            self._parse_optional_float(self.x_min_edit.text()),
            self._parse_optional_float(self.x_max_edit.text()),
            self._parse_optional_float(self.y_min_edit.text()),
            self._parse_optional_float(self.y_max_edit.text()),
        )

    def clear_view_limits(self) -> None:
        self.x_min_edit.clear()
        self.x_max_edit.clear()
        self.y_min_edit.clear()
        self.y_max_edit.clear()

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

        if x_index < 0:
            return

        if self.current_plot_mode() == "histogram":
            self.axes_changed.emit(x_index, y_index)
            return

        if y_index < 0:
            return

        self.axes_changed.emit(x_index, y_index)

    def _emit_plot_mode_changed(self) -> None:
        mode = str(self.plot_mode_combo.currentData())
        self.set_plot_mode(mode)
        self.plot_mode_changed.emit(mode)

    def _emit_sampling_changed(self) -> None:
        self.sampling_changed.emit(
            self.limit_points_checkbox.isChecked(),
            self.max_points_spin.value(),
        )

    def _emit_view_settings_changed(self, *args: object) -> None:
        del args
        self.view_settings_changed.emit()

    def _emit_auto_range_requested(self, *args: object) -> None:
        del args
        self.auto_range_requested.emit()

    def _emit_rename_gate_requested(self) -> None:
        self.rename_gate_requested.emit(self.gate_name_edit.text())

    @staticmethod
    def _parse_optional_float(text: str) -> float | None:
        stripped = text.strip()
        if not stripped:
            return None
        return float(stripped)
