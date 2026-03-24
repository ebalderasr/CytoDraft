from __future__ import annotations

import numpy as np
from pathlib import Path
from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtGui import QAction, QColor, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QColorDialog,
    QFileDialog,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from cytodraft.core.export import (
    export_batch_statistics_to_csv,
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
from cytodraft.core.statistics import (
    CHANNEL_DEPENDENT_STATS,
    StatisticResult,
    calculate_population_statistics,
)
from cytodraft.core.transforms import apply_scale, axis_label
from cytodraft.gui.batch_export_dialog import BatchExportDialog
from cytodraft.gui.compensation_dialog import CompensationWindow
from cytodraft.gui.gate_toolbar import GateToolbar
from cytodraft.gui.panels import InspectorPanel, SamplePanel
from cytodraft.gui.sample_table_window import SampleTableWindow
from cytodraft.gui.plot_widget import (
    CytometryPlotWidget,
    HistogramGateOverlay,
    HistogramOverlay,
    ScatterGateOverlay,
)
from cytodraft.models.gate import (
    CircleGate,
    DEFAULT_GATE_COLOR,
    PolygonGate,
    RangeGate,
    RectangleGate,
)
from cytodraft.models.sample import SampleData
from cytodraft.core.workspace_io import WORKSPACE_EXTENSION, load_workspace, save_workspace
from cytodraft.models.workspace import (
    DEFAULT_GROUP_NAME,
    WorkspaceSample,
    WorkspaceState,
    COMPENSATION_GROUP_NAME,
)
from cytodraft.services.gate_service import GateService
from cytodraft.services.sample_service import SampleService
from cytodraft.services.statistics_service import StatisticsService

GateModel = RectangleGate | RangeGate | PolygonGate | CircleGate


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.setWindowTitle("CytoDraft")
        self.resize(1400, 850)
        self.setMinimumSize(960, 680)

        self.sample_service = SampleService()
        self.gate_service = GateService()
        self.statistics_service = StatisticsService()
        self.workspace = WorkspaceState()
        self.selected_group_name: str | None = None
        self.current_sample: SampleData | None = None
        self.gates: list[RectangleGate | RangeGate | PolygonGate | CircleGate] = []
        self.active_gate: RectangleGate | RangeGate | PolygonGate | CircleGate | None = None
        self._latest_statistics: list[StatisticResult] = []
        self._latest_statistics_population_name = ""
        self._latest_statistics_channel_name = ""
        self._workspace_path: Path | None = None

        self.sample_panel = SamplePanel()
        self.plot_panel = CytometryPlotWidget()
        self.gate_toolbar = GateToolbar()
        self.inspector_panel = InspectorPanel()
        self._sample_table_window: SampleTableWindow | None = None
        self._compensation_window: CompensationWindow | None = None

        self._build_ui()
        self._connect_signals()
        self._move_statistics_to_sample_manager()
        self._refresh_available_groups()
        self.setAcceptDrops(True)

        self.statusBar().showMessage("Ready")

    def _build_ui(self) -> None:
        plot_area = QWidget()
        plot_area.setObjectName("plotAreaCard")
        plot_area_layout = QVBoxLayout()
        plot_area_layout.setContentsMargins(10, 10, 10, 10)
        plot_area_layout.setSpacing(0)
        plot_area_layout.addWidget(self.gate_toolbar)
        plot_area_layout.addWidget(self.plot_panel)
        plot_area.setLayout(plot_area_layout)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self.sample_panel)
        splitter.addWidget(plot_area)
        splitter.addWidget(self.inspector_panel)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 5)
        splitter.setStretchFactor(2, 3)
        splitter.setSizes([340, 700, 340])

        self.setCentralWidget(splitter)
        self._create_menu()
        self._create_toolbar()

    def _create_menu(self) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("&File")

        self.open_action = QAction("Open FCS...", self)
        self.open_action.setShortcut("Ctrl+O")

        self.open_workspace_action = QAction("Open Workspace...", self)
        self.open_workspace_action.setShortcut("Ctrl+W")

        self.save_workspace_action = QAction("Save Workspace", self)
        self.save_workspace_action.setShortcut("Ctrl+S")
        self.save_workspace_action.setEnabled(False)

        self.save_workspace_as_action = QAction("Save Workspace As...", self)
        self.save_workspace_as_action.setShortcut("Ctrl+Shift+S")

        self.export_gate_action = QAction("Export active gate...", self)
        self.export_gate_action.setShortcut("Ctrl+E")

        self.exit_action = QAction("Exit", self)
        self.exit_action.setShortcut("Ctrl+Q")

        file_menu.addAction(self.open_action)
        file_menu.addAction(self.open_workspace_action)
        file_menu.addSeparator()
        file_menu.addAction(self.save_workspace_action)
        file_menu.addAction(self.save_workspace_as_action)
        file_menu.addSeparator()
        file_menu.addAction(self.export_gate_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)

        view_menu = menu_bar.addMenu("&View")
        self.sample_table_action = QAction("Sample Manager...", self)
        self.sample_table_action.setShortcut("Ctrl+T")
        self.sample_table_action.setToolTip("Open sample manager for samples, groups, and statistics")
        view_menu.addAction(self.sample_table_action)

        self.compensation_editor_action = QAction("Compensation...", self)
        self.compensation_editor_action.setShortcut("Ctrl+M")
        self.compensation_editor_action.setToolTip(
            "Manage compensation controls, edit the spillover matrix and verify visually"
        )
        view_menu.addAction(self.compensation_editor_action)

        help_menu = menu_bar.addMenu("&Help")
        self.about_action = QAction("About CytoDraft", self)
        help_menu.addAction(self.about_action)

    def _create_toolbar(self) -> None:
        toolbar: QToolBar = self.addToolBar("Main")
        toolbar.setObjectName("main_toolbar")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)

        toolbar.addAction(self.sample_table_action)
        toolbar.addAction(self.compensation_editor_action)

    def _move_statistics_to_sample_manager(self) -> None:
        for tab_index in range(self.inspector_panel.controls_tabs.count()):
            if self.inspector_panel.controls_tabs.tabText(tab_index) == "Statistics":
                self.inspector_panel.controls_tabs.removeTab(tab_index)
                break

    def _connect_signals(self) -> None:
        self.open_action.triggered.connect(self.open_fcs_dialog)
        self.open_workspace_action.triggered.connect(self.open_workspace_dialog)
        self.save_workspace_action.triggered.connect(self.save_workspace_dialog)
        self.save_workspace_as_action.triggered.connect(self.save_workspace_as_dialog)
        self.export_gate_action.triggered.connect(self.on_export_active_gate)
        self.exit_action.triggered.connect(self.close)
        self.about_action.triggered.connect(self.show_about_dialog)
        self.sample_table_action.triggered.connect(self.open_sample_table)
        self.compensation_editor_action.triggered.connect(self.open_compensation_editor)
        self.sample_panel.add_sample_button.clicked.connect(self.open_fcs_dialog)
        self.sample_panel.remove_sample_button.clicked.connect(self.remove_selected_sample)
        self.sample_panel.select_group_samples_requested.connect(self.on_select_group_samples)
        self.sample_panel.rename_group_requested.connect(self.on_rename_group)
        self.sample_panel.recolor_group_requested.connect(self.on_recolor_group)
        self.sample_panel.annotate_group_requested.connect(self.on_annotate_group)
        self.sample_panel.delete_group_requested.connect(self.on_delete_group)
        self.sample_panel.sample_selection_changed.connect(self.on_sample_selection_changed)
        self.sample_panel.edit_sample_requested.connect(self.on_edit_sample)
        self.sample_panel.add_sample_keyword_requested.connect(self.on_add_keyword_to_sample)
        self.sample_panel.edit_compensation_sample_requested.connect(self.on_edit_compensation_sample)
        self.sample_panel.assign_sample_group_requested.connect(self.on_assign_sample_group)
        self.sample_panel.assign_custom_sample_group_requested.connect(self.on_assign_custom_sample_group)
        self.sample_panel.apply_active_gate_to_group_requested.connect(self.on_apply_active_gate_to_group)
        self.sample_panel.apply_all_gates_to_group_requested.connect(self.on_apply_all_gates_to_group)
        self.sample_panel.apply_active_gate_to_all_requested.connect(self.on_apply_active_gate_to_all_samples)
        self.sample_panel.apply_all_gates_to_all_requested.connect(self.on_apply_all_gates_to_all_samples)
        self.sample_panel.gate_selection_changed.connect(self.on_gate_selection_changed)
        self.sample_panel.rename_gate_context_requested.connect(self.on_rename_gate_from_context)
        self.sample_panel.recolor_gate_context_requested.connect(self.on_recolor_gate_from_context)
        self.sample_panel.delete_gate_context_requested.connect(self.on_delete_gate_from_context)
        self.sample_panel.export_gate_context_requested.connect(self.on_export_gate_from_context)
        self.sample_panel.delete_samples_batch_requested.connect(self.on_delete_samples_batch)
        self.sample_panel.assign_samples_group_batch_requested.connect(self.on_assign_samples_group_batch)
        self.sample_panel.apply_active_gate_to_selected_requested.connect(self.on_apply_active_gate_to_selected)
        self.sample_panel.apply_all_gates_to_selected_requested.connect(self.on_apply_all_gates_to_selected)
        self.sample_panel.delete_gates_batch_requested.connect(self.on_delete_gates_batch)
        self.sample_panel.apply_gates_to_group_batch_requested.connect(self.on_apply_gates_to_group_batch)
        self.sample_panel.apply_gates_to_all_batch_requested.connect(self.on_apply_gates_to_all_batch)
        self.gate_toolbar.draw_requested.connect(self.on_create_gate)
        self.gate_toolbar.apply_requested.connect(self.on_apply_gate)
        self.gate_toolbar.clear_requested.connect(self.on_clear_draft_gate)
        self.inspector_panel.axes_changed.connect(self.on_axes_changed)
        self.inspector_panel.plot_mode_changed.connect(self.on_plot_mode_changed)
        self.inspector_panel.sampling_changed.connect(self.on_sampling_changed)
        self.inspector_panel.view_settings_changed.connect(self.on_view_settings_changed)
        self.inspector_panel.auto_range_requested.connect(self.on_auto_range_requested)
        self.inspector_panel.calculate_statistics_requested.connect(self.on_calculate_statistics)
        self.inspector_panel.export_statistics_requested.connect(self.on_export_statistics)
        self.inspector_panel.batch_export_statistics_requested.connect(self.on_batch_export_statistics)


    # ------------------------------------------------------------------
    # Sample Table window
    # ------------------------------------------------------------------

    def open_sample_table(self) -> None:
        """Open (or bring to front) the Sample Table window."""
        if self._sample_table_window is None or not self._sample_table_window.isVisible():
            self._sample_table_window = SampleTableWindow(
                self.workspace,
                self.gate_service,
                self.statistics_service,
                on_workspace_changed=self._on_workspace_changed_from_sample_manager,
                on_add_samples_requested=self.open_fcs_dialog_for_group,
                parent=self,
            )
        else:
            self._sample_table_window.refresh()
        self._sample_table_window.show()
        self._sample_table_window.raise_()
        self._sample_table_window.activateWindow()

    def open_compensation_editor(self) -> None:
        """Open (or bring to front) the Compensation Manager window."""
        if self._compensation_window is None or not self._compensation_window.isVisible():
            self._compensation_window = CompensationWindow(
                self.workspace,
                on_workspace_changed=self._on_compensation_workspace_changed,
                parent=self,
            )
            self._compensation_window.add_fcs_to_group_requested.connect(
                self.open_fcs_dialog_for_group
            )
        else:
            self._compensation_window.refresh()
        self._compensation_window.show()
        self._compensation_window.raise_()
        self._compensation_window.activateWindow()

    def _on_compensation_workspace_changed(self) -> None:
        self._sync_from_workspace()
        self._refresh_sample_list(select_active=True)
        self._refresh_sample_details()

    def _refresh_sample_table(self) -> None:
        """Refresh the Sample Table window if it is open."""
        if self._sample_table_window is not None and self._sample_table_window.isVisible():
            self._sample_table_window.refresh()

    def _on_workspace_changed_from_sample_manager(self) -> None:
        self._sync_from_workspace()
        self._clear_statistics_results()
        self._refresh_available_groups()
        self._refresh_sample_list(select_active=True)
        if self.current_sample is None:
            self.selected_group_name = None
            self.gates = []
            self.active_gate = None
            self.sample_panel.reset_samples()
            self.sample_panel.reset_gates()
            self._update_population_context_labels()
            self.inspector_panel.set_file_info()
            self.inspector_panel.set_displayed_points(None, None)
            self.inspector_panel.clear_channels()
            self.inspector_panel.clear_statistics()
            self.plot_panel.clear_all_rois()
            self.plot_panel.show_placeholder_data()
            self.gate_toolbar.set_drawing_active(False)
            return
        self._refresh_gate_panel()
        self._show_active_sample()

    # ------------------------------------------------------------------
    # FCS file loading
    # ------------------------------------------------------------------

    def open_fcs_dialog(self) -> None:
        target_group = self.selected_group_name
        self.open_fcs_dialog_for_group(target_group)

    def open_fcs_dialog_for_group(self, group_name: str | None) -> None:
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Open FCS files",
            "",
            "FCS files (*.fcs);;All files (*)",
        )

        if not file_paths:
            self.statusBar().showMessage("Open file cancelled", 3000)
            return

        self.load_samples(file_paths, group_name=group_name)

    def load_samples(self, file_paths: list[str], group_name: str | None = None) -> None:
        loaded_count = 0
        failed_files: list[tuple[str, str]] = []

        resolved_group_name = group_name.strip() if group_name is not None else DEFAULT_GROUP_NAME
        if not resolved_group_name:
            resolved_group_name = DEFAULT_GROUP_NAME

        for file_path in file_paths:
            try:
                sample = self.sample_service.load_sample(file_path)
            except Exception as exc:
                failed_files.append((file_path, str(exc)))
                continue

            self.workspace.add_sample(sample, group_name=resolved_group_name)
            loaded_count += 1

        if loaded_count == 0:
            if failed_files:
                QMessageBox.critical(
                    self,
                    "Failed to load FCS files",
                    "\n\n".join(f"{path}\n{error}" for path, error in failed_files),
                )
            self.statusBar().showMessage("Failed to load FCS files", 5000)
            return

        self.selected_group_name = resolved_group_name if group_name is not None or self.selected_group_name == resolved_group_name else self.selected_group_name
        if group_name is not None:
            self.selected_group_name = resolved_group_name
        self._sync_from_workspace()
        self._clear_statistics_results()
        self._refresh_available_groups()
        self._refresh_sample_list(select_active=True)
        self._refresh_gate_panel()
        self._show_active_sample()
        self._refresh_sample_table()

        if failed_files:
            QMessageBox.warning(
                self,
                "Some FCS files could not be loaded",
                "\n\n".join(f"{path}\n{error}" for path, error in failed_files),
            )
            self.statusBar().showMessage(
                f"Loaded {loaded_count} file(s); {len(failed_files)} failed",
                6000,
            )
            return

        self.statusBar().showMessage(
            f"Loaded {loaded_count} FCS file(s) into {resolved_group_name}",
            6000,
        )

    def load_sample(self, file_path: str, group_name: str | None = None) -> None:
        self.load_samples([file_path], group_name=group_name)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        mime_data = event.mimeData()
        if mime_data.hasUrls() and any(url.isLocalFile() and url.toLocalFile().lower().endswith(".fcs") for url in mime_data.urls()):
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        mime_data = event.mimeData()
        file_paths = [
            url.toLocalFile()
            for url in mime_data.urls()
            if url.isLocalFile() and url.toLocalFile().lower().endswith(".fcs")
        ]
        if not file_paths:
            event.ignore()
            return

        target_group = self.selected_group_name
        self.load_samples(file_paths, group_name=target_group)
        event.acceptProposedAction()

    def _active_workspace_sample(self) -> WorkspaceSample | None:
        return self.workspace.active_sample

    def _sync_from_workspace(self) -> None:
        workspace_sample = self._active_workspace_sample()
        if workspace_sample is None:
            self.current_sample = None
            self.gates = []
            self.active_gate = None
            return

        self.current_sample = workspace_sample.sample
        self.gates = workspace_sample.gates
        self.active_gate = next(
            (gate for gate in self.gates if gate.name == workspace_sample.active_gate_name),
            None,
        )

    def _refresh_sample_list(self, *, select_active: bool = False) -> None:
        active_index = self.workspace.active_sample_index
        with QSignalBlocker(self.sample_panel.sample_tree):
            self.sample_panel.reset_samples()
            for workspace_index, workspace_sample in enumerate(self.workspace.samples):
                group = self.workspace.groups.get(workspace_sample.group_name)
                group_color = group.color_hex if group is not None else "#5a6b7a"
                self.sample_panel.add_sample(
                    workspace_sample.display_name,
                    workspace_index,
                    group_color,
                    workspace_sample.group_name,
                )
                gate_data = [(gate.name, gate.color_hex) for gate in workspace_sample.gates]
                self.sample_panel.set_gates_for_sample(workspace_index, gate_data)
            if select_active and active_index is not None:
                self.sample_panel.select_sample(active_index)
        self.sample_panel.remove_sample_button.setEnabled(active_index is not None)

    def _refresh_available_groups(self) -> None:
        groups = [
            (group.name, group.color_hex)
            for group in self.workspace.groups.values()
        ]
        self.sample_panel.set_available_groups(groups)

    def _population_selection_label(self, sample_index: int | None, population_name: str) -> str:
        if sample_index is None or not population_name:
            return "—"
        if sample_index < 0 or sample_index >= len(self.workspace.samples):
            return population_name
        return f"{self.workspace.samples[sample_index].sample.file_name}: {population_name}"

    def _refresh_sample_details(self) -> None:
        sample_index = self.sample_panel.current_sample_workspace_index()
        if sample_index is None or sample_index < 0 or sample_index >= len(self.workspace.samples):
            self.sample_panel.set_sample_details("")
            return

        workspace_sample = self.workspace.samples[sample_index]
        if workspace_sample.group_name == COMPENSATION_GROUP_NAME:
            details = workspace_sample.compensation.summary
            if workspace_sample.compensation.notes:
                details = f"{details} | {workspace_sample.compensation.notes}"
            self.sample_panel.set_sample_details(details)
            return

        self.sample_panel.set_sample_details(f"Group: {workspace_sample.group_name}")

    def _refresh_gate_panel(self) -> None:
        active_ws_index = self.workspace.active_sample_index
        if active_ws_index is None:
            self._update_population_context_labels()
            self._refresh_statistics_population_options()
            return
        gate_data = [(self._gate_list_label(gate), gate.color_hex) for gate in self.gates]
        gate_row = 0 if self.active_gate is None else self.gates.index(self.active_gate) + 1
        with QSignalBlocker(self.sample_panel.sample_tree):
            self.sample_panel.set_gates_for_sample(active_ws_index, gate_data)
            self.sample_panel.select_gate_row(active_ws_index, gate_row)
        if self.active_gate is None:
            self.inspector_panel.set_active_gate("All events")
        else:
            self.inspector_panel.set_active_gate(self.active_gate.name)
        self._update_population_context_labels()
        self._refresh_statistics_population_options()

    def _show_active_sample(self) -> None:
        if self.current_sample is None:
            self.clear_loaded_sample()
            return

        self._update_inspector(self.current_sample)
        self._configure_axis_selectors(self.current_sample)
        self.redraw_current_plot(show_status=False)

    def _update_inspector(self, sample: SampleData) -> None:
        self.inspector_panel.set_file_info(
            file_name=sample.file_name,
            events=str(sample.event_count),
            channels=str(sample.channel_count),
            active_gate=self.current_population_name(),
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

    def _scatter_gate_overlay_for_gate(
        self,
        gate: GateModel,
        *,
        x_idx: int,
        y_idx: int,
    ) -> ScatterGateOverlay | None:
        if isinstance(gate, RectangleGate):
            if gate.x_channel_index != x_idx or gate.y_channel_index != y_idx:
                return None
            return ScatterGateOverlay(
                kind="rectangle",
                color_hex=gate.color_hex,
                x_min=gate.x_min,
                x_max=gate.x_max,
                y_min=gate.y_min,
                y_max=gate.y_max,
            )

        if isinstance(gate, PolygonGate):
            if gate.x_channel_index != x_idx or gate.y_channel_index != y_idx:
                return None
            return ScatterGateOverlay(
                kind="polygon",
                color_hex=gate.color_hex,
                vertices=gate.vertices,
            )

        if isinstance(gate, CircleGate):
            if gate.x_channel_index != x_idx or gate.y_channel_index != y_idx:
                return None
            return ScatterGateOverlay(
                kind="ellipse",
                color_hex=gate.color_hex,
                center_x=gate.center_x,
                center_y=gate.center_y,
                radius_x=gate.radius_x or gate.radius,
                radius_y=gate.radius_y or gate.radius,
            )

        return None

    def _histogram_gate_overlay_for_gate(
        self,
        gate: GateModel,
        *,
        x_idx: int,
    ) -> HistogramGateOverlay | None:
        if not isinstance(gate, RangeGate):
            return None
        if gate.channel_index != x_idx:
            return None
        return HistogramGateOverlay(
            kind="range",
            color_hex=gate.color_hex,
            x_min=gate.x_min,
            x_max=gate.x_max,
        )

    def _update_population_context_labels(self) -> None:
        pass  # Population context is shown in the inspector panel

    def _refresh_gate_list_labels(self) -> None:
        active_ws_index = self.workspace.active_sample_index
        if active_ws_index is None:
            return
        for gate_index, gate in enumerate(self.gates):
            self.sample_panel.update_gate_in_sample(
                active_ws_index,
                gate_index + 1,
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
        self.workspace = WorkspaceState()
        if self._sample_table_window is not None:
            self._sample_table_window.workspace = self.workspace
        self.selected_group_name = None
        self.current_sample = None
        self.gates = []
        self.active_gate = None

        self._refresh_available_groups()
        self.sample_panel.reset_samples()
        self.sample_panel.reset_gates()
        self._update_population_context_labels()
        self.inspector_panel.set_file_info()
        self.inspector_panel.set_displayed_points(None, None)
        self.inspector_panel.clear_channels()
        self.inspector_panel.clear_statistics()
        self._clear_statistics_results()
        self.plot_panel.clear_all_rois()
        self.plot_panel.show_placeholder_data()
        self.gate_toolbar.set_drawing_active(False)

    def remove_selected_sample(self) -> None:
        sample_indices = self.sample_panel.selected_sample_workspace_indices()
        gate_indices = self.sample_panel.selected_gate_indices()

        if len(sample_indices) > 1:
            self.on_delete_samples_batch(sample_indices)
            return
        if len(gate_indices) > 1:
            self.on_delete_gates_batch(gate_indices)
            return

        sample_index = self.sample_panel.current_sample_workspace_index()
        if self.current_sample is None or sample_index is None:
            self.statusBar().showMessage("No sample selected", 3000)
            return

        removed_name = self.workspace.remove_sample(sample_index).sample.file_name
        self._sync_from_workspace()
        self._clear_statistics_results()
        self._refresh_available_groups()
        self._refresh_sample_list(select_active=True)
        if self.current_sample is None:
            self.clear_loaded_sample()
        else:
            self._refresh_gate_panel()
            self._show_active_sample()
        self._refresh_sample_table()
        self.statusBar().showMessage(f"Removed {removed_name}", 4000)

    def on_sample_selection_changed(self, row: int) -> None:
        if row < 0:
            self._refresh_sample_details()
            return
        if row >= len(self.workspace.samples):
            self._refresh_sample_details()
            return

        self.workspace.active_sample_index = row
        self._sync_from_workspace()
        self._clear_statistics_results()
        self._refresh_gate_panel()
        self._show_active_sample()
        self._refresh_sample_details()
        if self.current_sample is not None:
            self.statusBar().showMessage(f"Focused on {self.current_sample.file_name}", 4000)

    def on_group_selection_changed(self, group_name: object) -> None:
        resolved_group_name = None if group_name is None else str(group_name)
        self.selected_group_name = resolved_group_name
        self._refresh_sample_list(select_active=True)
        self._refresh_sample_details()

    def on_rename_group(self, group_name: str) -> None:
        group = self.workspace.groups.get(group_name)
        if group is None:
            return
        new_name, accepted = QInputDialog.getText(
            self,
            "Rename group",
            "Group name:",
            text=group.name,
        )
        if not accepted:
            return
        normalized = new_name.strip()
        if not normalized:
            QMessageBox.warning(self, "Rename group", "Group name cannot be empty.")
            return
        self.workspace.rename_group(group_name, normalized)
        if self.selected_group_name == group_name:
            self.selected_group_name = normalized
        self._refresh_available_groups()
        self._refresh_sample_list(select_active=True)
        self.statusBar().showMessage(f"Renamed group to {normalized}", 4000)

    def on_select_group_samples(self, group_name: str) -> None:
        self.sample_panel.highlight_group_samples(group_name)
        count = sum(1 for ws in self.workspace.samples if ws.group_name == group_name)
        self.statusBar().showMessage(f"{count} sample(s) in group '{group_name}'", 3000)

    def on_create_group(self) -> None:
        group_name, accepted = QInputDialog.getText(
            self,
            "Create group",
            "Group name:",
        )
        if not accepted:
            return
        normalized = group_name.strip()
        if not normalized:
            QMessageBox.warning(self, "Create group", "Group name cannot be empty.")
            return
        self.workspace.ensure_group(normalized)
        self._refresh_available_groups()
        self.statusBar().showMessage(f"Created group {normalized}", 4000)

    def on_delete_group(self, group_name: str) -> None:
        if group_name in {DEFAULT_GROUP_NAME, COMPENSATION_GROUP_NAME}:
            QMessageBox.information(
                self,
                "Delete group",
                f'The "{group_name}" group is reserved and cannot be deleted.',
            )
            return

        answer = QMessageBox.question(
            self,
            "Delete group",
            f'Delete the "{group_name}" group?\nSamples in this group will be moved to "{DEFAULT_GROUP_NAME}".',
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self.workspace.delete_group(group_name, fallback_group_name=DEFAULT_GROUP_NAME)
        if self.selected_group_name == group_name:
            self.selected_group_name = DEFAULT_GROUP_NAME
        self._refresh_available_groups()
        self._refresh_sample_list(select_active=True)
        self._refresh_sample_table()
        self.statusBar().showMessage(f"Deleted group {group_name}", 4000)

    def on_recolor_group(self, group_name: str) -> None:
        group = self.workspace.groups.get(group_name)
        if group is None:
            return
        color = QColorDialog.getColor(
            QColor(group.color_hex),
            self,
            f"Select color for {group.name}",
        )
        if not color.isValid():
            return
        group.color_hex = color.name().lower()
        self._refresh_available_groups()
        self._refresh_sample_list(select_active=True)
        self.statusBar().showMessage(
            f"Changed {group.name} color to {group.color_hex}",
            4000,
        )

    def on_annotate_group(self, group_name: str) -> None:
        group = self.workspace.groups.get(group_name)
        if group is None:
            return
        notes, accepted = QInputDialog.getMultiLineText(
            self,
            "Group annotations",
            "Notes:",
            text=group.notes,
        )
        if not accepted:
            return
        group.notes = notes.strip()
        self._refresh_available_groups()
        self.statusBar().showMessage(f"Updated annotations for {group.name}", 4000)

    def on_edit_compensation_sample(self, sample_index: int) -> None:
        """Open the Compensation Manager when the user right-clicks a compensation sample."""
        self.open_compensation_editor()

    def on_edit_sample(self, sample_index: int) -> None:
        if sample_index < 0 or sample_index >= len(self.workspace.samples):
            return

        workspace_sample = self.workspace.samples[sample_index]
        current_name = workspace_sample.sample_name
        new_name, accepted = QInputDialog.getText(
            self,
            "Rename sample",
            "Sample name:",
            text=current_name,
        )
        if not accepted:
            return
        normalized = new_name.strip()
        workspace_sample.display_name_override = normalized or None
        self._refresh_sample_list(select_active=True)
        self._refresh_sample_details()
        self._refresh_sample_table()
        self.statusBar().showMessage(f"Renamed sample to {workspace_sample.sample_name}", 4000)

    def on_add_keyword_to_sample(self, sample_index: int) -> None:
        if sample_index < 0 or sample_index >= len(self.workspace.samples):
            return

        keyword_name, accepted = QInputDialog.getText(
            self,
            "Add keyword to sample",
            "Keyword name:",
        )
        if not accepted:
            return
        normalized_name = keyword_name.strip()
        if not normalized_name:
            QMessageBox.warning(self, "Add keyword", "Keyword name cannot be empty.")
            return

        keyword_value, accepted = QInputDialog.getText(
            self,
            "Add keyword to sample",
            f'Value for "{normalized_name}":',
        )
        if not accepted:
            return

        self.workspace.add_keyword_column(normalized_name)
        self.workspace.samples[sample_index].keywords[normalized_name] = keyword_value
        self._refresh_sample_table()
        self.statusBar().showMessage(
            f'Added keyword "{normalized_name}" to {self.workspace.samples[sample_index].sample_name}',
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
        gate_overlays: list[ScatterGateOverlay] = []

        if self.active_gate is not None:
            active_overlay = self._scatter_gate_overlay_for_gate(self.active_gate, x_idx=x_idx, y_idx=y_idx)
            if active_overlay is not None:
                gate_overlays.append(active_overlay)

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
                child_overlay = self._scatter_gate_overlay_for_gate(child_gate, x_idx=x_idx, y_idx=y_idx)
                if child_overlay is not None:
                    gate_overlays.append(child_overlay)

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
            gate_overlays=gate_overlays,
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
        histogram_subpopulation_overlays: list[HistogramOverlay] = []
        histogram_gate_overlays: list[HistogramGateOverlay] = []

        x_label = axis_label(sample.channel_label(x_idx), x_scale)

        if self.active_gate is not None:
            active_gate_overlay = self._histogram_gate_overlay_for_gate(self.active_gate, x_idx=x_idx)
            if active_gate_overlay is not None:
                histogram_gate_overlays.append(active_gate_overlay)

        if len(x) == 0:
            self.plot_panel.show_empty_message("No plottable events under current axis scales")
            self.inspector_panel.set_displayed_points(0, int(population_mask.sum()))
            if show_status:
                self.statusBar().showMessage("No plottable events under current axis scales", 4000)
            return

        if self.inspector_panel.show_subpopulations_enabled():
            current_name = self.current_population_name()
            for child_gate in self._children_of_population(current_name):
                child_values = apply_scale(sample.events[child_gate.full_mask, x_idx], x_scale)
                child_values = child_values[np.isfinite(child_values)]
                if len(child_values) > 0:
                    histogram_subpopulation_overlays.append(
                        HistogramOverlay(
                            values=child_values,
                            color_hex=child_gate.color_hex,
                            label=child_gate.name,
                        )
                    )
                child_gate_overlay = self._histogram_gate_overlay_for_gate(child_gate, x_idx=x_idx)
                if child_gate_overlay is not None:
                    histogram_gate_overlays.append(child_gate_overlay)

        displayed_count, total_count = self.plot_panel.plot_histogram(
            x,
            x_label,
            title=f"{sample.file_name} | {self.current_population_name()} | Histogram of {x_label}",
            subpopulation_overlays=histogram_subpopulation_overlays,
            gate_overlays=histogram_gate_overlays,
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
        self.gate_toolbar.set_plot_mode(mode)
        self.gate_toolbar.set_drawing_active(False)
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
            workspace_sample = self._active_workspace_sample()
            if workspace_sample is not None:
                workspace_sample.active_gate_name = None
            self.inspector_panel.set_active_gate("All events")
        else:
            gate_index = row - 1
            if gate_index >= len(self.gates):
                return
            self.active_gate = self.gates[gate_index]
            workspace_sample = self._active_workspace_sample()
            if workspace_sample is not None:
                workspace_sample.active_gate_name = self.active_gate.name
            self.inspector_panel.set_active_gate(self.active_gate.name)

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

    def on_create_gate(self, gate_type: str) -> None:
        if self.current_sample is None:
            self.statusBar().showMessage("Load an FCS file before creating a gate", 4000)
            return

        if gate_type == "range":
            created = self.plot_panel.create_range_region()
            draft_name = f"Draft range on {self.current_population_name()}"
        elif gate_type == "polygon":
            created = self.plot_panel.create_polygon_roi()
            draft_name = f"Draft polygon on {self.current_population_name()}"
        elif gate_type == "circle":
            created = self.plot_panel.create_circle_roi()
            draft_name = f"Draft circle on {self.current_population_name()}"
        else:  # rectangle
            created = self.plot_panel.create_rectangle_roi()
            draft_name = f"Draft rectangle on {self.current_population_name()}"

        if not created:
            self.statusBar().showMessage("Could not create gate on the current plot", 4000)
            return

        self.inspector_panel.set_active_gate(draft_name)
        self.gate_toolbar.set_drawing_active(True)
        self.statusBar().showMessage(
            "Gate ROI created — adjust it on the plot, then click Apply Gate.",
            5000,
        )

    def on_apply_gate(self) -> None:
        if self.current_sample is None:
            self.statusBar().showMessage("No sample loaded", 4000)
            return

        mode = self.inspector_panel.current_plot_mode()
        if mode == "histogram":
            self._apply_range_gate()
            self.gate_toolbar.set_drawing_active(False)
            return

        polygon_points = self.plot_panel.polygon_roi_points()
        if polygon_points is not None:
            self._apply_polygon_gate()
            self.gate_toolbar.set_drawing_active(False)
            return

        circle_geometry = self.plot_panel.circle_roi_geometry()
        if circle_geometry is not None:
            self._apply_circle_gate()
        else:
            self._apply_rectangle_gate()
        self.gate_toolbar.set_drawing_active(False)

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
            x_scale=x_scale,
            y_scale=y_scale,
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
            x_scale=x_scale,
            y_scale=y_scale,
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

        center_x, center_y, radius_x, radius_y = geometry
        full_mask = circle_mask_from_parent(
            x,
            y,
            parent_mask,
            center_x=center_x,
            center_y=center_y,
            radius=radius_x,
            radius_x=radius_x,
            radius_y=radius_y,
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
            radius=max(radius_x, radius_y),
            radius_x=radius_x,
            radius_y=radius_y,
            event_count=event_count,
            percentage_parent=percentage_parent,
            percentage_total=percentage_total,
            full_mask=full_mask,
            x_scale=x_scale,
            y_scale=y_scale,
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
            x_scale=x_scale,
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
        gate: GateModel,
    ) -> None:
        self.gates.append(gate)
        workspace_sample = self._active_workspace_sample()
        if workspace_sample is not None:
            workspace_sample.active_gate_name = gate.name
        self._clear_statistics_results()
        self._refresh_statistics_population_options()
        active_ws_index = self.workspace.active_sample_index
        if active_ws_index is not None:
            gate_data = [(self._gate_list_label(g), g.color_hex) for g in self.gates]
            with QSignalBlocker(self.sample_panel.sample_tree):
                self.sample_panel.set_gates_for_sample(active_ws_index, gate_data)
                self.sample_panel.select_gate_row(active_ws_index, len(self.gates))
        self._refresh_sample_table()

    def on_rename_active_gate(self, raw_name: str) -> None:
        if self.active_gate is None:
            return

        new_name = raw_name.strip()
        if not new_name:
            self.statusBar().showMessage("Gate name cannot be empty", 3000)
            return

        if new_name == self.active_gate.name:
            return

        old_name = self.active_gate.name
        self.active_gate.name = new_name
        workspace_sample = self._active_workspace_sample()
        if workspace_sample is not None and workspace_sample.active_gate_name == old_name:
            workspace_sample.active_gate_name = new_name
        for workspace_sample in self.workspace.samples:
            if workspace_sample.compensation_positive.population_name == old_name:
                workspace_sample.compensation_positive.population_name = new_name
            if workspace_sample.compensation_negative.population_name == old_name:
                workspace_sample.compensation_negative.population_name = new_name
        for gate in self.gates:
            if gate.parent_name == old_name:
                gate.parent_name = new_name
        self._refresh_gate_list_labels()
        self.inspector_panel.set_active_gate(self.active_gate.name)
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
        active_ws_index = self.workspace.active_sample_index
        if active_ws_index is not None:
            self.sample_panel.update_gate_in_sample(
                active_ws_index,
                gate_index + 1,
                self._gate_list_label(self.active_gate),
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

    def on_export_gate_from_context(self, gate_index: int) -> None:
        if gate_index < 0 or gate_index >= len(self.gates):
            return
        self.active_gate = self.gates[gate_index]
        self.on_export_active_gate()

    def on_delete_gate_from_context(self, gate_index: int) -> None:
        gate = self.gates[gate_index]
        answer = QMessageBox.question(
            self,
            "Delete gate",
            f"Delete {gate.name}?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        names_to_delete = self._gate_subtree_names(self.gates, gate.name)
        remaining_gates = [candidate for candidate in self.gates if candidate.name not in names_to_delete]
        self.gates[:] = remaining_gates
        self.active_gate = None
        workspace_sample = self._active_workspace_sample()
        if workspace_sample is not None:
            workspace_sample.active_gate_name = None
        for workspace_sample in self.workspace.samples:
            if workspace_sample.compensation_positive.population_name in names_to_delete:
                workspace_sample.compensation_positive.population_name = ""
                workspace_sample.compensation_positive.sample_index = None
            if workspace_sample.compensation_negative.population_name in names_to_delete:
                workspace_sample.compensation_negative.population_name = ""
                workspace_sample.compensation_negative.sample_index = None
        self._clear_statistics_results()
        active_ws_index = self.workspace.active_sample_index
        if active_ws_index is not None:
            gate_data = [(self._gate_list_label(g), g.color_hex) for g in self.gates]
            with QSignalBlocker(self.sample_panel.sample_tree):
                self.sample_panel.set_gates_for_sample(active_ws_index, gate_data)
                self.sample_panel.select_gate_row(active_ws_index, 0)
        self.inspector_panel.set_active_gate("All events")
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
        self.gate_toolbar.set_drawing_active(False)
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

    def on_batch_export_statistics(self) -> None:
        """Open the batch export dialog and compute+export statistics across groups."""
        if not self.workspace.samples:
            self.statusBar().showMessage("No samples loaded", 3000)
            return

        dialog = BatchExportDialog(self.workspace, self)
        if not dialog.exec():
            return

        selected_groups = dialog.selected_groups()
        selected_populations = dialog.selected_populations()
        selected_channels = dialog.selected_channels()
        selected_metrics = dialog.selected_metric_keys()

        if not selected_groups:
            QMessageBox.warning(self, "Batch export", "Select at least one group.")
            return
        if not selected_populations:
            QMessageBox.warning(self, "Batch export", "Select at least one population.")
            return
        if not selected_metrics:
            QMessageBox.warning(self, "Batch export", "Select at least one metric.")
            return

        channel_independent = [k for k in selected_metrics if k not in CHANNEL_DEPENDENT_STATS]
        channel_dependent = [k for k in selected_metrics if k in CHANNEL_DEPENDENT_STATS]

        rows: list[dict] = []
        for _, ws in self.workspace.samples_in_group(None):
            if ws.group_name not in selected_groups:
                continue
            sample = ws.sample
            gate_by_name = {g.name: g for g in ws.gates}

            for pop_name in selected_populations:
                if pop_name == "All events":
                    pop_mask = np.ones(sample.event_count, dtype=bool)
                    parent_mask: np.ndarray | None = None
                else:
                    gate = gate_by_name.get(pop_name)
                    if gate is None:
                        continue
                    pop_mask = gate.full_mask
                    parent_gate = gate_by_name.get(gate.parent_name)
                    parent_mask = (
                        parent_gate.full_mask
                        if parent_gate is not None
                        else np.ones(sample.event_count, dtype=bool)
                    )

                # Channel-independent stats — computed once per (sample, population)
                if channel_independent:
                    dummy = np.empty(0)
                    for stat in calculate_population_statistics(
                        dummy,
                        pop_mask,
                        total_event_count=sample.event_count,
                        parent_mask=parent_mask,
                        statistics=channel_independent,
                    ):
                        rows.append(
                            {
                                "group": ws.group_name,
                                "sample": sample.file_name,
                                "population": pop_name,
                                "channel": "—",
                                "statistic_key": stat.key,
                                "statistic_label": stat.label,
                                "value": stat.value,
                            }
                        )

                # Channel-dependent stats — once per (sample, population, channel)
                if channel_dependent and selected_channels:
                    for ch_name in selected_channels:
                        ch_index = next(
                            (
                                i
                                for i, ch in enumerate(sample.channels)
                                if ch.display_name == ch_name
                            ),
                            None,
                        )
                        if ch_index is None:
                            continue
                        ch_values = sample.events[pop_mask, ch_index]
                        for stat in calculate_population_statistics(
                            ch_values,
                            pop_mask,
                            total_event_count=sample.event_count,
                            parent_mask=parent_mask,
                            statistics=channel_dependent,
                        ):
                            rows.append(
                                {
                                    "group": ws.group_name,
                                    "sample": sample.file_name,
                                    "population": pop_name,
                                    "channel": ch_name,
                                    "statistic_key": stat.key,
                                    "statistic_label": stat.label,
                                    "value": stat.value,
                                }
                            )

        if not rows:
            QMessageBox.information(
                self,
                "Batch export",
                "No data found for the current selection.\n"
                "Check that the selected samples have the chosen gates and channels.",
            )
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Statistics Batch",
            "statistics_batch.csv",
            "CSV files (*.csv);;All files (*)",
        )
        if not file_path:
            return

        try:
            output_path = export_batch_statistics_to_csv(rows, file_path)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Batch export failed",
                f"Could not export statistics.\n\nError:\n{exc}",
            )
            return

        self.statusBar().showMessage(
            f"Exported {len(rows)} rows to {output_path}", 6000
        )

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

    def on_assign_sample_group(self, sample_index: int, group_name: str) -> None:
        if sample_index < 0 or sample_index >= len(self.workspace.samples):
            return
        workspace_sample = self.workspace.samples[sample_index]
        normalized_group = group_name.strip() or DEFAULT_GROUP_NAME
        self.workspace.ensure_group(normalized_group)
        workspace_sample.group_name = normalized_group
        self._refresh_available_groups()
        self._refresh_sample_list(select_active=True)
        self._refresh_sample_table()
        self.statusBar().showMessage(
            f"{workspace_sample.sample_name} assigned to {workspace_sample.group_name}",
            4000,
        )

    def on_assign_custom_sample_group(self, sample_index: int) -> None:
        if sample_index < 0 or sample_index >= len(self.workspace.samples):
            return
        workspace_sample = self.workspace.samples[sample_index]
        group_name, accepted = QInputDialog.getText(
            self,
            "Assign group",
            "Group name:",
            text=workspace_sample.group_name,
        )
        if not accepted:
            return
        normalized = group_name.strip()
        if not normalized:
            QMessageBox.warning(self, "Assign group", "Group name cannot be empty.")
            return
        self._ensure_group_with_color(normalized)
        self.on_assign_sample_group(sample_index, normalized)

    def _ensure_group_with_color(self, group_name: str) -> None:
        """Create a new group and prompt for its color if it doesn't already exist."""
        is_new = group_name not in self.workspace.groups
        self.workspace.ensure_group(group_name)
        if is_new:
            color = QColorDialog.getColor(
                QColor(self.workspace.groups[group_name].color_hex),
                self,
                f"Select color for '{group_name}'",
            )
            if color.isValid():
                self.workspace.groups[group_name].color_hex = color.name().lower()

    def on_apply_active_gate_to_group(self, sample_index: int) -> None:
        self._propagate_gates(sample_index, mode="active_gate", scope="group")

    def on_apply_all_gates_to_group(self, sample_index: int) -> None:
        self._propagate_gates(sample_index, mode="all_gates", scope="group")

    def on_apply_active_gate_to_all_samples(self, sample_index: int) -> None:
        self._propagate_gates(sample_index, mode="active_gate", scope="all")

    def on_apply_all_gates_to_all_samples(self, sample_index: int) -> None:
        self._propagate_gates(sample_index, mode="all_gates", scope="all")

    # ── Batch (multi-select) handlers ────────────────────────────────────

    def on_delete_samples_batch(self, ws_indices: list[int]) -> None:
        if not ws_indices:
            return
        count = len(ws_indices)
        answer = QMessageBox.question(
            self,
            "Delete samples",
            f"Delete {count} selected sample(s)?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        for idx in sorted(ws_indices, reverse=True):
            if 0 <= idx < len(self.workspace.samples):
                self.workspace.remove_sample(idx)
        self._sync_from_workspace()
        self._clear_statistics_results()
        self._refresh_available_groups()
        self._refresh_sample_list(select_active=True)
        if self.current_sample is None:
            self.clear_loaded_sample()
        else:
            self._refresh_gate_panel()
            self._show_active_sample()
        self._refresh_sample_table()
        self.statusBar().showMessage(f"Removed {count} sample(s)", 4000)

    def on_assign_samples_group_batch(self, ws_indices: list[int], group_name: str) -> None:
        normalized = group_name.strip() or DEFAULT_GROUP_NAME
        self._ensure_group_with_color(normalized)
        for idx in ws_indices:
            if 0 <= idx < len(self.workspace.samples):
                self.workspace.samples[idx].group_name = normalized
        self._refresh_available_groups()
        self._refresh_sample_list(select_active=True)
        self._refresh_sample_table()
        self.statusBar().showMessage(
            f"{len(ws_indices)} sample(s) assigned to {normalized}", 4000
        )

    def on_apply_active_gate_to_selected(self, ws_indices: list[int]) -> None:
        active_idx = self.workspace.active_sample_index
        if active_idx is None:
            return
        source_sample = self.workspace.samples[active_idx]
        if source_sample.active_gate_name is None:
            self.statusBar().showMessage("Select an active gate first", 5000)
            return
        gates_to_apply = [g for g in source_sample.gates if g.name == source_sample.active_gate_name]
        if not gates_to_apply:
            return
        self._propagate_gates_to_indices(active_idx, gates_to_apply, ws_indices)

    def on_apply_all_gates_to_selected(self, ws_indices: list[int]) -> None:
        active_idx = self.workspace.active_sample_index
        if active_idx is None:
            return
        source_sample = self.workspace.samples[active_idx]
        gates_to_apply = list(source_sample.gates)
        if not gates_to_apply:
            self.statusBar().showMessage("The source sample has no gates to propagate", 5000)
            return
        self._propagate_gates_to_indices(active_idx, gates_to_apply, ws_indices)

    def _propagate_gates_to_indices(
        self,
        source_idx: int,
        gates_to_apply: list,
        target_indices: list[int],
    ) -> None:
        applied = 0
        failures: list[str] = []
        for idx in target_indices:
            if idx == source_idx or idx < 0 or idx >= len(self.workspace.samples):
                continue
            try:
                self.gate_service.replace_gates_on_sample(self.workspace.samples[idx], gates_to_apply)
                applied += 1
            except Exception as exc:
                failures.append(f"{self.workspace.samples[idx].sample.file_name}: {exc}")
        if failures:
            QMessageBox.warning(self, "Apply gates", "\n".join(failures))
        if applied and self.workspace.active_sample_index is not None:
            self._sync_from_workspace()
            self._refresh_gate_panel()
            self.redraw_current_plot(show_status=False)
        self._refresh_sample_table()
        self.statusBar().showMessage(f"Propagated gates to {applied} sample(s)", 5000)

    def on_delete_gates_batch(self, gate_indices: list[int]) -> None:
        valid = [i for i in gate_indices if 0 <= i < len(self.gates)]
        if not valid:
            return
        count = len(valid)
        answer = QMessageBox.question(
            self,
            "Delete gates",
            f"Delete {count} selected gate(s) and their descendants?",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        names_to_delete: set[str] = set()
        for i in valid:
            names_to_delete.update(self._gate_subtree_names(self.gates, self.gates[i].name))
        self.gates[:] = [g for g in self.gates if g.name not in names_to_delete]
        self.active_gate = None
        active_ws = self._active_workspace_sample()
        if active_ws is not None:
            active_ws.active_gate_name = None
        for ws in self.workspace.samples:
            if ws.compensation_positive.population_name in names_to_delete:
                ws.compensation_positive.population_name = ""
                ws.compensation_positive.sample_index = None
            if ws.compensation_negative.population_name in names_to_delete:
                ws.compensation_negative.population_name = ""
                ws.compensation_negative.sample_index = None
        self._clear_statistics_results()
        active_ws_index = self.workspace.active_sample_index
        if active_ws_index is not None:
            gate_data = [(self._gate_list_label(g), g.color_hex) for g in self.gates]
            with QSignalBlocker(self.sample_panel.sample_tree):
                self.sample_panel.set_gates_for_sample(active_ws_index, gate_data)
                self.sample_panel.select_gate_row(active_ws_index, 0)
        self.inspector_panel.set_active_gate("All events")
        self._refresh_statistics_population_options()
        self._update_population_context_labels()
        self.redraw_current_plot(show_status=False)
        self.statusBar().showMessage(f"Deleted {count} gate(s)", 4000)

    def on_apply_gates_to_group_batch(self, source_ws_index: int, gate_indices: list[int]) -> None:
        self._propagate_selected_gates(source_ws_index, gate_indices, scope="group")

    def on_apply_gates_to_all_batch(self, source_ws_index: int, gate_indices: list[int]) -> None:
        self._propagate_selected_gates(source_ws_index, gate_indices, scope="all")

    def _propagate_selected_gates(
        self, source_ws_index: int, gate_indices: list[int], *, scope: str
    ) -> None:
        if source_ws_index < 0 or source_ws_index >= len(self.workspace.samples):
            return
        source_sample = self.workspace.samples[source_ws_index]
        gates_to_apply = [
            source_sample.gates[i] for i in gate_indices if 0 <= i < len(source_sample.gates)
        ]
        if not gates_to_apply:
            return
        target_group_name = source_sample.group_name if scope == "group" else None
        applied_count, failures, scope_label = self.gate_service.propagate_gates(
            self.workspace,
            source_sample_index=source_ws_index,
            gate_names=[g.name for g in gates_to_apply],
            target_group_name=target_group_name,
        )
        if failures:
            QMessageBox.warning(self, "Apply gates", "\n".join(failures))
        if self.workspace.active_sample_index is not None:
            self._sync_from_workspace()
            self._refresh_gate_panel()
            self.redraw_current_plot(show_status=False)
        self._refresh_sample_table()
        self.statusBar().showMessage(
            f"Propagated {len(gates_to_apply)} gate(s) to {applied_count} sample(s) in {scope_label}",
            6000,
        )

    def _propagate_gates(self, sample_index: int, *, mode: str, scope: str) -> None:
        if sample_index < 0 or sample_index >= len(self.workspace.samples):
            return

        source_sample = self.workspace.samples[sample_index]
        source_gates = source_sample.gates
        if mode == "active_gate":
            if source_sample.active_gate_name is None:
                self.statusBar().showMessage("Select an active gate in the source sample first", 5000)
                return
            gates_to_apply = [gate for gate in source_gates if gate.name == source_sample.active_gate_name]
        else:
            gates_to_apply = list(source_gates)

        if not gates_to_apply:
            self.statusBar().showMessage("The source sample has no gates to propagate", 5000)
            return

        target_group_name = source_sample.group_name if scope == "group" else None
        applied_count, failures, scope_label = self.gate_service.propagate_gates(
            self.workspace,
            source_sample_index=sample_index,
            gate_names=[gate.name for gate in gates_to_apply],
            target_group_name=target_group_name,
        )

        if applied_count == 0 and not failures:
            self.statusBar().showMessage(f"No target samples available in {scope_label}", 5000)
            return

        if self.workspace.active_sample_index is not None:
            self._sync_from_workspace()
            self._refresh_gate_panel()
            self.redraw_current_plot(show_status=False)
        self._refresh_sample_table()

        if failures and applied_count == 0:
            QMessageBox.warning(self, "Apply gates", "\n".join(failures))
            self.statusBar().showMessage("No gates were propagated", 5000)
            return

        if failures:
            QMessageBox.warning(self, "Apply gates", "\n".join(failures))
            self.statusBar().showMessage(
                f"Propagated gates to {applied_count} sample(s); {len(failures)} failed",
                6000,
            )
            return

        self.statusBar().showMessage(
            f"Propagated {mode.replace('_', ' ')} from {source_sample.sample.file_name} to {applied_count} sample(s) in {scope_label}",
            6000,
        )

    def _replace_gates_on_sample(self, target_sample: WorkspaceSample, source_gates: list[GateModel]) -> None:
        self.gate_service.replace_gates_on_sample(target_sample, source_gates)

    def _upsert_gate_on_sample(self, target_sample: WorkspaceSample, gate: GateModel) -> None:
        self.gate_service.upsert_gate_on_sample(target_sample, gate)

    @staticmethod
    def _gate_subtree_names(gates: list[GateModel], root_name: str) -> set[str]:
        return GateService.gate_subtree_names(gates, root_name)

    def _delete_gate_subtree(self, gates: list[GateModel], root_name: str) -> None:
        self.gate_service.delete_gate_subtree(gates, root_name)

    # ------------------------------------------------------------------
    # Workspace save / load
    # ------------------------------------------------------------------

    def open_workspace_dialog(self) -> None:
        """Open a .cytodraft workspace file."""
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Open Workspace",
            "",
            f"CytoDraft Workspace (*{WORKSPACE_EXTENSION});;All files (*)",
        )
        if not path_str:
            return
        self._load_workspace_from_path(Path(path_str))

    def _load_workspace_from_path(self, path: Path) -> None:
        self.statusBar().showMessage(f"Loading workspace: {path.name}\u2026")
        try:
            workspace, warnings = load_workspace(
                path,
                missing_file_handler=self._handle_missing_fcs_file,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Cannot open workspace", str(exc))
            self.statusBar().showMessage("Failed to open workspace", 5000)
            return

        self._apply_loaded_workspace(workspace, path)

        if warnings:
            QMessageBox.warning(
                self,
                "Workspace loaded with warnings",
                "The workspace was loaded, but some issues were encountered:\n\n"
                + "\n".join(f"\u2022 {w}" for w in warnings),
            )
        self.statusBar().showMessage(f"Opened workspace: {path.name}", 6000)

    def _apply_loaded_workspace(self, workspace: WorkspaceState, path: Path) -> None:
        """Replace the current workspace and refresh all UI."""
        self.workspace = workspace
        self._workspace_path = path
        self.current_sample = None
        self.gates = []
        self.active_gate = None
        self._latest_statistics = []
        self._latest_statistics_population_name = ""
        self._latest_statistics_channel_name = ""
        self.selected_group_name = None

        if self._sample_table_window is not None:
            self._sample_table_window.close()
            self._sample_table_window = None

        self._sync_from_workspace()
        self._refresh_available_groups()
        self._refresh_sample_list(select_active=True)
        self._refresh_gate_panel()
        self._show_active_sample()
        self.save_workspace_action.setEnabled(True)
        self._update_window_title()

    def save_workspace_dialog(self) -> None:
        """Save to the current workspace file, or prompt for a path."""
        if self._workspace_path is None:
            self.save_workspace_as_dialog()
            return
        self._save_workspace_to_path(self._workspace_path)

    def save_workspace_as_dialog(self) -> None:
        """Prompt the user for a save path and save the workspace."""
        default_name = (
            self._workspace_path.stem if self._workspace_path else "experiment"
        )
        path_str, _ = QFileDialog.getSaveFileName(
            self,
            "Save Workspace As",
            default_name + WORKSPACE_EXTENSION,
            f"CytoDraft Workspace (*{WORKSPACE_EXTENSION});;All files (*)",
        )
        if not path_str:
            return
        path = Path(path_str)
        if path.suffix != WORKSPACE_EXTENSION:
            path = path.with_suffix(WORKSPACE_EXTENSION)
        self._save_workspace_to_path(path)

    def _save_workspace_to_path(self, path: Path) -> None:
        try:
            save_workspace(self.workspace, path)
        except Exception as exc:
            QMessageBox.critical(self, "Cannot save workspace", str(exc))
            self.statusBar().showMessage("Save failed", 5000)
            return
        self._workspace_path = path
        self.save_workspace_action.setEnabled(True)
        self._update_window_title()
        self.statusBar().showMessage(f"Saved: {path.name}", 5000)

    def _update_window_title(self) -> None:
        if self._workspace_path is not None:
            self.setWindowTitle(f"CytoDraft \u2014 {self._workspace_path.stem}")
        else:
            self.setWindowTitle("CytoDraft")

    def _handle_missing_fcs_file(self, original_path: str) -> Path | None:
        """Called when a referenced FCS file is not found during workspace load."""
        answer = QMessageBox.question(
            self,
            "File not found",
            f"The following FCS file could not be found:\n\n{original_path}\n\n"
            "Would you like to locate it manually?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if answer != QMessageBox.Yes:
            return None
        path_str, _ = QFileDialog.getOpenFileName(
            self,
            "Locate FCS file",
            "",
            "FCS files (*.fcs);;All files (*)",
        )
        return Path(path_str) if path_str else None

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
