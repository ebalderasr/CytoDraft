from __future__ import annotations

import csv

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from cytodraft.models.workspace import WorkspaceState

# Background color for editable keyword cells
_KEYWORD_BG = QColor("#eef6ff")


class SampleTableWindow(QDialog):
    """Spreadsheet view: one row per sample, gate statistics + user keyword columns."""

    def __init__(self, workspace: WorkspaceState, parent=None) -> None:
        super().__init__(parent)
        self.workspace = workspace

        self.setWindowTitle("Sample Table")
        self.setMinimumSize(800, 480)
        self.resize(1200, 620)
        # Allow resize/maximize independently of the main window
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowCloseButtonHint
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
        )

        # Internal state updated on every rebuild
        self._row_sample_indices: list[int] = []
        self._n_fixed_cols: int = 0
        self._keyword_columns: list[str] = []
        self._gate_col_specs: list[tuple[str, str]] = []  # (gate_name, stat_key)

        self._build_ui()
        self.refresh()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # ── Top toolbar ────────────────────────────────────────────────
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        toolbar.setContentsMargins(0, 0, 0, 0)

        toolbar.addWidget(QLabel("Group:"))
        self._group_combo = QComboBox()
        self._group_combo.setMinimumWidth(140)
        self._group_combo.currentIndexChanged.connect(self._rebuild_table)
        toolbar.addWidget(self._group_combo)

        toolbar.addStretch(1)

        self._add_kw_btn = QPushButton("+ Add keyword")
        self._add_kw_btn.setProperty("variant", "subtle")
        self._add_kw_btn.setToolTip("Add a new editable keyword column to all samples")
        self._add_kw_btn.clicked.connect(self._on_add_keyword)

        self._remove_kw_btn = QPushButton("Remove keyword")
        self._remove_kw_btn.setProperty("variant", "danger")
        self._remove_kw_btn.setToolTip("Remove an existing keyword column")
        self._remove_kw_btn.clicked.connect(self._on_remove_keyword)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setProperty("variant", "subtle")
        self._refresh_btn.setToolTip("Reload data from the workspace")
        self._refresh_btn.clicked.connect(self.refresh)

        self._export_btn = QPushButton("Export CSV")
        self._export_btn.setProperty("variant", "primary")
        self._export_btn.setToolTip("Export this table to a CSV file")
        self._export_btn.clicked.connect(self._on_export_csv)

        for btn in (self._add_kw_btn, self._remove_kw_btn, self._refresh_btn, self._export_btn):
            toolbar.addWidget(btn)

        # ── Legend label ───────────────────────────────────────────────
        legend = QLabel("Gate statistics are read-only. Keyword columns (blue) are editable.")
        legend.setStyleSheet("color: #6b7280; font-size: 11px;")

        # ── Table ──────────────────────────────────────────────────────
        self._table = QTableWidget()
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.SelectedClicked)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.setWordWrap(False)
        self._table.itemChanged.connect(self._on_item_changed)

        # ── Main layout ────────────────────────────────────────────────
        layout = QVBoxLayout()
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)
        layout.addLayout(toolbar)
        layout.addWidget(legend)
        layout.addWidget(self._table)
        self.setLayout(layout)

    # ------------------------------------------------------------------
    # Public refresh — call this whenever the workspace changes
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Re-populate group filter and rebuild the table."""
        current_group = self._group_combo.currentData()

        self._group_combo.blockSignals(True)
        self._group_combo.clear()
        self._group_combo.addItem("All groups", None)
        for group_name in sorted(self.workspace.groups):
            self._group_combo.addItem(group_name, group_name)

        # Restore previously selected group if it still exists
        restored = False
        for i in range(self._group_combo.count()):
            if self._group_combo.itemData(i) == current_group:
                self._group_combo.setCurrentIndex(i)
                restored = True
                break
        if not restored:
            self._group_combo.setCurrentIndex(0)

        self._group_combo.blockSignals(False)

        self._rebuild_table()

    # ------------------------------------------------------------------
    # Table construction
    # ------------------------------------------------------------------

    def _rebuild_table(self) -> None:
        selected_group: str | None = self._group_combo.currentData()
        samples = self.workspace.samples_in_group(selected_group)

        # Collect ordered unique gate names present in the visible samples
        gate_names: list[str] = []
        seen_gates: set[str] = set()
        for _, ws in samples:
            for gate in ws.gates:
                if gate.name not in seen_gates:
                    gate_names.append(gate.name)
                    seen_gates.add(gate.name)

        keyword_columns = list(self.workspace.keyword_columns)

        # Build column specs -------------------------------------------------
        # Fixed columns (read-only)
        fixed_headers = ["Sample", "Group", "Total events"]
        # Gate stat columns: events + % parent for each gate (read-only)
        gate_col_specs: list[tuple[str, str]] = []
        for gname in gate_names:
            gate_col_specs.append((gname, "events"))
            gate_col_specs.append((gname, "% parent"))
        gate_headers = [f"{g}  —  {s}" for g, s in gate_col_specs]
        # Keyword columns (editable)
        kw_headers = keyword_columns

        all_headers = fixed_headers + gate_headers + kw_headers
        n_fixed = len(fixed_headers) + len(gate_headers)

        # Store for use in _on_item_changed
        self._row_sample_indices = []
        self._n_fixed_cols = n_fixed
        self._keyword_columns = keyword_columns
        self._gate_col_specs = gate_col_specs

        # Populate table -----------------------------------------------------
        self._table.blockSignals(True)
        self._table.clearContents()
        self._table.setColumnCount(len(all_headers))
        self._table.setHorizontalHeaderLabels(all_headers)
        self._table.setRowCount(len(samples))

        for row, (sample_idx, ws) in enumerate(samples):
            self._row_sample_indices.append(sample_idx)
            gate_by_name = {g.name: g for g in ws.gates}

            # Fixed: Sample, Group, Total events
            self._set_readonly(row, 0, ws.sample.file_name)
            self._set_readonly(row, 1, ws.group_name)
            self._set_readonly(row, 2, f"{ws.sample.event_count:,}")

            # Gate stat columns
            for col_offset, (gname, stat) in enumerate(gate_col_specs):
                col = len(fixed_headers) + col_offset
                gate = gate_by_name.get(gname)
                if gate is None:
                    self._set_readonly(row, col, "—")
                elif stat == "events":
                    self._set_readonly(row, col, f"{gate.event_count:,}")
                else:  # % parent
                    self._set_readonly(row, col, f"{gate.percentage_parent:.2f}")

            # Keyword columns (editable, highlighted blue)
            for kw_offset, keyword in enumerate(keyword_columns):
                col = n_fixed + kw_offset
                value = ws.keywords.get(keyword, "")
                item = QTableWidgetItem(value)
                item.setBackground(_KEYWORD_BG)
                self._table.setItem(row, col, item)

        # Style keyword column headers to match their cells
        for kw_offset in range(len(keyword_columns)):
            col = n_fixed + kw_offset
            header_item = self._table.horizontalHeaderItem(col)
            if header_item:
                header_item.setForeground(QColor("#1d4ed8"))

        self._table.blockSignals(False)
        self._table.resizeColumnsToContents()

        # Give keyword columns a sensible minimum width
        for kw_offset in range(len(keyword_columns)):
            col = n_fixed + kw_offset
            if self._table.columnWidth(col) < 120:
                self._table.setColumnWidth(col, 120)

    def _set_readonly(self, row: int, col: int, text: str) -> None:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        self._table.setItem(row, col, item)

    # ------------------------------------------------------------------
    # Keyword cell edits
    # ------------------------------------------------------------------

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        col = item.column()
        row = item.row()
        kw_offset = col - self._n_fixed_cols
        if kw_offset < 0 or kw_offset >= len(self._keyword_columns):
            return
        if row >= len(self._row_sample_indices):
            return
        keyword = self._keyword_columns[kw_offset]
        sample_idx = self._row_sample_indices[row]
        self.workspace.samples[sample_idx].keywords[keyword] = item.text()
        # Keep blue background after edit
        item.setBackground(_KEYWORD_BG)

    # ------------------------------------------------------------------
    # Keyword column management
    # ------------------------------------------------------------------

    def _on_add_keyword(self) -> None:
        name, ok = QInputDialog.getText(
            self,
            "Add keyword column",
            "Keyword name (e.g. Clona, Tiempo, Dosis):",
        )
        if not ok:
            return
        name = name.strip()
        if not name:
            return
        if name in self.workspace.keyword_columns:
            QMessageBox.warning(self, "Add keyword", f'La keyword "{name}" ya existe.')
            return
        self.workspace.add_keyword_column(name)
        self._rebuild_table()

    def _on_remove_keyword(self) -> None:
        if not self.workspace.keyword_columns:
            QMessageBox.information(self, "Remove keyword", "No hay keyword columns para eliminar.")
            return
        name, ok = QInputDialog.getItem(
            self,
            "Remove keyword column",
            "Selecciona la keyword a eliminar:",
            self.workspace.keyword_columns,
            editable=False,
        )
        if not ok:
            return
        reply = QMessageBox.question(
            self,
            "Remove keyword",
            f'¿Eliminar la columna "{name}" y todos sus valores?\nEsta acción no se puede deshacer.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.workspace.remove_keyword_column(name)
        self._rebuild_table()

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _on_export_csv(self) -> None:
        if self._table.rowCount() == 0:
            QMessageBox.information(self, "Export CSV", "No hay datos para exportar.")
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
            self._table.horizontalHeaderItem(c).text()
            for c in range(self._table.columnCount())
        ]
        rows = []
        for r in range(self._table.rowCount()):
            row_data = []
            for c in range(self._table.columnCount()):
                item = self._table.item(r, c)
                row_data.append(item.text() if item else "")
            rows.append(row_data)

        try:
            with open(file_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                writer.writerows(rows)
        except OSError as exc:
            QMessageBox.critical(self, "Export CSV", f"Error al guardar el archivo:\n{exc}")
            return

        self.statusBar().showMessage(f"Exported to {file_path}", 4000) if hasattr(self, "statusBar") else None
