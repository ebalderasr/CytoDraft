from __future__ import annotations

import csv
from collections.abc import Callable

from PySide6.QtCore import QMimeData, Qt
from PySide6.QtGui import QColor, QDrag
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QColorDialog,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from cytodraft.gui.batch_export_dialog import StatisticsColumnDialog
from cytodraft.models.workspace import COMPENSATION_GROUP_NAME, DEFAULT_GROUP_NAME, WorkspaceState
from cytodraft.services.gate_service import GateService
from cytodraft.services.statistics_service import StatisticsService

_NAME_BG = QColor("#f7f7ff")
_GROUP_BG = QColor("#eefbf3")
_KEYWORD_BG = QColor("#eef6ff")
_FIXED_HEADER_BG = QColor("#f3f4f6")
_GATE_HEADER_BG = QColor("#fff7ed")
_STAT_HEADER_BG = QColor("#f5f3ff")
_KEYWORD_HEADER_BG = QColor("#eff6ff")
_SAMPLE_ROWS_MIME = "application/x-cytodraft-sample-rows"


class SampleTableWidget(QTableWidget):
    def __init__(self, selected_sample_indices: Callable[[], list[int]], parent=None) -> None:
        super().__init__(parent)
        self._selected_sample_indices = selected_sample_indices
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setDefaultDropAction(Qt.MoveAction)

    def startDrag(self, supported_actions: Qt.DropActions) -> None:
        del supported_actions
        sample_indices = self._selected_sample_indices()
        if not sample_indices:
            return

        mime_data = QMimeData()
        mime_data.setData(
            _SAMPLE_ROWS_MIME,
            ",".join(str(index) for index in sample_indices).encode("utf-8"),
        )
        drag = QDrag(self)
        drag.setMimeData(mime_data)
        drag.exec(Qt.MoveAction)


class GroupListWidget(QListWidget):
    def __init__(self, on_samples_dropped: Callable[[list[int], str], None], parent=None) -> None:
        super().__init__(parent)
        self._on_samples_dropped = on_samples_dropped
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(_SAMPLE_ROWS_MIME):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasFormat(_SAMPLE_ROWS_MIME):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        if not event.mimeData().hasFormat(_SAMPLE_ROWS_MIME):
            super().dropEvent(event)
            return

        target_item = self.itemAt(event.position().toPoint())
        if target_item is None:
            event.ignore()
            return

        payload = bytes(event.mimeData().data(_SAMPLE_ROWS_MIME)).decode("utf-8")
        sample_indices = [int(part) for part in payload.split(",") if part.strip()]
        group_name = target_item.data(Qt.UserRole)
        if sample_indices and group_name:
            self._on_samples_dropped(sample_indices, str(group_name))
            event.acceptProposedAction()
            return

        event.ignore()


class SampleTableWindow(QDialog):
    """Sample manager for bulk sample edits, gate inspection, and gate propagation."""

    def __init__(
        self,
        workspace: WorkspaceState,
        gate_service: GateService,
        statistics_service: StatisticsService,
        on_workspace_changed: Callable[[], None] | None = None,
        on_add_samples_requested: Callable[[str | None], None] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.workspace = workspace
        self.gate_service = gate_service
        self.statistics_service = statistics_service
        self._on_workspace_changed = on_workspace_changed
        self._on_add_samples_requested = on_add_samples_requested

        self.setWindowTitle("Sample Manager")
        self.setMinimumSize(960, 560)
        self.resize(1380, 760)
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowCloseButtonHint
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
        )

        self._row_sample_indices: list[int] = []
        self._n_fixed_cols = 0
        self._keyword_columns: list[str] = []
        self._gate_col_specs: list[tuple[str, str]] = []
        self._statistic_columns = []
        self._show_gate_summary = True
        self._show_statistics = True
        self._show_keywords = True
        self._updating_gate_browser = False

        self._build_ui()
        self.refresh()

    @staticmethod
    def _vline() -> QFrame:
        """Thin vertical separator for the action bar."""
        sep = QFrame()
        sep.setFrameShape(QFrame.VLine)
        sep.setFrameShadow(QFrame.Plain)
        sep.setFixedWidth(1)
        sep.setStyleSheet("background: #d4dde7; border: none;")
        sep.setContentsMargins(0, 4, 0, 4)
        return sep

    def _build_ui(self) -> None:
        # ── Action row (modifies data) ──────────────────────────────────────
        action_row = QHBoxLayout()
        action_row.setSpacing(5)
        action_row.setContentsMargins(0, 0, 0, 0)

        self._add_samples_btn = QPushButton("Add samples")
        self._add_samples_btn.setProperty("variant", "primary")
        self._add_samples_btn.clicked.connect(self._on_add_samples)

        self._add_kw_btn = QPushButton("+ Keyword")
        self._add_kw_btn.setProperty("variant", "subtle")
        self._add_kw_btn.setToolTip("Add a custom keyword column")
        self._add_kw_btn.clicked.connect(self._on_add_keyword)

        self._remove_kw_btn = QPushButton("− Keyword")
        self._remove_kw_btn.setProperty("variant", "danger")
        self._remove_kw_btn.setToolTip("Remove a keyword column")
        self._remove_kw_btn.clicked.connect(self._on_remove_keyword)

        self._statistics_btn = QPushButton("+ Statistic")
        self._statistics_btn.setProperty("variant", "subtle")
        self._statistics_btn.setToolTip("Add a statistics column")
        self._statistics_btn.clicked.connect(self._on_add_statistics)

        self._remove_stat_btn = QPushButton("− Statistic")
        self._remove_stat_btn.setProperty("variant", "danger")
        self._remove_stat_btn.setToolTip("Remove a statistics column")
        self._remove_stat_btn.clicked.connect(self._on_remove_statistics)

        self._move_group_btn = QPushButton("Move to group")
        self._move_group_btn.setProperty("variant", "subtle")
        self._move_group_btn.clicked.connect(self._on_move_selected_samples_to_group)

        self._select_equiv_gate_btn = QPushButton("≡ Match gate")
        self._select_equiv_gate_btn.setProperty("variant", "subtle")
        self._select_equiv_gate_btn.setToolTip("Select all samples that have a specific gate name")
        self._select_equiv_gate_btn.clicked.connect(self._on_select_equivalent_gates)

        self._delete_samples_btn = QPushButton("Delete samples")
        self._delete_samples_btn.setProperty("variant", "danger")
        self._delete_samples_btn.clicked.connect(self._on_delete_selected_samples)

        self._export_btn = QPushButton("Export CSV")
        self._export_btn.setProperty("variant", "primary")
        self._export_btn.clicked.connect(self._on_export_csv)

        self._refresh_btn = QPushButton("↻")
        self._refresh_btn.setProperty("variant", "subtle")
        self._refresh_btn.setToolTip("Refresh table")
        self._refresh_btn.setFixedWidth(34)
        self._refresh_btn.clicked.connect(self.refresh)

        action_row.addWidget(self._add_samples_btn)
        action_row.addWidget(self._vline())
        action_row.addWidget(self._add_kw_btn)
        action_row.addWidget(self._remove_kw_btn)
        action_row.addWidget(self._vline())
        action_row.addWidget(self._statistics_btn)
        action_row.addWidget(self._remove_stat_btn)
        action_row.addWidget(self._vline())
        action_row.addWidget(self._move_group_btn)
        action_row.addWidget(self._select_equiv_gate_btn)
        action_row.addWidget(self._delete_samples_btn)
        action_row.addStretch(1)
        action_row.addWidget(self._refresh_btn)
        action_row.addWidget(self._export_btn)

        # ── Filter row (display options) ────────────────────────────────────
        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        filter_row.setContentsMargins(0, 0, 0, 0)

        filter_label = QLabel("Group:")
        filter_label.setStyleSheet("color: #536274; font-weight: 600; font-size: 12px;")
        self._group_combo = QComboBox()
        self._group_combo.setMinimumWidth(160)
        self._group_combo.currentIndexChanged.connect(self._rebuild_table)

        show_label = QLabel("Show:")
        show_label.setStyleSheet("color: #536274; font-weight: 600; font-size: 12px; margin-left: 8px;")

        self._toggle_gates_btn = QPushButton("Gates")
        self._toggle_gates_btn.setCheckable(True)
        self._toggle_gates_btn.setChecked(True)
        self._toggle_gates_btn.setProperty("variant", "chip")
        self._toggle_gates_btn.toggled.connect(self._on_toggle_gate_summary)

        self._toggle_stats_btn = QPushButton("Statistics")
        self._toggle_stats_btn.setCheckable(True)
        self._toggle_stats_btn.setChecked(True)
        self._toggle_stats_btn.setProperty("variant", "chip")
        self._toggle_stats_btn.toggled.connect(self._on_toggle_statistics)

        self._toggle_keywords_btn = QPushButton("Keywords")
        self._toggle_keywords_btn.setCheckable(True)
        self._toggle_keywords_btn.setChecked(True)
        self._toggle_keywords_btn.setProperty("variant", "chip")
        self._toggle_keywords_btn.toggled.connect(self._on_toggle_keywords)

        filter_row.addWidget(filter_label)
        filter_row.addWidget(self._group_combo)
        filter_row.addWidget(show_label)
        filter_row.addWidget(self._toggle_gates_btn)
        filter_row.addWidget(self._toggle_stats_btn)
        filter_row.addWidget(self._toggle_keywords_btn)
        filter_row.addStretch(1)

        helper_row = QHBoxLayout()
        helper_row.setSpacing(8)
        helper_row.setContentsMargins(0, 0, 0, 0)

        legend = QLabel("Edit sample names, groups, and keywords directly in the table.")
        legend.setStyleSheet("color: #6b7280; font-size: 11px;")

        sections = QLabel(
            "Gray: sample info  |  Amber: gates  |  Violet: statistics  |  Blue: keywords"
        )
        sections.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        sections.setStyleSheet("color: #6b7280; font-size: 11px;")
        self._sections_label = sections

        helper_row.addWidget(legend)
        helper_row.addStretch(1)
        helper_row.addWidget(sections)

        self._table = SampleTableWidget(self._selected_sample_indices)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.setWordWrap(False)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.itemChanged.connect(self._on_item_changed)
        self._table.itemSelectionChanged.connect(self._on_table_selection_changed)
        self._table.customContextMenuRequested.connect(self._on_table_context_menu)

        self._gate_tree = QTreeWidget()
        self._gate_tree.setHeaderLabels(["Population / gate", "Samples", "Events", "% parent"])
        self._gate_tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._gate_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self._gate_tree.customContextMenuRequested.connect(self._on_gate_tree_context_menu)

        tree_hint = QLabel(
            "Gate browser: single-sample selection shows the full hierarchy. Multi-selection shows gate coverage across samples."
        )
        tree_hint.setWordWrap(True)
        tree_hint.setStyleSheet("color: #6b7280; font-size: 11px;")

        table_panel = QWidget()
        table_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        table_layout = QVBoxLayout()
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(4)
        table_layout.addWidget(QLabel("Samples"))
        table_layout.addWidget(self._table, stretch=1)
        table_panel.setLayout(table_layout)

        self._group_list = GroupListWidget(self._assign_samples_to_group)
        self._group_list.setAlternatingRowColors(True)
        self._group_list.setMaximumHeight(140)
        self._group_list.currentItemChanged.connect(self._on_group_list_selection_changed)

        self._group_notes_label = QLabel("Notes: —")
        self._group_notes_label.setWordWrap(True)
        self._group_notes_label.setStyleSheet("color: #6b7280;")

        self._new_group_btn = QPushButton("New")
        self._new_group_btn.setProperty("variant", "primary")
        self._new_group_btn.clicked.connect(self._on_create_group)

        self._rename_group_btn = QPushButton("Rename")
        self._rename_group_btn.setProperty("variant", "subtle")
        self._rename_group_btn.clicked.connect(self._on_rename_group)

        self._group_color_btn = QPushButton("Color")
        self._group_color_btn.setProperty("variant", "subtle")
        self._group_color_btn.clicked.connect(self._on_recolor_group)

        self._group_notes_btn = QPushButton("Notes")
        self._group_notes_btn.setProperty("variant", "subtle")
        self._group_notes_btn.clicked.connect(self._on_edit_group_notes)

        self._delete_group_btn = QPushButton("Delete")
        self._delete_group_btn.setProperty("variant", "danger")
        self._delete_group_btn.clicked.connect(self._on_delete_group)

        group_buttons = QGridLayout()
        group_buttons.setContentsMargins(0, 0, 0, 0)
        group_buttons.setHorizontalSpacing(6)
        group_buttons.setVerticalSpacing(6)
        group_buttons.addWidget(self._new_group_btn, 0, 0)
        group_buttons.addWidget(self._rename_group_btn, 0, 1)
        group_buttons.addWidget(self._group_color_btn, 0, 2)
        group_buttons.addWidget(self._group_notes_btn, 1, 0)
        group_buttons.addWidget(self._delete_group_btn, 1, 1)

        group_panel = QWidget()
        group_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        group_layout = QVBoxLayout()
        group_layout.setContentsMargins(0, 0, 0, 0)
        group_layout.setSpacing(4)
        group_layout.addWidget(QLabel("Groups"))
        group_layout.addWidget(self._group_list)
        group_layout.addLayout(group_buttons)
        group_layout.addWidget(self._group_notes_label)
        group_panel.setLayout(group_layout)

        browser_panel = QWidget()
        browser_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        browser_layout = QVBoxLayout()
        browser_layout.setContentsMargins(0, 0, 0, 0)
        browser_layout.setSpacing(4)
        browser_layout.addWidget(QLabel("Populations / gates"))
        browser_layout.addWidget(tree_hint)
        browser_layout.addWidget(self._gate_tree, stretch=1)
        browser_panel.setLayout(browser_layout)

        right_panel = QWidget()
        right_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)
        right_layout.addWidget(group_panel)
        right_layout.addWidget(browser_panel, stretch=1)
        right_panel.setLayout(right_layout)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(table_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([980, 400])
        splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        top_panel = QWidget()
        top_panel.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        top_layout = QVBoxLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(4)
        top_layout.addLayout(action_row)
        top_layout.addLayout(filter_row)
        top_layout.addLayout(helper_row)
        top_panel.setLayout(top_layout)

        layout = QVBoxLayout()
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(4)
        layout.addWidget(top_panel)
        layout.addWidget(splitter, stretch=1)
        self.setLayout(layout)

    def refresh(self) -> None:
        current_group = self._group_combo.currentData()
        self._group_combo.blockSignals(True)
        self._group_combo.clear()
        self._group_combo.addItem("All groups", None)
        for group_name in sorted(self.workspace.groups):
            self._group_combo.addItem(group_name, group_name)

        restored = False
        for index in range(self._group_combo.count()):
            if self._group_combo.itemData(index) == current_group:
                self._group_combo.setCurrentIndex(index)
                restored = True
                break
        if not restored:
            self._group_combo.setCurrentIndex(0)
        self._group_combo.blockSignals(False)
        self._refresh_group_list()
        self._rebuild_table()

    def _refresh_group_list(self) -> None:
        current_group = self._current_group_name_for_actions()
        self._group_list.blockSignals(True)
        self._group_list.clear()
        for group_name in sorted(self.workspace.groups):
            item = QListWidgetItem(group_name)
            item.setData(Qt.UserRole, group_name)
            item.setForeground(QColor(self.workspace.groups[group_name].color_hex))
            self._group_list.addItem(item)

        selected_row = -1
        for row in range(self._group_list.count()):
            item = self._group_list.item(row)
            if item.data(Qt.UserRole) == current_group:
                selected_row = row
                break
        if selected_row < 0 and self._group_list.count() > 0:
            selected_row = 0
        if selected_row >= 0:
            self._group_list.setCurrentRow(selected_row)
        self._group_list.blockSignals(False)
        self._refresh_group_notes()

    def _current_group_name_for_actions(self) -> str | None:
        item = self._group_list.currentItem()
        if item is not None:
            return item.data(Qt.UserRole)
        current_filter = self._group_combo.currentData()
        return current_filter if current_filter is not None else DEFAULT_GROUP_NAME

    def _refresh_group_notes(self) -> None:
        group_name = self._current_group_name_for_actions()
        if group_name is None:
            self._group_notes_label.setText("Notes: —")
            return
        group = self.workspace.groups.get(group_name)
        self._group_notes_label.setText(f"Notes: {group.notes}" if group and group.notes else "Notes: —")

    def _on_group_list_selection_changed(self, current, previous) -> None:
        del previous
        if current is None:
            self._refresh_group_notes()
            return
        group_name = current.data(Qt.UserRole)
        combo_index = self._group_combo.findData(group_name)
        if combo_index >= 0:
            self._group_combo.setCurrentIndex(combo_index)
        self._refresh_group_notes()

    def _rebuild_table(self) -> None:
        selected_group: str | None = self._group_combo.currentData()
        samples = self.workspace.samples_in_group(selected_group)

        gate_names: list[str] = []
        seen_gates: set[str] = set()
        for _, workspace_sample in samples:
            for gate in workspace_sample.gates:
                if gate.name not in seen_gates:
                    gate_names.append(gate.name)
                    seen_gates.add(gate.name)

        fixed_headers = ["Sample", "Group", "Total events"]
        gate_col_specs: list[tuple[str, str]] = []
        if self._show_gate_summary:
            for gate_name in gate_names:
                gate_col_specs.append((gate_name, "events"))
                gate_col_specs.append((gate_name, "% parent"))
        gate_headers = [f"{gate_name}  -  {stat}" for gate_name, stat in gate_col_specs]
        keyword_columns = list(self.workspace.keyword_columns) if self._show_keywords else []
        statistic_columns = list(self.workspace.statistic_columns) if self._show_statistics else []
        statistic_headers = [column.header for column in statistic_columns]
        all_headers = fixed_headers + gate_headers + statistic_headers + keyword_columns

        self._row_sample_indices = []
        self._n_fixed_cols = len(fixed_headers) + len(gate_headers) + len(statistic_headers)
        self._keyword_columns = keyword_columns
        self._gate_col_specs = gate_col_specs
        self._statistic_columns = statistic_columns
        self._sections_label.setText(self._visible_sections_label())

        self._table.blockSignals(True)
        self._table.clearContents()
        self._table.setColumnCount(len(all_headers))
        self._table.setHorizontalHeaderLabels(all_headers)
        self._table.setRowCount(len(samples))

        for row, (sample_index, workspace_sample) in enumerate(samples):
            self._row_sample_indices.append(sample_index)
            gate_by_name = {gate.name: gate for gate in workspace_sample.gates}

            self._set_editable(row, 0, workspace_sample.sample_name, _NAME_BG)
            self._set_editable(row, 1, workspace_sample.group_name, _GROUP_BG)
            self._set_readonly(row, 2, f"{workspace_sample.sample.event_count:,}")

            for col_offset, (gate_name, stat_name) in enumerate(gate_col_specs):
                col = len(fixed_headers) + col_offset
                gate = gate_by_name.get(gate_name)
                if gate is None:
                    self._set_readonly(row, col, "—")
                elif stat_name == "events":
                    self._set_readonly(row, col, f"{gate.event_count:,}")
                else:
                    self._set_readonly(row, col, f"{gate.percentage_parent:.2f}")

            stats_start = len(fixed_headers) + len(gate_col_specs)
            for stat_offset, column in enumerate(statistic_columns):
                col = stats_start + stat_offset
                text = "—"
                if column.group_name is None or workspace_sample.group_name == column.group_name:
                    result = self.statistics_service.calculate_for_workspace_sample(
                        workspace_sample,
                        population_name=column.population_name,
                        channel_name=column.channel_name,
                        statistic_key=column.statistic_key,
                    )
                    text = self.statistics_service.format_result(result)
                self._set_readonly(row, col, text)

            for kw_offset, keyword in enumerate(keyword_columns):
                col = self._n_fixed_cols + kw_offset
                value = workspace_sample.keywords.get(keyword, "")
                self._set_editable(row, col, value, _KEYWORD_BG)

        self._table.blockSignals(False)

        for col in range(len(fixed_headers)):
            self._style_header_item(
                col,
                background=_FIXED_HEADER_BG,
                tooltip="Sample-level fields",
            )

        gate_start = len(fixed_headers)
        for gate_offset in range(len(gate_col_specs)):
            self._style_header_item(
                gate_start + gate_offset,
                background=_GATE_HEADER_BG,
                foreground=QColor("#9a3412"),
                tooltip="Read-only gate summary",
            )

        stats_start = len(fixed_headers) + len(gate_col_specs)
        for stat_offset in range(len(statistic_columns)):
            self._style_header_item(
                stats_start + stat_offset,
                background=_STAT_HEADER_BG,
                foreground=QColor("#6d28d9"),
                tooltip="Calculated statistic column",
            )

        for kw_offset in range(len(keyword_columns)):
            col = self._n_fixed_cols + kw_offset
            self._style_header_item(
                col,
                background=_KEYWORD_HEADER_BG,
                foreground=QColor("#1d4ed8"),
                tooltip="Editable keyword field",
            )

        self._table.resizeColumnsToContents()
        for column in (0, 1):
            if self._table.columnWidth(column) < 140:
                self._table.setColumnWidth(column, 140)
        for kw_offset in range(len(keyword_columns)):
            col = self._n_fixed_cols + kw_offset
            if self._table.columnWidth(col) < 120:
                self._table.setColumnWidth(col, 120)
        for stat_offset in range(len(statistic_columns)):
            col = stats_start + stat_offset
            if self._table.columnWidth(col) < 180:
                self._table.setColumnWidth(col, 180)

        if self._table.rowCount() > 0 and not self._table.selectionModel().selectedRows():
            self._table.selectRow(0)
        self._rebuild_gate_browser()

    def _style_header_item(
        self,
        col: int,
        *,
        background: QColor,
        foreground: QColor | None = None,
        tooltip: str = "",
    ) -> None:
        header_item = self._table.horizontalHeaderItem(col)
        if header_item is None:
            return
        header_item.setBackground(background)
        if foreground is not None:
            header_item.setForeground(foreground)
        if tooltip:
            header_item.setToolTip(tooltip)

    def _visible_sections_label(self) -> str:
        sections = ["sample info (gray)"]
        if self._show_gate_summary:
            sections.append("gate summary (amber)")
        if self._show_statistics:
            sections.append("calculated statistics (violet)")
        if self._show_keywords:
            sections.append("editable keywords (blue)")
        return "Columns: " + " | ".join(sections)

    def _on_toggle_gate_summary(self, checked: bool) -> None:
        self._show_gate_summary = checked
        self.refresh()

    def _on_toggle_statistics(self, checked: bool) -> None:
        self._show_statistics = checked
        self.refresh()

    def _on_toggle_keywords(self, checked: bool) -> None:
        self._show_keywords = checked
        self.refresh()

    def _set_readonly(self, row: int, col: int, text: str) -> None:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        self._table.setItem(row, col, item)

    def _set_editable(self, row: int, col: int, text: str, background: QColor) -> None:
        item = QTableWidgetItem(text)
        item.setBackground(background)
        self._table.setItem(row, col, item)

    def _selected_sample_indices(self) -> list[int]:
        rows = sorted(index.row() for index in self._table.selectionModel().selectedRows())
        return [
            self._row_sample_indices[row]
            for row in rows
            if 0 <= row < len(self._row_sample_indices)
        ]

    def _sample_indices_for_row(self, row: int) -> list[int]:
        if 0 <= row < len(self._row_sample_indices):
            sample_index = self._row_sample_indices[row]
            selected = self._selected_sample_indices()
            if sample_index in selected:
                return selected
            return [sample_index]
        return []

    def _keyword_name_for_column(self, col: int) -> str | None:
        kw_offset = col - self._n_fixed_cols
        if 0 <= kw_offset < len(self._keyword_columns):
            return self._keyword_columns[kw_offset]
        return None

    def _single_selected_sample_index(self) -> int | None:
        sample_indices = self._selected_sample_indices()
        if len(sample_indices) == 1:
            return sample_indices[0]
        return None

    def _on_table_selection_changed(self) -> None:
        self._rebuild_gate_browser()

    def _on_table_context_menu(self, pos) -> None:
        item = self._table.itemAt(pos)
        if item is None:
            return

        row = item.row()
        col = item.column()
        sample_indices = self._sample_indices_for_row(row)
        if not sample_indices:
            return

        is_multi = len(sample_indices) > 1
        source_ws = self.workspace.samples[sample_indices[0]]
        item_group = source_ws.group_name

        menu = QMenu(self)

        # ── Keyword copy (column-specific) ───────────────────────
        keyword_name = self._keyword_name_for_column(col)
        if keyword_name is not None:
            copy_group_action = menu.addAction(f'Copy "{keyword_name}" to same group')
            copy_all_action = menu.addAction(f'Copy "{keyword_name}" to all samples')
            menu.addSeparator()
        else:
            copy_group_action = None
            copy_all_action = None

        # ── Assign to group ───────────────────────────────────────
        assign_menu = menu.addMenu("Assign to group")
        group_actions: list[tuple[str, object]] = []
        for gname in sorted(self.workspace.groups):
            action = assign_menu.addAction(gname)
            group_actions.append((gname, action))
        if group_actions:
            assign_menu.addSeparator()
        custom_group_action = assign_menu.addAction("Other group...")

        # ── Sample actions ────────────────────────────────────────
        menu.addSeparator()
        edit_action = menu.addAction("Edit sample name...") if not is_multi else None
        menu.addSeparator()
        delete_action = menu.addAction(f"Delete {len(sample_indices)} sample(s)")

        # ── Gate propagation (single source) ─────────────────────
        has_gates = bool(source_ws.gates)
        if has_gates:
            menu.addSeparator()
            apply_all_group_action = menu.addAction("Apply all gates to this group")
            apply_all_all_action = menu.addAction("Apply all gates to all samples")
        else:
            apply_all_group_action = None
            apply_all_all_action = None

        # ── Group management ──────────────────────────────────────
        menu.addSeparator()
        select_group_action = menu.addAction(f"Select all in '{item_group}'")
        group_edit_menu = menu.addMenu(f"Edit group '{item_group}'")
        rename_group_action = group_edit_menu.addAction("Rename group...")
        recolor_group_action = group_edit_menu.addAction("Change group color...")
        notes_group_action = group_edit_menu.addAction("Edit notes...")
        group_edit_menu.addSeparator()
        delete_group_action = group_edit_menu.addAction("Delete group")

        chosen = menu.exec(self._table.viewport().mapToGlobal(pos))
        if chosen is None:
            return

        if copy_group_action and chosen is copy_group_action:
            self._copy_keyword_value(row, col, scope="group")
            return
        if copy_all_action and chosen is copy_all_action:
            self._copy_keyword_value(row, col, scope="all")
            return
        for gname, action in group_actions:
            if chosen is action:
                self._assign_samples_to_group(sample_indices, gname)
                return
        if chosen is custom_group_action:
            self._move_samples_to_group_dialog(sample_indices)
            return
        if edit_action and chosen is edit_action:
            self._rename_sample_dialog(sample_indices[0])
            return
        if chosen is delete_action:
            self._delete_samples(sample_indices)
            return
        if apply_all_group_action and chosen is apply_all_group_action:
            self._apply_all_gates_from(sample_indices[0], scope="group")
            return
        if apply_all_all_action and chosen is apply_all_all_action:
            self._apply_all_gates_from(sample_indices[0], scope="all")
            return
        if chosen is select_group_action:
            self._select_all_in_group(item_group)
            return
        if chosen is rename_group_action:
            self._rename_group_dialog(item_group)
            return
        if chosen is recolor_group_action:
            self._recolor_group_dialog(item_group)
            return
        if chosen is notes_group_action:
            self._edit_group_notes_dialog(item_group)
            return
        if chosen is delete_group_action:
            self._delete_group_dialog(item_group)

    def _rebuild_gate_browser(self) -> None:
        self._updating_gate_browser = True
        self._gate_tree.clear()

        selected_sample_index = self._single_selected_sample_index()
        if selected_sample_index is not None:
            self._populate_gate_tree_for_sample(selected_sample_index)
        else:
            self._populate_gate_tree_aggregate(self._selected_sample_indices())

        self._gate_tree.expandAll()
        self._gate_tree.resizeColumnToContents(0)
        self._updating_gate_browser = False

    def _populate_gate_tree_for_sample(self, sample_index: int) -> None:
        if sample_index < 0 or sample_index >= len(self.workspace.samples):
            return

        workspace_sample = self.workspace.samples[sample_index]
        self._gate_tree.setHeaderLabels(["Population / gate", "Samples", "Events", "% parent"])
        item_by_name: dict[str, QTreeWidgetItem] = {}

        for gate in workspace_sample.gates:
            item = QTreeWidgetItem(
                [
                    gate.name,
                    "1/1",
                    f"{gate.event_count:,}",
                    f"{gate.percentage_parent:.2f}",
                ]
            )
            item.setData(0, Qt.UserRole, gate.name)
            item.setForeground(0, QColor(gate.color_hex))
            parent_item = item_by_name.get(gate.parent_name)
            if parent_item is None:
                self._gate_tree.addTopLevelItem(item)
            else:
                parent_item.addChild(item)
            item_by_name[gate.name] = item

        if not workspace_sample.gates:
            self._gate_tree.addTopLevelItem(QTreeWidgetItem(["No gates in selected sample", "0/1", "—", "—"]))

    def _populate_gate_tree_aggregate(self, sample_indices: list[int]) -> None:
        visible_indices = sample_indices or list(self._row_sample_indices)
        self._gate_tree.setHeaderLabels(["Population / gate", "Samples", "Events", "% parent"])
        if not visible_indices:
            self._gate_tree.addTopLevelItem(QTreeWidgetItem(["No samples loaded", "0/0", "—", "—"]))
            return

        coverage: dict[str, int] = {}
        parent_name_by_gate: dict[str, str] = {}
        event_totals: dict[str, int] = {}
        parent_percent_totals: dict[str, float] = {}

        for sample_index in visible_indices:
            if sample_index < 0 or sample_index >= len(self.workspace.samples):
                continue
            for gate in self.workspace.samples[sample_index].gates:
                coverage[gate.name] = coverage.get(gate.name, 0) + 1
                parent_name_by_gate.setdefault(gate.name, gate.parent_name)
                event_totals[gate.name] = event_totals.get(gate.name, 0) + gate.event_count
                parent_percent_totals[gate.name] = parent_percent_totals.get(gate.name, 0.0) + gate.percentage_parent

        item_by_name: dict[str, QTreeWidgetItem] = {}
        total_samples = len(visible_indices)
        gate_names = sorted(coverage, key=lambda name: (self._gate_depth(name, parent_name_by_gate), name.lower()))
        for gate_name in gate_names:
            count = coverage[gate_name]
            avg_percent = parent_percent_totals[gate_name] / count if count else 0.0
            item = QTreeWidgetItem(
                [
                    gate_name,
                    f"{count}/{total_samples}",
                    f"{event_totals[gate_name]:,}",
                    f"{avg_percent:.2f}",
                ]
            )
            item.setData(0, Qt.UserRole, gate_name)
            parent_name = parent_name_by_gate.get(gate_name, "All events")
            parent_item = item_by_name.get(parent_name)
            if parent_item is None:
                self._gate_tree.addTopLevelItem(item)
            else:
                parent_item.addChild(item)
            item_by_name[gate_name] = item

        if not gate_names:
            self._gate_tree.addTopLevelItem(
                QTreeWidgetItem(["No gates in selected samples", f"0/{total_samples}", "—", "—"])
            )

    @staticmethod
    def _gate_depth(gate_name: str, parent_name_by_gate: dict[str, str]) -> int:
        depth = 0
        current_parent = parent_name_by_gate.get(gate_name, "All events")
        while current_parent != "All events":
            depth += 1
            current_parent = parent_name_by_gate.get(current_parent, "All events")
        return depth

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        row = item.row()
        col = item.column()
        if row >= len(self._row_sample_indices):
            return

        sample_index = self._row_sample_indices[row]
        workspace_sample = self.workspace.samples[sample_index]

        if col == 0:
            workspace_sample.display_name_override = item.text().strip() or None
            item.setBackground(_NAME_BG)
            self._notify_workspace_changed()
            return

        if col == 1:
            group_name = item.text().strip() or "Ungrouped"
            self.workspace.ensure_group(group_name)
            workspace_sample.group_name = group_name
            item.setText(group_name)
            item.setBackground(_GROUP_BG)
            self._notify_workspace_changed()
            return

        kw_offset = col - self._n_fixed_cols
        if 0 <= kw_offset < len(self._keyword_columns):
            keyword = self._keyword_columns[kw_offset]
            workspace_sample.keywords[keyword] = item.text()
            item.setBackground(_KEYWORD_BG)
            self._notify_workspace_changed(refresh_table=False)

    def _on_add_keyword(self) -> None:
        name, ok = QInputDialog.getText(
            self,
            "Add keyword column",
            "Keyword name (e.g. Clone, Time, Dose):",
        )
        if not ok:
            return
        normalized = name.strip()
        if not normalized:
            return
        if normalized in self.workspace.keyword_columns:
            QMessageBox.warning(self, "Add keyword", f'The keyword "{normalized}" already exists.')
            return
        self.workspace.add_keyword_column(normalized)
        self._notify_workspace_changed()

    def _on_add_statistics(self) -> None:
        dialog = StatisticsColumnDialog(self.workspace, self.statistics_service, self)
        if not dialog.exec():
            return

        population_name = dialog.selected_population_name()
        channel_name = dialog.selected_channel_name()
        statistic_keys = dialog.selected_metric_keys()
        if not population_name:
            QMessageBox.warning(self, "Statistics", "Select a population.")
            return
        if not statistic_keys:
            QMessageBox.warning(self, "Statistics", "Select at least one statistic.")
            return
        if not channel_name and any(
            statistic_key in {"mean", "median", "std", "cv", "min", "max", "p5", "p95"}
            for statistic_key in statistic_keys
        ):
            QMessageBox.warning(self, "Statistics", "Select a channel.")
            return

        for column in self.statistics_service.make_columns(
            group_name=dialog.selected_group_name(),
            population_name=population_name,
            channel_name=channel_name,
            statistic_keys=statistic_keys,
        ):
            self.workspace.add_statistic_column(column)
        self._notify_workspace_changed()

    def _on_add_samples(self) -> None:
        if self._on_add_samples_requested is None:
            return
        self._on_add_samples_requested(self._current_group_name_for_actions())

    def _on_create_group(self) -> None:
        name, ok = QInputDialog.getText(
            self,
            "Create group",
            "Group name:",
        )
        if not ok:
            return
        normalized = name.strip()
        if not normalized:
            QMessageBox.warning(self, "Create group", "Group name cannot be empty.")
            return
        self._ensure_group_with_color(normalized)
        self.refresh()
        row = self._group_list.row(self._find_group_list_item(normalized))
        if row >= 0:
            self._group_list.setCurrentRow(row)
        self._notify_workspace_changed(refresh_table=False)

    def _ensure_group_with_color(self, group_name: str) -> None:
        """Create group if new, then prompt for color."""
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

    def _on_rename_group(self) -> None:
        group_name = self._current_group_name_for_actions()
        if group_name is None:
            return
        group = self.workspace.groups.get(group_name)
        if group is None:
            return
        new_name, ok = QInputDialog.getText(
            self,
            "Rename group",
            "Group name:",
            text=group.name,
        )
        if not ok:
            return
        normalized = new_name.strip()
        if not normalized:
            QMessageBox.warning(self, "Rename group", "Group name cannot be empty.")
            return
        self.workspace.rename_group(group_name, normalized)
        current_filter = self._group_combo.currentData()
        self.refresh()
        if current_filter == group_name:
            combo_index = self._group_combo.findData(normalized)
            if combo_index >= 0:
                self._group_combo.setCurrentIndex(combo_index)
        row = self._group_list.row(self._find_group_list_item(normalized))
        if row >= 0:
            self._group_list.setCurrentRow(row)
        self._notify_workspace_changed(refresh_table=False)

    def _on_recolor_group(self) -> None:
        group_name = self._current_group_name_for_actions()
        if group_name is None:
            return
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
        self.refresh()
        self._notify_workspace_changed(refresh_table=False)

    def _on_edit_group_notes(self) -> None:
        group_name = self._current_group_name_for_actions()
        if group_name is None:
            return
        group = self.workspace.groups.get(group_name)
        if group is None:
            return
        notes, ok = QInputDialog.getMultiLineText(
            self,
            "Group notes",
            "Notes:",
            text=group.notes,
        )
        if not ok:
            return
        group.notes = notes.strip()
        self._refresh_group_notes()
        self._notify_workspace_changed(refresh_table=False)

    def _on_delete_group(self) -> None:
        group_name = self._current_group_name_for_actions()
        if group_name is None:
            return
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
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.workspace.delete_group(group_name, fallback_group_name=DEFAULT_GROUP_NAME)
        self.refresh()
        self._notify_workspace_changed(refresh_table=False)

    def _find_group_list_item(self, group_name: str) -> QListWidgetItem | None:
        for row in range(self._group_list.count()):
            item = self._group_list.item(row)
            if item.data(Qt.UserRole) == group_name:
                return item
        return None

    def _copy_keyword_value(self, row: int, col: int, *, scope: str) -> None:
        keyword_name = self._keyword_name_for_column(col)
        if keyword_name is None or row >= len(self._row_sample_indices):
            return

        source_sample = self.workspace.samples[self._row_sample_indices[row]]
        value = source_sample.keywords.get(keyword_name, "")
        if scope == "group":
            target_samples = [
                workspace_sample
                for workspace_sample in self.workspace.samples
                if workspace_sample.group_name == source_sample.group_name
            ]
        else:
            target_samples = list(self.workspace.samples)

        for workspace_sample in target_samples:
            workspace_sample.keywords[keyword_name] = value
        self._notify_workspace_changed()

    def _assign_samples_to_group(self, sample_indices: list[int], group_name: str) -> None:
        normalized = group_name.strip() or DEFAULT_GROUP_NAME
        self.workspace.ensure_group(normalized)
        for sample_index in sample_indices:
            if 0 <= sample_index < len(self.workspace.samples):
                self.workspace.samples[sample_index].group_name = normalized
        self._notify_workspace_changed()

    def _remove_samples_from_group(self, sample_indices: list[int]) -> None:
        self._assign_samples_to_group(sample_indices, DEFAULT_GROUP_NAME)

    def _move_samples_to_group_dialog(self, sample_indices: list[int]) -> None:
        if not sample_indices:
            return
        current_groups = sorted(self.workspace.groups)
        initial_group = self.workspace.samples[sample_indices[0]].group_name
        group_name, ok = QInputDialog.getItem(
            self,
            "Move samples to group",
            "Target group (or type a new group name):",
            current_groups,
            current=max(0, current_groups.index(initial_group)) if initial_group in current_groups else 0,
            editable=True,
        )
        if not ok:
            return
        normalized = group_name.strip() or DEFAULT_GROUP_NAME
        self._ensure_group_with_color(normalized)
        self._assign_samples_to_group(sample_indices, normalized)

    def _rename_sample_dialog(self, sample_index: int) -> None:
        if sample_index < 0 or sample_index >= len(self.workspace.samples):
            return
        ws = self.workspace.samples[sample_index]
        new_name, ok = QInputDialog.getText(
            self, "Rename sample", "Sample name:", text=ws.sample_name
        )
        if not ok:
            return
        ws.display_name_override = new_name.strip() or None
        self._notify_workspace_changed()

    def _apply_all_gates_from(self, source_index: int, *, scope: str) -> None:
        if source_index < 0 or source_index >= len(self.workspace.samples):
            return
        source = self.workspace.samples[source_index]
        gate_names = [g.name for g in source.gates]
        if not gate_names:
            return
        target_group = source.group_name if scope == "group" else None
        self._apply_selected_gates(source_index, gate_names, target_group)

    def _select_all_in_group(self, group_name: str) -> None:
        self._table.clearSelection()
        for row, sample_index in enumerate(self._row_sample_indices):
            if self.workspace.samples[sample_index].group_name == group_name:
                self._table.selectRow(row)

    def _rename_group_dialog(self, group_name: str) -> None:
        group = self.workspace.groups.get(group_name)
        if group is None:
            return
        new_name, ok = QInputDialog.getText(
            self, "Rename group", "Group name:", text=group.name
        )
        if not ok:
            return
        normalized = new_name.strip()
        if not normalized:
            QMessageBox.warning(self, "Rename group", "Group name cannot be empty.")
            return
        self.workspace.rename_group(group_name, normalized)
        current_filter = self._group_combo.currentData()
        self.refresh()
        if current_filter == group_name:
            idx = self._group_combo.findData(normalized)
            if idx >= 0:
                self._group_combo.setCurrentIndex(idx)
        self._notify_workspace_changed(refresh_table=False)

    def _recolor_group_dialog(self, group_name: str) -> None:
        group = self.workspace.groups.get(group_name)
        if group is None:
            return
        color = QColorDialog.getColor(
            QColor(group.color_hex), self, f"Select color for '{group_name}'"
        )
        if not color.isValid():
            return
        group.color_hex = color.name().lower()
        self.refresh()
        self._notify_workspace_changed(refresh_table=False)

    def _edit_group_notes_dialog(self, group_name: str) -> None:
        group = self.workspace.groups.get(group_name)
        if group is None:
            return
        notes, ok = QInputDialog.getMultiLineText(
            self, "Group notes", "Notes:", text=group.notes
        )
        if not ok:
            return
        group.notes = notes.strip()
        self._refresh_group_notes()
        self._notify_workspace_changed(refresh_table=False)

    def _delete_group_dialog(self, group_name: str) -> None:
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
            f'Delete the "{group_name}" group?\nSamples will be moved to "{DEFAULT_GROUP_NAME}".',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.workspace.delete_group(group_name, fallback_group_name=DEFAULT_GROUP_NAME)
        self.refresh()
        self._notify_workspace_changed(refresh_table=False)

    def _delete_samples(self, sample_indices: list[int]) -> None:
        if not sample_indices:
            return
        answer = QMessageBox.question(
            self,
            "Delete samples",
            f"Delete {len(sample_indices)} selected sample(s)?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        for sample_index in sorted(set(sample_indices), reverse=True):
            self.workspace.remove_sample(sample_index)
        self._notify_workspace_changed()

    def _on_remove_statistics(self) -> None:
        if not self.workspace.statistic_columns:
            QMessageBox.information(self, "Remove statistic", "There are no statistic columns to remove.")
            return

        options = [column.header for column in self.workspace.statistic_columns]
        options.append("Clear all statistic columns")
        selected, ok = QInputDialog.getItem(
            self,
            "Remove statistic column",
            "Select the statistic column to remove:",
            options,
            editable=False,
        )
        if not ok:
            return

        if selected == "Clear all statistic columns":
            answer = QMessageBox.question(
                self,
                "Clear statistic columns",
                "Delete all statistic columns from the Sample Manager?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
            self.workspace.clear_statistic_columns()
            self._notify_workspace_changed()
            return

        column_index = options.index(selected)
        self.workspace.remove_statistic_column(column_index)
        self._notify_workspace_changed()

    def _on_remove_keyword(self) -> None:
        if not self.workspace.keyword_columns:
            QMessageBox.information(self, "Remove keyword", "There are no keyword columns to remove.")
            return
        name, ok = QInputDialog.getItem(
            self,
            "Remove keyword column",
            "Select the keyword to remove:",
            self.workspace.keyword_columns,
            editable=False,
        )
        if not ok:
            return
        answer = QMessageBox.question(
            self,
            "Remove keyword",
            f'Delete the "{name}" column and all its values?\nThis cannot be undone.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.workspace.remove_keyword_column(name)
        self._notify_workspace_changed()

    def _on_delete_selected_samples(self) -> None:
        sample_indices = self._selected_sample_indices()
        if not sample_indices:
            QMessageBox.information(self, "Delete samples", "Select one or more samples first.")
            return
        self._delete_samples(sample_indices)

    def _on_move_selected_samples_to_group(self) -> None:
        sample_indices = self._selected_sample_indices()
        if not sample_indices:
            QMessageBox.information(self, "Move to group", "Select one or more samples first.")
            return
        self._move_samples_to_group_dialog(sample_indices)

    def _on_select_equivalent_gates(self) -> None:
        """Prompt for a gate name and select all table rows whose sample has that gate."""
        gate_names: list[str] = []
        seen: set[str] = set()
        for ws_sample in self.workspace.samples:
            for gate in ws_sample.gates:
                if gate.name not in seen:
                    gate_names.append(gate.name)
                    seen.add(gate.name)
        gate_names.sort()

        if not gate_names:
            QMessageBox.information(self, "Match gate", "No gates found in the workspace.")
            return

        gate_name, accepted = QInputDialog.getItem(
            self, "Match gate", "Select gate name to highlight:", gate_names, 0, False
        )
        if not accepted:
            return
        self.select_samples_with_gate(gate_name)

    def select_samples_with_gate(self, gate_name: str) -> None:
        """Select all table rows whose sample has a gate with the given name."""
        self._table.clearSelection()
        for row, ws_idx in enumerate(self._row_sample_indices):
            if ws_idx < 0 or ws_idx >= len(self.workspace.samples):
                continue
            ws_sample = self.workspace.samples[ws_idx]
            if any(g.name == gate_name for g in ws_sample.gates):
                for col in range(self._table.columnCount()):
                    item = self._table.item(row, col)
                    if item:
                        item.setSelected(True)

    def _on_gate_tree_context_menu(self, pos) -> None:
        source_sample_index = self._single_selected_sample_index()
        if source_sample_index is None:
            QMessageBox.information(
                self,
                "Apply gates",
                "Select exactly one source sample in the table before propagating gates.",
            )
            return

        selected_items = [
            item
            for item in self._gate_tree.selectedItems()
            if item.data(0, Qt.UserRole)
        ]
        if not selected_items:
            item = self._gate_tree.itemAt(pos)
            if item is None or not item.data(0, Qt.UserRole):
                return
            selected_items = [item]

        gate_names = [str(item.data(0, Qt.UserRole)) for item in selected_items]
        menu = QMenu(self)
        same_group_action = menu.addAction("Apply selected gate(s) to the same group")
        all_samples_action = menu.addAction("Apply selected gate(s) to all samples")
        group_menu = menu.addMenu("Apply selected gate(s) to group")
        group_actions: dict[object, str] = {}
        for group_name in sorted(self.workspace.groups):
            action = group_menu.addAction(group_name)
            group_actions[action] = group_name

        chosen_action = menu.exec(self._gate_tree.mapToGlobal(pos))
        if chosen_action is None:
            return

        source_group = self.workspace.samples[source_sample_index].group_name
        if chosen_action is same_group_action:
            self._apply_selected_gates(source_sample_index, gate_names, source_group)
            return
        if chosen_action is all_samples_action:
            self._apply_selected_gates(source_sample_index, gate_names, None)
            return
        target_group_name = group_actions.get(chosen_action)
        if target_group_name is not None:
            self._apply_selected_gates(source_sample_index, gate_names, target_group_name)

    def _apply_selected_gates(
        self,
        source_sample_index: int,
        gate_names: list[str],
        target_group_name: str | None,
    ) -> None:
        applied_count, failures, scope_label = self.gate_service.propagate_gates(
            self.workspace,
            source_sample_index=source_sample_index,
            gate_names=gate_names,
            target_group_name=target_group_name,
        )

        if failures and applied_count == 0:
            QMessageBox.warning(self, "Apply gates", "\n".join(failures))
            return

        if failures:
            QMessageBox.warning(self, "Apply gates", "\n".join(failures))

        if applied_count == 0 and not failures:
            QMessageBox.information(self, "Apply gates", f"No target samples available in {scope_label}.")
            return

        self._notify_workspace_changed()

    def _notify_workspace_changed(self, *, refresh_table: bool = True) -> None:
        if self._on_workspace_changed is not None:
            self._on_workspace_changed()
        if refresh_table:
            self.refresh()
        else:
            self._rebuild_gate_browser()

    def _on_export_csv(self) -> None:
        if self._table.rowCount() == 0:
            QMessageBox.information(self, "Export CSV", "There is no data to export.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export sample table as CSV",
            "sample_table.csv",
            "CSV files (*.csv)",
        )
        if not file_path:
            return

        headers = [
            self._table.horizontalHeaderItem(col).text()
            for col in range(self._table.columnCount())
        ]
        rows: list[list[str]] = []
        for row in range(self._table.rowCount()):
            row_data: list[str] = []
            for col in range(self._table.columnCount()):
                item = self._table.item(row, col)
                row_data.append(item.text() if item is not None else "")
            rows.append(row_data)

        try:
            with open(file_path, "w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(headers)
                writer.writerows(rows)
        except OSError as exc:
            QMessageBox.critical(self, "Export CSV", f"Could not save the file:\n{exc}")
