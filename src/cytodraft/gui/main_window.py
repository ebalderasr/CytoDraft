from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QFileDialog, QMainWindow, QMessageBox, QSplitter

from cytodraft.core.export import export_masked_events_to_csv
from cytodraft.core.fcs_reader import choose_default_axes
from cytodraft.core.gating import rectangle_mask_from_parent, range_mask_from_parent
from cytodraft.core.transforms import apply_scale, axis_label
from cytodraft.gui.panels import InspectorPanel, SamplePanel
from cytodraft.gui.plot_widget import CytometryPlotWidget
from cytodraft.models.gate import RangeGate, RectangleGate
from cytodraft.models.sample import SampleData
from cytodraft.services.sample_service import SampleService


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("CytoDraft")
        self.resize(1400, 850)

        self.sample_service = SampleService()
        self.current_sample: SampleData | None = None
        self.gates: list[RectangleGate | RangeGate] = []
        self.active_gate: RectangleGate | RangeGate | None = None

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

        self.export_gate_action = QAction("Export active gate to CSV...", self)
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
        self.sample_panel.gate_selection_changed.connect(self.on_gate_selection_changed)
        self.inspector_panel.axes_changed.connect(self.on_axes_changed)
        self.inspector_panel.plot_mode_changed.connect(self.on_plot_mode_changed)
        self.inspector_panel.sampling_changed.connect(self.on_sampling_changed)
        self.inspector_panel.view_settings_changed.connect(self.on_view_settings_changed)
        self.inspector_panel.auto_range_requested.connect(self.on_auto_range_requested)
        self.inspector_panel.create_gate_requested.connect(self.on_create_gate)
        self.inspector_panel.apply_gate_requested.connect(self.on_apply_gate)
        self.inspector_panel.clear_gate_requested.connect(self.on_clear_draft_gate)
        self.inspector_panel.export_gate_requested.connect(self.on_export_active_gate)

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

        self.sample_panel.add_sample(sample.file_name)
        self.sample_panel.reset_gates()

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

        displayed_count, total_count = self.plot_panel.plot_scatter(
            x,
            y,
            x_label,
            y_label,
            title=f"{sample.file_name} | {self.current_population_name()} | {y_label} vs {x_label}",
            max_points=display_limit,
            selected_mask=None,
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
        else:
            gate_index = row - 1
            if gate_index >= len(self.gates):
                return
            self.active_gate = self.gates[gate_index]
            self.inspector_panel.set_active_gate(self.active_gate.name)

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
        else:
            self._apply_rectangle_gate()

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

        gate_name = f"Gate {len(self.gates) + 1}"
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

        gate_name = f"Gate {len(self.gates) + 1}"
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
        )

        self._store_and_select_new_gate(gate)
        self.statusBar().showMessage(
            f"Applied {gate.name} on {gate.parent_name}: "
            f"{event_count:,} events ({percentage_parent:.2f}% parent, {percentage_total:.2f}% total)",
            6000,
        )

    def _store_and_select_new_gate(self, gate: RectangleGate | RangeGate) -> None:
        self.gates.append(gate)
        self.sample_panel.add_gate(gate.label, select=False)
        new_row = len(self.gates)
        self.sample_panel.select_gate_row(new_row)

    def on_clear_draft_gate(self) -> None:
        self.plot_panel.clear_all_rois()
        self.inspector_panel.set_active_gate(self.current_population_name())
        self.statusBar().showMessage("Draft gate cleared", 4000)

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
            "Export active gate to CSV",
            default_name,
            "CSV files (*.csv);;All files (*)",
        )

        if not file_path:
            self.statusBar().showMessage("Export cancelled", 3000)
            return

        try:
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
                "Current stage: scatter/histogram plotting + hierarchical rectangle/range gating."
            ),
        )
