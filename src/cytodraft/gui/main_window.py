from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QFileDialog,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QSplitter,
)

from cytodraft.core.export import (
    export_masked_events_to_csv,
    export_masked_events_to_fcs,
    export_population_statistics_to_csv,
)
from cytodraft.core.fcs_reader import choose_default_axes
from cytodraft.core.gating import (
    circle_mask_from_parent,
    polygon_mask_from_parent,
    rectangle_mask_from_parent,
    range_mask_from_parent,
)
from cytodraft.core.statistics import StatisticResult, calculate_population_statistics
from cytodraft.core.transforms import apply_scale, axis_label
from cytodraft.gui.panels import InspectorPanel, SamplePanel
from cytodraft.gui.plot_widget import CytometryPlotWidget
from cytodraft.models.gate import (
    CircleGate,
    DEFAULT_GATE_COLOR,
    PolygonGate,
    RangeGate,
    RectangleGate,
)
from cytodraft.models.sample import SampleData
from cytodraft.services.sample_service import SampleService


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("CytoDraft")
        self.resize(1400, 850)
        self.setMinimumSize(960, 680)

        self.sample_service = SampleService()
        self.current_sample: SampleData | None = None
        self.gates: list[RectangleGate | RangeGate | PolygonGate | CircleGate] = []
        self.active_gate: RectangleGate | RangeGate | PolygonGate | CircleGate | None = None
        self._latest_statistics: list[StatisticResult] = []
        self._latest_statistics_population_name = ""
        self._latest_statistics_channel_name = ""

        self.sample_panel = SamplePanel()
        self.plot_panel = CytometryPlotWidget()
        self.inspector_panel = InspectorPanel()

        self._build_ui()
        self._connect_signals()

        self.statusBar().showMessage("Ready")

    def _build_ui(self) -> None:
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
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

        self.export_gate_action = QAction("Export active gate...", self)
        self.export_gate_action.setShortcut("Ctrl+E")

        self.exit_action = QAction("Exit", self)
        self.exit_action.setShortcut("Ctrl+Q")

        file_menu.addAction(self.open_action)
        file_menu.addAction(self.export_gate_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)

        help_menu = menu_bar.addMenu("&Help")
        self.about_action = QAction("About CytoDraft", self)
        help_menu.addAction(self.about_action)

    def _connect_signals(self) -> None:
        self.open_action.triggered.connect(self.open_fcs_dialog)
        self.export_gate_action.triggered.connect(self.on_export_active_gate)
        self.exit_action.triggered.connect(self.close)
        self.about_action.triggered.connect(self.show_about_dialog)
        self.sample_panel.add_sample_button.clicked.connect(self.open_fcs_dialog)
        self.sample_panel.remove_sample_button.clicked.connect(self.remove_selected_sample)
        self.sample_panel.sample_selection_changed.connect(self.on_sample_selection_changed)
        self.sample_panel.gate_selection_changed.connect(self.on_gate_selection_changed)
        self.sample_panel.rename_gate_context_requested.connect(self.on_rename_gate_from_context)
        self.sample_panel.recolor_gate_context_requested.connect(self.on_recolor_gate_from_context)
        self.sample_panel.delete_gate_context_requested.connect(self.on_delete_gate_from_context)
        self.inspector_panel.axes_changed.connect(self.on_axes_changed)
        self.inspector_panel.plot_mode_changed.connect(self.on_plot_mode_changed)
        self.inspector_panel.sampling_changed.connect(self.on_sampling_changed)
        self.inspector_panel.view_settings_changed.connect(self.on_view_settings_changed)
        self.inspector_panel.auto_range_requested.connect(self.on_auto_range_requested)
        self.inspector_panel.create_gate_requested.connect(self.on_create_gate)
        self.inspector_panel.apply_gate_requested.connect(self.on_apply_gate)
        self.inspector_panel.clear_gate_requested.connect(self.on_clear_draft_gate)
        self.inspector_panel.export_gate_requested.connect(self.on_export_active_gate)
        self.inspector_panel.calculate_statistics_requested.connect(self.on_calculate_statistics)
        self.inspector_panel.export_statistics_requested.connect(self.on_export_statistics)
        self.inspector_panel.rename_gate_requested.connect(self.on_rename_active_gate)
        self.inspector_panel.recolor_gate_requested.connect(self.on_recolor_active_gate)

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
        self.gates = []
        self.active_gate = None
        self._clear_statistics_results()

        self.sample_panel.reset_samples()
        self.sample_panel.add_sample(sample.file_name)
        self.sample_panel.reset_gates()
        self._update_population_context_labels()

        self._update_inspector(sample)
        self._configure_axis_selectors(sample)
        self.redraw_current_plot()

        self.statusBar().showMessage(
            f"Loaded {sample.file_name} | {sample.event_count} events | {sample.channel_count} channels",
            6000,
        )

    def _update_inspector(self, sample: SampleData) -> None:
        self.inspector_panel.set_file_info(
            file_name=sample.file_name,
            events=str(sample.event_count),
            channels=str(sample.channel_count),
            active_gate="All events",
        )
        self.inspector_panel.set_displayed_points(None, None)

    def _configure_axis_selectors(self, sample: SampleData) -> None:
        channel_names = [channel.display_name for channel in sample.channels]

        try:
            x_idx, y_idx = choose_default_axes(sample)
        except ValueError:
            x_idx, y_idx = 0, 0

        self.inspector_panel.set_channels(channel_names, x_index=x_idx, y_index=y_idx)
        self.inspector_panel.set_statistics_channels(channel_names, selected_channel_index=x_idx)
        self._refresh_statistics_population_options()

    def _refresh_statistics_population_options(self) -> None:
        if self.current_sample is None:
            self.inspector_panel.clear_statistics()
            self._clear_statistics_results()
            return

        population_options: list[tuple[str, int | None]] = [("All events", None)]
        for index, gate in enumerate(self.gates):
            population_options.append((gate.name, index))

        selected_gate_index = self.gates.index(self.active_gate) if self.active_gate in self.gates else None
        self.inspector_panel.set_statistics_populations(
            population_options,
            selected_gate_index=selected_gate_index,
        )

    def _clear_statistics_results(self) -> None:
        self._latest_statistics = []
        self._latest_statistics_population_name = ""
        self._latest_statistics_channel_name = ""
        self.inspector_panel.set_statistics_results([])

    def _population_from_statistics_selection(
        self,
    ) -> tuple[str, np.ndarray, np.ndarray | None] | None:
        if self.current_sample is None:
            return None

        gate_index = self.inspector_panel.current_statistics_population_index()
        if gate_index is None:
            return (
                "All events",
                np.ones(self.current_sample.event_count, dtype=bool),
                np.ones(self.current_sample.event_count, dtype=bool),
            )

        if gate_index < 0 or gate_index >= len(self.gates):
            return None

        gate = self.gates[gate_index]
        parent_mask = self._mask_for_population_name(gate.parent_name)
        return gate.name, gate.full_mask, parent_mask

    def _mask_for_population_name(self, population_name: str) -> np.ndarray | None:
        if self.current_sample is None:
            return None

        if population_name == "All events":
            return np.ones(self.current_sample.event_count, dtype=bool)

        for gate in self.gates:
            if gate.name == population_name:
                return gate.full_mask
        return None

    def _children_of_population(
        self,
        population_name: str,
    ) -> list[RectangleGate | RangeGate | PolygonGate | CircleGate]:
        return [gate for gate in self.gates if gate.parent_name == population_name]

    def _gate_depth(self, gate: RectangleGate | RangeGate | PolygonGate | CircleGate) -> int:
        depth = 0
        current_parent = gate.parent_name
        while current_parent != "All events":
            parent_gate = next((candidate for candidate in self.gates if candidate.name == current_parent), None)
            if parent_gate is None:
                break
            depth += 1
            current_parent = parent_gate.parent_name
        return depth

    def _gate_list_label(self, gate: RectangleGate | RangeGate | PolygonGate | CircleGate) -> str:
        depth = self._gate_depth(gate)
        indent = "  " * depth
        return f"{indent}{gate.name} <- {gate.parent_name} | {gate.event_count:,} events ({gate.percentage_parent:.2f}% parent, {gate.percentage_total:.2f}% total)"

    def _update_population_context_labels(self) -> None:
        current_name = self.current_population_name()
        if self.active_gate is None:
            origin_name = "Root population"
        else:
            origin_name = self.active_gate.parent_name

        child_names = [gate.name for gate in self._children_of_population(current_name)]
        self.sample_panel.set_population_context(origin_name, child_names)

    def _refresh_gate_list_labels(self) -> None:
        for gate_index, gate in enumerate(self.gates):
            self.sample_panel.update_gate(
                gate_index,
                self._gate_list_label(gate),
                gate.color_hex,
            )

    def current_population_mask(self) -> np.ndarray | None:
        if self.current_sample is None:
            return None

        if self.active_gate is None:
            return np.ones(self.current_sample.event_count, dtype=bool)

        return self.active_gate.full_mask

    def current_population_name(self) -> str:
        if self.active_gate is None:
            return "All events"
        return self.active_gate.name

    def current_population_color(self) -> str:
        if self.active_gate is None:
            return "#466ebe"
        return self.active_gate.color_hex

    def clear_loaded_sample(self) -> None:
        self.current_sample = None
        self.gates = []
        self.active_gate = None

        self.sample_panel.reset_samples()
        self.sample_panel.reset_gates()
        self._update_population_context_labels()
        self.inspector_panel.set_file_info()
        self.inspector_panel.set_displayed_points(None, None)
        self.inspector_panel.set_gate_editor_state(None, None)
        self.inspector_panel.clear_channels()
        self.inspector_panel.clear_statistics()
        self._clear_statistics_results()
        self.plot_panel.clear_all_rois()
        self.plot_panel.show_placeholder_data()

    def remove_selected_sample(self) -> None:
        if self.current_sample is None or self.sample_panel.sample_list.currentRow() < 0:
            self.statusBar().showMessage("No sample selected", 3000)
            return

        removed_name = self.current_sample.file_name
        self.clear_loaded_sample()
        self.statusBar().showMessage(f"Removed {removed_name}", 4000)

    def on_sample_selection_changed(self, row: int) -> None:
        if row < 0:
            return

        # The current app state supports a single active sample.
        if row > 0:
            self.sample_panel.sample_list.setCurrentRow(0)
            self.statusBar().showMessage(
                "CytoDraft currently supports one loaded sample at a time",
                4000,
            )

    def redraw_current_plot(self, *, show_status: bool = True) -> None:
        if self.current_sample is None:
            return

        mode = self.inspector_panel.current_plot_mode()
        x_idx, y_idx = self.inspector_panel.current_axes()

        if mode == "histogram":
            self.plot_histogram(x_idx, show_status=show_status)
        else:
            self.plot_scatter(x_idx, y_idx, show_status=show_status)

    def plot_scatter(self, x_idx: int, y_idx: int, *, show_status: bool = True) -> None:
        if self.current_sample is None:
            return

        sample = self.current_sample
        if x_idx < 0 or y_idx < 0:
            return
        if x_idx >= sample.channel_count or y_idx >= sample.channel_count:
            return

        population_mask = self.current_population_mask()
        if population_mask is None:
            return

        raw_x = sample.events[population_mask, x_idx]
        raw_y = sample.events[population_mask, y_idx]

        x_scale, y_scale = self.inspector_panel.current_scales()

        x = apply_scale(raw_x, x_scale)
        y = apply_scale(raw_y, y_scale)

        finite_mask = np.isfinite(x) & np.isfinite(y)
        x = x[finite_mask]
        y = y[finite_mask]

        x_label = axis_label(sample.channel_label(x_idx), x_scale)
        y_label = axis_label(sample.channel_label(y_idx), y_scale)

        if len(x) == 0 or len(y) == 0:
            self.plot_panel.show_empty_message("No plottable events under current axis scales")
            self.inspector_panel.set_displayed_points(0, int(population_mask.sum()))
            if show_status:
                self.statusBar().showMessage("No plottable events under current axis scales", 4000)
            return

        limit_enabled, max_points = self.inspector_panel.sampling_settings()
        display_limit = max_points if limit_enabled else None
        subpopulation_overlays: list[tuple[np.ndarray, np.ndarray, str]] = []

        if self.inspector_panel.show_subpopulations_enabled():
            current_name = self.current_population_name()
            for child_gate in self._children_of_population(current_name):
                child_local_mask = child_gate.full_mask[population_mask]
                if len(child_local_mask) != len(finite_mask):
                    continue
                child_display_mask = child_local_mask[finite_mask]
                if not np.any(child_display_mask):
                    continue
                subpopulation_overlays.append(
                    (
                        x[child_display_mask],
                        y[child_display_mask],
                        child_gate.color_hex,
                    )
                )

        displayed_count, total_count = self.plot_panel.plot_scatter(
            x,
            y,
            x_label,
            y_label,
            title=f"{sample.file_name} | {self.current_population_name()} | {y_label} vs {x_label}",
            max_points=display_limit,
            selected_mask=None,
            point_color=self.current_population_color(),
            subpopulation_overlays=subpopulation_overlays,
        )

        x_min, x_max, y_min, y_max = self.inspector_panel.current_view_limits()
        if any(v is not None for v in (x_min, x_max, y_min, y_max)):
            self.plot_panel.set_manual_ranges(
                x_min=x_min,
                x_max=x_max,
                y_min=y_min,
                y_max=y_max,
            )
        else:
            self.plot_panel.auto_range()

        self.inspector_panel.set_displayed_points(displayed_count, total_count)

        if show_status:
            suffix = f"{displayed_count:,}/{total_count:,} displayed"
            self.statusBar().showMessage(
                f"Population: {self.current_population_name()} | Scatter | X: {x_label} | Y: {y_label} | {suffix}",
                4000,
            )

    def plot_histogram(self, x_idx: int, *, show_status: bool = True) -> None:
        if self.current_sample is None:
            return

        sample = self.current_sample
        if x_idx < 0 or x_idx >= sample.channel_count:
            return

        population_mask = self.current_population_mask()
        if population_mask is None:
            return

        raw_x = sample.events[population_mask, x_idx]
        x_scale, _ = self.inspector_panel.current_scales()
        x = apply_scale(raw_x, x_scale)
        x = x[np.isfinite(x)]

        x_label = axis_label(sample.channel_label(x_idx), x_scale)

        if len(x) == 0:
            self.plot_panel.show_empty_message("No plottable events under current axis scales")
            self.inspector_panel.set_displayed_points(0, int(population_mask.sum()))
            if show_status:
                self.statusBar().showMessage("No plottable events under current axis scales", 4000)
            return

        displayed_count, total_count = self.plot_panel.plot_histogram(
            x,
            x_label,
            title=f"{sample.file_name} | {self.current_population_name()} | Histogram of {x_label}",
        )

        x_min, x_max, y_min, y_max = self.inspector_panel.current_view_limits()
        if any(v is not None for v in (x_min, x_max, y_min, y_max)):
            self.plot_panel.set_manual_ranges(
                x_min=x_min,
                x_max=x_max,
                y_min=y_min,
                y_max=y_max,
            )
        else:
            self.plot_panel.auto_range()

        self.inspector_panel.set_displayed_points(displayed_count, total_count)

        if show_status:
            suffix = f"{displayed_count:,}/{total_count:,} displayed"
            self.statusBar().showMessage(
                f"Population: {self.current_population_name()} | Histogram | Channel: {x_label} | {suffix}",
                4000,
            )

    def on_axes_changed(self, x_idx: int, y_idx: int) -> None:
        del x_idx, y_idx
        self.redraw_current_plot()

    def on_plot_mode_changed(self, mode: str) -> None:
        self.plot_panel.clear_all_rois()
        self.redraw_current_plot()
        self.statusBar().showMessage(f"Plot mode set to {mode}", 3000)

    def on_sampling_changed(self, enabled: bool, max_points: int) -> None:
        del enabled, max_points
        self.redraw_current_plot()

    def on_view_settings_changed(self) -> None:
        self.redraw_current_plot()

    def on_auto_range_requested(self) -> None:
        self.inspector_panel.clear_view_limits()
        self.redraw_current_plot()

    def on_gate_selection_changed(self, row: int) -> None:
        if self.current_sample is None:
            return

        self.plot_panel.clear_all_rois()

        if row <= 0:
            self.active_gate = None
            self.inspector_panel.set_active_gate("All events")
            self.inspector_panel.set_gate_editor_state(None, None)
        else:
            gate_index = row - 1
            if gate_index >= len(self.gates):
                return
            self.active_gate = self.gates[gate_index]
            self.inspector_panel.set_active_gate(self.active_gate.name)
            self.inspector_panel.set_gate_editor_state(
                self.active_gate.name,
                self.active_gate.color_hex,
            )

        self._refresh_statistics_population_options()
        self._update_population_context_labels()

        self.redraw_current_plot(show_status=False)

        if self.active_gate is None:
            self.statusBar().showMessage("Focused on All events", 4000)
        else:
            self.statusBar().showMessage(
                f"Focused on {self.active_gate.name}: {self.active_gate.event_count:,} events",
                4000,
            )

    def on_create_gate(self) -> None:
        if self.current_sample is None:
            self.statusBar().showMessage("Load an FCS file before creating a gate", 4000)
            return

        mode = self.inspector_panel.current_plot_mode()
        if mode == "histogram":
            created = self.plot_panel.create_range_region()
            draft_name = f"Draft range on {self.current_population_name()}"
        else:
            scatter_gate_type = self.inspector_panel.current_scatter_gate_type()
            if scatter_gate_type == "polygon":
                created = self.plot_panel.create_polygon_roi()
                draft_name = f"Draft polygon on {self.current_population_name()}"
            elif scatter_gate_type == "circle":
                created = self.plot_panel.create_circle_roi()
                draft_name = f"Draft circle on {self.current_population_name()}"
            else:
                created = self.plot_panel.create_rectangle_roi()
                draft_name = f"Draft rectangle on {self.current_population_name()}"

        if not created:
            self.statusBar().showMessage("Could not create gate on the current plot", 4000)
            return

        self.inspector_panel.set_active_gate(draft_name)
        self.statusBar().showMessage(
            "Gate ROI created. Adjust it and then click Apply gate.",
            5000,
        )

    def on_apply_gate(self) -> None:
        if self.current_sample is None:
            self.statusBar().showMessage("No sample loaded", 4000)
            return

        mode = self.inspector_panel.current_plot_mode()
        if mode == "histogram":
            self._apply_range_gate()
            return

        polygon_points = self.plot_panel.polygon_roi_points()
        if polygon_points is not None:
            self._apply_polygon_gate()
            return

        circle_geometry = self.plot_panel.circle_roi_geometry()
        if circle_geometry is not None:
            self._apply_circle_gate()
        else:
            self._apply_rectangle_gate()

    def prompt_for_gate_details(
        self,
        *,
        initial_name: str,
        initial_color: str,
        title: str,
    ) -> tuple[str, str] | None:
        gate_name, accepted = QInputDialog.getText(
            self,
            title,
            "Gate name:",
            text=initial_name,
        )
        if not accepted:
            return None

        normalized_name = gate_name.strip()
        if not normalized_name:
            QMessageBox.warning(self, title, "Gate name cannot be empty.")
            return None

        color = QColorDialog.getColor(
            QColor(initial_color),
            self,
            f"{title}: gate color",
        )
        if not color.isValid():
            return None

        return normalized_name, color.name().lower()

    def _apply_rectangle_gate(self) -> None:
        if self.current_sample is None:
            return

        bounds = self.plot_panel.rectangle_roi_bounds()
        if bounds is None:
            self.statusBar().showMessage("Create a rectangle gate first", 4000)
            return

        x_idx, y_idx = self.inspector_panel.current_axes()
        sample = self.current_sample

        parent_mask = self.current_population_mask()
        if parent_mask is None:
            self.statusBar().showMessage("No active population available", 4000)
            return

        parent_count = int(parent_mask.sum())
        if parent_count == 0:
            self.statusBar().showMessage("The active population is empty", 4000)
            return

        x_scale, y_scale = self.inspector_panel.current_scales()
        x = apply_scale(sample.events[:, x_idx], x_scale)
        y = apply_scale(sample.events[:, y_idx], y_scale)

        x_min, x_max, y_min, y_max = bounds
        full_mask = rectangle_mask_from_parent(
            x,
            y,
            parent_mask,
            x_min=x_min,
            x_max=x_max,
            y_min=y_min,
            y_max=y_max,
        )

        event_count = int(full_mask.sum())
        total_count = sample.event_count
        percentage_parent = (event_count / parent_count * 100.0) if parent_count else 0.0
        percentage_total = (event_count / total_count * 100.0) if total_count else 0.0

        prompted_details = self.prompt_for_gate_details(
            initial_name=f"Gate {len(self.gates) + 1}",
            initial_color=DEFAULT_GATE_COLOR,
            title="Apply rectangle gate",
        )
        if prompted_details is None:
            self.statusBar().showMessage("Gate creation cancelled", 3000)
            return

        gate_name, gate_color = prompted_details
        gate = RectangleGate(
            name=gate_name,
            parent_name=self.current_population_name(),
            x_channel_index=x_idx,
            y_channel_index=y_idx,
            x_label=sample.channel_label(x_idx),
            y_label=sample.channel_label(y_idx),
            x_min=min(x_min, x_max),
            x_max=max(x_min, x_max),
            y_min=min(y_min, y_max),
            y_max=max(y_min, y_max),
            event_count=event_count,
            percentage_parent=percentage_parent,
            percentage_total=percentage_total,
            full_mask=full_mask,
            color_hex=gate_color,
        )

        self._store_and_select_new_gate(gate)
        self.statusBar().showMessage(
            f"Applied {gate.name} on {gate.parent_name}: "
            f"{event_count:,} events ({percentage_parent:.2f}% parent, {percentage_total:.2f}% total)",
            6000,
        )

    def _apply_polygon_gate(self) -> None:
        if self.current_sample is None:
            return

        vertices = self.plot_panel.polygon_roi_points()
        if vertices is None or len(vertices) < 3:
            self.statusBar().showMessage("Create a polygon gate first", 4000)
            return

        x_idx, y_idx = self.inspector_panel.current_axes()
        sample = self.current_sample

        parent_mask = self.current_population_mask()
        if parent_mask is None:
            self.statusBar().showMessage("No active population available", 4000)
            return

        parent_count = int(parent_mask.sum())
        if parent_count == 0:
            self.statusBar().showMessage("The active population is empty", 4000)
            return

        x_scale, y_scale = self.inspector_panel.current_scales()
        x = apply_scale(sample.events[:, x_idx], x_scale)
        y = apply_scale(sample.events[:, y_idx], y_scale)

        full_mask = polygon_mask_from_parent(
            x,
            y,
            parent_mask,
            vertices,
        )

        event_count = int(full_mask.sum())
        total_count = sample.event_count
        percentage_parent = (event_count / parent_count * 100.0) if parent_count else 0.0
        percentage_total = (event_count / total_count * 100.0) if total_count else 0.0

        prompted_details = self.prompt_for_gate_details(
            initial_name=f"Gate {len(self.gates) + 1}",
            initial_color=DEFAULT_GATE_COLOR,
            title="Apply polygon gate",
        )
        if prompted_details is None:
            self.statusBar().showMessage("Gate creation cancelled", 3000)
            return

        gate_name, gate_color = prompted_details
        gate = PolygonGate(
            name=gate_name,
            parent_name=self.current_population_name(),
            x_channel_index=x_idx,
            y_channel_index=y_idx,
            x_label=sample.channel_label(x_idx),
            y_label=sample.channel_label(y_idx),
            vertices=[(float(px), float(py)) for px, py in vertices],
            event_count=event_count,
            percentage_parent=percentage_parent,
            percentage_total=percentage_total,
            full_mask=full_mask,
            color_hex=gate_color,
        )

        self._store_and_select_new_gate(gate)
        self.statusBar().showMessage(
            f"Applied {gate.name} on {gate.parent_name}: "
            f"{event_count:,} events ({percentage_parent:.2f}% parent, {percentage_total:.2f}% total)",
            6000,
        )

    def _apply_circle_gate(self) -> None:
        if self.current_sample is None:
            return

        geometry = self.plot_panel.circle_roi_geometry()
        if geometry is None:
            self.statusBar().showMessage("Create a circle gate first", 4000)
            return

        x_idx, y_idx = self.inspector_panel.current_axes()
        sample = self.current_sample

        parent_mask = self.current_population_mask()
        if parent_mask is None:
            self.statusBar().showMessage("No active population available", 4000)
            return

        parent_count = int(parent_mask.sum())
        if parent_count == 0:
            self.statusBar().showMessage("The active population is empty", 4000)
            return

        x_scale, y_scale = self.inspector_panel.current_scales()
        x = apply_scale(sample.events[:, x_idx], x_scale)
        y = apply_scale(sample.events[:, y_idx], y_scale)

        center_x, center_y, radius = geometry
        full_mask = circle_mask_from_parent(
            x,
            y,
            parent_mask,
            center_x=center_x,
            center_y=center_y,
            radius=radius,
        )

        event_count = int(full_mask.sum())
        total_count = sample.event_count
        percentage_parent = (event_count / parent_count * 100.0) if parent_count else 0.0
        percentage_total = (event_count / total_count * 100.0) if total_count else 0.0

        prompted_details = self.prompt_for_gate_details(
            initial_name=f"Gate {len(self.gates) + 1}",
            initial_color=DEFAULT_GATE_COLOR,
            title="Apply circle gate",
        )
        if prompted_details is None:
            self.statusBar().showMessage("Gate creation cancelled", 3000)
            return

        gate_name, gate_color = prompted_details
        gate = CircleGate(
            name=gate_name,
            parent_name=self.current_population_name(),
            x_channel_index=x_idx,
            y_channel_index=y_idx,
            x_label=sample.channel_label(x_idx),
            y_label=sample.channel_label(y_idx),
            center_x=center_x,
            center_y=center_y,
            radius=radius,
            event_count=event_count,
            percentage_parent=percentage_parent,
            percentage_total=percentage_total,
            full_mask=full_mask,
            color_hex=gate_color,
        )

        self._store_and_select_new_gate(gate)
        self.statusBar().showMessage(
            f"Applied {gate.name} on {gate.parent_name}: "
            f"{event_count:,} events ({percentage_parent:.2f}% parent, {percentage_total:.2f}% total)",
            6000,
        )

    def _apply_range_gate(self) -> None:
        if self.current_sample is None:
            return

        bounds = self.plot_panel.range_region_bounds()
        if bounds is None:
            self.statusBar().showMessage("Create a range gate first", 4000)
            return

        x_idx, _ = self.inspector_panel.current_axes()
        sample = self.current_sample

        parent_mask = self.current_population_mask()
        if parent_mask is None:
            self.statusBar().showMessage("No active population available", 4000)
            return

        parent_count = int(parent_mask.sum())
        if parent_count == 0:
            self.statusBar().showMessage("The active population is empty", 4000)
            return

        x_scale, _ = self.inspector_panel.current_scales()
        x = apply_scale(sample.events[:, x_idx], x_scale)

        x_min, x_max = bounds
        full_mask = range_mask_from_parent(
            x,
            parent_mask,
            x_min=x_min,
            x_max=x_max,
        )

        event_count = int(full_mask.sum())
        total_count = sample.event_count
        percentage_parent = (event_count / parent_count * 100.0) if parent_count else 0.0
        percentage_total = (event_count / total_count * 100.0) if total_count else 0.0

        prompted_details = self.prompt_for_gate_details(
            initial_name=f"Gate {len(self.gates) + 1}",
            initial_color=DEFAULT_GATE_COLOR,
            title="Apply range gate",
        )
        if prompted_details is None:
            self.statusBar().showMessage("Gate creation cancelled", 3000)
            return

        gate_name, gate_color = prompted_details
        gate = RangeGate(
            name=gate_name,
            parent_name=self.current_population_name(),
            channel_index=x_idx,
            channel_label=sample.channel_label(x_idx),
            x_min=min(x_min, x_max),
            x_max=max(x_min, x_max),
            event_count=event_count,
            percentage_parent=percentage_parent,
            percentage_total=percentage_total,
            full_mask=full_mask,
            color_hex=gate_color,
        )

        self._store_and_select_new_gate(gate)
        self.statusBar().showMessage(
            f"Applied {gate.name} on {gate.parent_name}: "
            f"{event_count:,} events ({percentage_parent:.2f}% parent, {percentage_total:.2f}% total)",
            6000,
        )

    def _store_and_select_new_gate(
        self,
        gate: RectangleGate | RangeGate | PolygonGate | CircleGate,
    ) -> None:
        self.gates.append(gate)
        self._clear_statistics_results()
        self._refresh_statistics_population_options()
        self.sample_panel.add_gate(self._gate_list_label(gate), select=False)
        self._refresh_gate_list_labels()
        new_row = len(self.gates)
        self.sample_panel.select_gate_row(new_row)

    def on_rename_active_gate(self, raw_name: str) -> None:
        if self.active_gate is None:
            return

        new_name = raw_name.strip()
        if not new_name:
            self.inspector_panel.set_gate_editor_state(
                self.active_gate.name,
                self.active_gate.color_hex,
            )
            self.statusBar().showMessage("Gate name cannot be empty", 3000)
            return

        if new_name == self.active_gate.name:
            return

        old_name = self.active_gate.name
        self.active_gate.name = new_name
        for gate in self.gates:
            if gate.parent_name == old_name:
                gate.parent_name = new_name
        self._refresh_gate_list_labels()
        self.inspector_panel.set_active_gate(self.active_gate.name)
        self.inspector_panel.set_gate_editor_state(
            self.active_gate.name,
            self.active_gate.color_hex,
        )
        self._clear_statistics_results()
        self._refresh_statistics_population_options()
        self._update_population_context_labels()
        self.redraw_current_plot(show_status=False)
        self.statusBar().showMessage(f"Renamed gate to {self.active_gate.name}", 4000)

    def on_recolor_active_gate(self) -> None:
        if self.active_gate is None:
            self.statusBar().showMessage("Select a gate before changing its color", 3000)
            return

        color = QColorDialog.getColor(
            QColor(self.active_gate.color_hex),
            self,
            f"Select color for {self.active_gate.name}",
        )
        if not color.isValid():
            return

        self.active_gate.color_hex = color.name().lower()
        gate_index = self.gates.index(self.active_gate)
        self.sample_panel.update_gate(
            gate_index,
            self._gate_list_label(self.active_gate),
            self.active_gate.color_hex,
        )
        self.inspector_panel.set_gate_editor_state(
            self.active_gate.name,
            self.active_gate.color_hex,
        )
        self.statusBar().showMessage(
            f"Changed {self.active_gate.name} color to {self.active_gate.color_hex}",
            4000,
        )
        self.redraw_current_plot(show_status=False)

    def on_rename_gate_from_context(self, gate_index: int) -> None:
        gate = self.gates[gate_index]
        gate_name, accepted = QInputDialog.getText(
            self,
            "Rename gate",
            "Gate name:",
            text=gate.name,
        )
        if not accepted:
            return

        self.active_gate = gate
        self.on_rename_active_gate(gate_name)

    def on_recolor_gate_from_context(self, gate_index: int) -> None:
        self.active_gate = self.gates[gate_index]
        self.on_recolor_active_gate()

    def on_delete_gate_from_context(self, gate_index: int) -> None:
        gate = self.gates[gate_index]
        answer = QMessageBox.question(
            self,
            "Delete gate",
            f"Delete {gate.name}?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        names_to_delete = {gate.name}
        changed = True
        while changed:
            changed = False
            for candidate in self.gates:
                if candidate.parent_name in names_to_delete and candidate.name not in names_to_delete:
                    names_to_delete.add(candidate.name)
                    changed = True

        self.gates = [candidate for candidate in self.gates if candidate.name not in names_to_delete]
        self.sample_panel.reset_gates()
        for remaining_gate in self.gates:
            self.sample_panel.add_gate(self._gate_list_label(remaining_gate), select=False)
        self.active_gate = None
        self._clear_statistics_results()
        self.sample_panel.select_gate_row(0)
        self.inspector_panel.set_active_gate("All events")
        self.inspector_panel.set_gate_editor_state(None, None)
        self._refresh_statistics_population_options()
        self._update_population_context_labels()
        self.redraw_current_plot(show_status=False)
        if len(names_to_delete) == 1:
            self.statusBar().showMessage(f"Deleted {gate.name}", 4000)
        else:
            self.statusBar().showMessage(
                f"Deleted {gate.name} and {len(names_to_delete) - 1} descendant gates",
                4000,
            )

    def on_clear_draft_gate(self) -> None:
        self.plot_panel.clear_all_rois()
        self.inspector_panel.set_active_gate(self.current_population_name())
        self.statusBar().showMessage("Draft gate cleared", 4000)

    def on_calculate_statistics(self) -> None:
        if self.current_sample is None:
            self.statusBar().showMessage("Load an FCS file before calculating statistics", 4000)
            return

        population_selection = self._population_from_statistics_selection()
        if population_selection is None:
            self.statusBar().showMessage("Select a valid population for statistics", 4000)
            return

        statistic_keys = self.inspector_panel.selected_statistics()
        if not statistic_keys:
            self.statusBar().showMessage("Select at least one statistic", 4000)
            return

        channel_index = self.inspector_panel.current_statistics_channel_index()
        if channel_index < 0 or channel_index >= self.current_sample.channel_count:
            self.statusBar().showMessage("Select a valid channel for statistics", 4000)
            return

        population_name, population_mask, parent_mask = population_selection
        channel_name = self.current_sample.channel_label(channel_index)
        channel_values = self.current_sample.events[population_mask, channel_index]
        statistics = calculate_population_statistics(
            channel_values,
            population_mask,
            total_event_count=self.current_sample.event_count,
            parent_mask=parent_mask,
            statistics=statistic_keys,
        )

        rows = [(result.label, self._format_statistic_value(result)) for result in statistics]
        self.inspector_panel.set_statistics_results(rows)
        self._latest_statistics = statistics
        self._latest_statistics_population_name = population_name
        self._latest_statistics_channel_name = channel_name
        self.statusBar().showMessage(
            f"Calculated {len(statistics)} statistics for {population_name} on {channel_name}",
            5000,
        )

    def on_export_statistics(self) -> None:
        if self.current_sample is None:
            self.statusBar().showMessage("No sample loaded", 4000)
            return

        if not self._latest_statistics:
            self.statusBar().showMessage("Calculate statistics before exporting", 4000)
            return

        default_name = (
            f"{self.current_sample.file_path.stem}_"
            f"{self._latest_statistics_population_name.lower().replace(' ', '_')}_statistics.csv"
        )
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export statistics",
            default_name,
            "CSV files (*.csv);;All files (*)",
        )

        if not file_path:
            self.statusBar().showMessage("Statistics export cancelled", 3000)
            return

        try:
            output_path = export_population_statistics_to_csv(
                sample_name=self.current_sample.file_name,
                population_name=self._latest_statistics_population_name,
                channel_name=self._latest_statistics_channel_name,
                statistics=self._latest_statistics,
                output_path=file_path,
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Statistics export failed",
                f"Could not export statistics.\n\nError:\n{exc}",
            )
            self.statusBar().showMessage("Failed to export statistics", 5000)
            return

        self.statusBar().showMessage(f"Exported statistics to {output_path}", 6000)

    @staticmethod
    def _format_statistic_value(result: StatisticResult) -> str:
        if result.key == "event_count":
            return f"{int(round(result.value)):,}"
        if np.isnan(result.value):
            return "NaN"
        return f"{result.value:.4f}"

    def on_export_active_gate(self) -> None:
        if self.current_sample is None:
            self.statusBar().showMessage("No sample loaded", 4000)
            return

        if self.active_gate is None:
            self.statusBar().showMessage("Select a gate before exporting", 4000)
            return

        default_name = (
            f"{self.current_sample.file_path.stem}_"
            f"{self.active_gate.name.lower().replace(' ', '_')}.csv"
        )

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export active gate",
            default_name,
            "CSV files (*.csv);;FCS files (*.fcs);;All files (*)",
        )

        if not file_path:
            self.statusBar().showMessage("Export cancelled", 3000)
            return

        try:
            suffix = file_path.lower()
            if suffix.endswith(".fcs"):
                output_path = export_masked_events_to_fcs(
                    self.current_sample,
                    self.active_gate.full_mask,
                    file_path,
                )
            else:
                output_path = export_masked_events_to_csv(
                    self.current_sample,
                    self.active_gate.full_mask,
                    file_path,
                )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Export failed",
                f"Could not export active gate.\n\nError:\n{exc}",
            )
            self.statusBar().showMessage("Failed to export gate", 5000)
            return

        self.statusBar().showMessage(
            f"Exported {self.active_gate.name} to {output_path}",
            6000,
        )

    def show_about_dialog(self) -> None:
        QMessageBox.about(
            self,
            "About CytoDraft",
            (
                "CytoDraft\n\n"
                "Open-source desktop application for cytometry data analysis.\n"
                "Current stage: scatter/histogram plotting + hierarchical rectangle/range/polygon gating."
            ),
        )
