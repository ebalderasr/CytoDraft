"""Compensation Manager window.

All compensation functionality in one place:
  - Add / remove control samples (from existing workspace samples or imported from disk)
  - Edit control metadata (type, fluorochrome, target channel, notes)
  - Assign positive and negative populations via gate drop-downs
  - Edit the spillover matrix
  - Verify compensation with a live scatter plot

Signals emitted to the main window
-----------------------------------
add_fcs_to_group_requested(str group_name)
    Import new FCS files directly into the compensation group.
workspace_changed()
    Any workspace mutation (metadata, populations, matrix) that requires
    the main window to refresh its UI.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from cytodraft.core.compensation import (
    apply_compensation,
    extract_spillover,
    flat_to_matrix,
    matrix_to_flat,
    resolve_fluoro_indices,
)
from cytodraft.models.workspace import (
    COMPENSATION_GROUP_NAME,
    DEFAULT_GROUP_NAME,
    CompensationSampleMetadata,
    WorkspaceState,
)

_MAX_SCATTER_POINTS = 15_000
_DIAG_BG = QColor("#f0fdf4")
_EDIT_BG = QColor("#ffffff")

_CONTROL_TYPES = [
    ("Single stain", "single_stain"),
    ("Unstained", "unstained"),
    ("FMO", "fmo"),
    ("Beads", "beads"),
    ("Autofluorescence", "autofluorescence"),
]


# ── Helpers ────────────────────────────────────────────────────────────────────

def _vline() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.VLine)
    sep.setFrameShadow(QFrame.Plain)
    sep.setFixedWidth(1)
    sep.setStyleSheet("background: #d4dde7; border: none;")
    return sep


# ── Spillover matrix table ─────────────────────────────────────────────────────

class _MatrixTable(QTableWidget):
    matrix_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._n = 0
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        self.itemChanged.connect(self._on_item_changed)

    def load(self, channels: list[str], matrix: np.ndarray) -> None:
        n = len(channels)
        self._n = n
        self.blockSignals(True)
        self.setRowCount(n)
        self.setColumnCount(n)
        self.setHorizontalHeaderLabels(channels)
        self.setVerticalHeaderLabels(channels)
        for r in range(n):
            for c in range(n):
                item = QTableWidgetItem(f"{matrix[r, c]:.4f}")
                item.setTextAlignment(Qt.AlignCenter)
                if r == c:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    item.setBackground(_DIAG_BG)
                    item.setForeground(QColor("#166534"))
                else:
                    item.setBackground(_EDIT_BG)
                self.setItem(r, c, item)
        self.resizeColumnsToContents()
        self.blockSignals(False)

    def current_matrix(self) -> tuple[list[str], np.ndarray] | None:
        n = self._n
        if n == 0:
            return None
        headers = [
            (self.horizontalHeaderItem(c).text() if self.horizontalHeaderItem(c) else str(c))
            for c in range(n)
        ]
        values: list[float] = []
        for r in range(n):
            for c in range(n):
                item = self.item(r, c)
                try:
                    values.append(float(item.text()) if item else (100.0 if r == c else 0.0))
                except ValueError:
                    values.append(100.0 if r == c else 0.0)
        return headers, flat_to_matrix(values, n)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if item.row() == item.column():
            return
        try:
            val = float(item.text())
        except ValueError:
            val = 0.0
            item.setText("0.0000")
        val = max(-200.0, min(200.0, val))
        self.matrix_changed.emit()


# ── Pairwise scatter grid ──────────────────────────────────────────────────────

_MAX_GRID_CHANNELS = 10   # cap to avoid rendering too many plots at once
_MAX_PTS_PER_PLOT = 4_000  # subsampling limit per plot


class _PairScatterGrid(QWidget):
    """N×N grid of scatter plots for visualising spillover and compensation quality.

    Layout follows the spillover matrix convention:
      - Columns  = source fluorochrome (X axis)
      - Rows     = detector that receives spillover (Y axis)
      - Diagonal = channel name label

    For any off-diagonal cell (r, c):
      - Gray dots  = raw (uncompensated) events
      - Blue dots  = compensated events
      - Correctly compensated: events should cluster near the X axis
        (detector r reads ~0 when only fluorochrome c is present)

    The grid updates in-place when the matrix changes but the sample and
    channel list stay the same, avoiding a full widget rebuild.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._workspace: WorkspaceState | None = None
        self._spill_channels: list[str] = []
        self._spill_matrix: np.ndarray | None = None

        # Cached data for in-place updates
        self._cached_sample_idx: int | None = None
        self._cached_channels: list[str] = []
        self._fluoro_indices: list[int] | None = None
        self._sel: np.ndarray | None = None        # subsample index array
        self._raw_sub: np.ndarray | None = None    # raw events, subsampled
        self._comp_sub: np.ndarray | None = None   # compensated events, subsampled

        # Grid state
        self._n_grid: int = 0
        self._raw_items: list[list[pg.ScatterPlotItem | None]] = []
        self._comp_items: list[list[pg.ScatterPlotItem | None]] = []

        self._build_ui()

    # ── Public API (same interface as the old _ScatterPane) ────────────────────

    def set_workspace(self, workspace: WorkspaceState) -> None:
        self._workspace = workspace
        self._refresh_sample_combo()

    def update_spillover(self, channels: list[str], matrix: np.ndarray) -> None:
        self._spill_channels = list(channels)
        self._spill_matrix = matrix.copy()

        sample_idx = self._sample_combo.currentData()
        same_context = (
            channels == self._cached_channels
            and sample_idx == self._cached_sample_idx
            and self._n_grid > 0
        )
        if same_context:
            self._recompute_comp_sub()
            self._update_scatter_data()
        else:
            self._rebuild_grid()

    def clear_spillover(self) -> None:
        self._spill_channels = []
        self._spill_matrix = None
        self._rebuild_grid()

    # ── Build UI ───────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Controls row
        ctrl = QHBoxLayout()
        ctrl.setSpacing(8)

        ctrl.addWidget(QLabel("Sample:"))
        self._sample_combo = QComboBox()
        self._sample_combo.setMinimumWidth(200)
        self._sample_combo.currentIndexChanged.connect(self._on_sample_changed)
        ctrl.addWidget(self._sample_combo)

        self._raw_check = QCheckBox("Show raw (gray)")
        self._raw_check.setChecked(True)
        self._raw_check.toggled.connect(self._on_raw_toggled)
        ctrl.addWidget(self._raw_check)

        ctrl.addStretch(1)
        self._info_lbl = QLabel()
        self._info_lbl.setStyleSheet("color: #6b7280; font-size: 11px;")
        ctrl.addWidget(self._info_lbl)

        layout.addLayout(ctrl)

        # Scroll area wrapping the grid of plots
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._grid_container = QWidget()
        self._grid_layout = QGridLayout(self._grid_container)
        self._grid_layout.setSpacing(3)
        self._grid_layout.setContentsMargins(4, 4, 4, 4)
        scroll.setWidget(self._grid_container)
        layout.addWidget(scroll, stretch=1)

        hint = QLabel(
            "Columns = source fluorochrome (X axis)  ·  Rows = detector (Y axis)  ·  "
            "Gray = raw  ·  Blue = compensated  ·  "
            "Well-compensated: blue cloud is vertical / axis-aligned, no diagonal tilt."
        )
        hint.setStyleSheet("color: #6b7280; font-size: 11px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

    # ── Sample combo ───────────────────────────────────────────────────────────

    def _refresh_sample_combo(self) -> None:
        prev_idx = self._sample_combo.currentData()
        self._sample_combo.blockSignals(True)
        self._sample_combo.clear()
        if self._workspace:
            for i, ws in enumerate(self._workspace.samples):
                self._sample_combo.addItem(ws.sample_name, i)
        # Restore previous selection if still valid
        if prev_idx is not None:
            for j in range(self._sample_combo.count()):
                if self._sample_combo.itemData(j) == prev_idx:
                    self._sample_combo.setCurrentIndex(j)
                    break
        self._sample_combo.blockSignals(False)
        self._rebuild_grid()

    def _on_sample_changed(self) -> None:
        self._rebuild_grid()

    # ── Raw/comp visibility toggle (no rebuild needed) ─────────────────────────

    def _on_raw_toggled(self, checked: bool) -> None:
        for row_items in self._raw_items:
            for item in row_items:
                if item is not None:
                    item.setVisible(checked)

    # ── Grid build ─────────────────────────────────────────────────────────────

    def _clear_grid(self) -> None:
        while self._grid_layout.count():
            child = self._grid_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self._raw_items = []
        self._comp_items = []
        self._n_grid = 0
        self._cached_sample_idx = None
        self._cached_channels = []
        self._fluoro_indices = None
        self._sel = None
        self._raw_sub = None
        self._comp_sub = None

    def _rebuild_grid(self) -> None:
        self._clear_grid()

        if not self._spill_channels or self._spill_matrix is None:
            self._info_lbl.setText("No spillover matrix loaded.")
            return

        if not self._workspace:
            self._info_lbl.setText("No workspace.")
            return

        sample_idx = self._sample_combo.currentData()
        if sample_idx is None or sample_idx >= len(self._workspace.samples):
            self._info_lbl.setText("Select a sample above.")
            return

        sample = self._workspace.samples[sample_idx].sample

        n = min(len(self._spill_channels), _MAX_GRID_CHANNELS)
        channels = self._spill_channels[:n]
        matrix = self._spill_matrix[:n, :n]

        indices = resolve_fluoro_indices(channels, sample)
        if indices is None:
            self._info_lbl.setText(
                "Channel names in the matrix don't match this sample's channels. "
                "Try a different sample."
            )
            return

        # Subsample raw events (consistent seed so plots are stable)
        raw = sample.events
        n_events = raw.shape[0]
        max_pts = min(_MAX_PTS_PER_PLOT, n_events)
        if n_events > max_pts:
            rng = np.random.default_rng(42)
            self._sel = rng.choice(n_events, max_pts, replace=False)
        else:
            self._sel = np.arange(n_events)

        self._cached_sample_idx = sample_idx
        self._cached_channels = list(channels)
        self._fluoro_indices = indices
        self._raw_sub = raw[self._sel]  # shape (pts, total_channels)
        self._recompute_comp_sub()

        self._n_grid = n
        self._raw_items = [[None] * n for _ in range(n)]
        self._comp_items = [[None] * n for _ in range(n)]

        # Cell size: smaller grids get larger plots
        cell_size = max(90, min(180, 900 // n))

        show_raw = self._raw_check.isChecked()

        for r in range(n):
            for c in range(n):
                plot = self._make_cell_plot(cell_size)

                if r == c:
                    self._fill_diagonal(plot, channels[r])
                else:
                    xi = indices[c]
                    yi = indices[r]
                    self._fill_scatter_cell(
                        plot, r, c, xi, yi,
                        edge_left=(c == 0),
                        edge_bottom=(r == n - 1),
                        ch_x=channels[c],
                        ch_y=channels[r],
                        show_raw=show_raw,
                    )

                self._grid_layout.addWidget(plot, r, c)

        suffix = ""
        if len(self._spill_channels) > n:
            suffix = f" (first {n} of {len(self._spill_channels)} channels shown)"
        self._info_lbl.setText(
            f"{n}×{n} grid · {len(self._sel):,} events per plot{suffix}"
        )

    @staticmethod
    def _make_cell_plot(size: int) -> pg.PlotWidget:
        plot = pg.PlotWidget(background="#fbfcfe")
        plot.setFixedSize(size, size)
        plot.hideButtons()
        plot.setMenuEnabled(False)
        plot.showGrid(x=True, y=True, alpha=0.2)
        for ax in ("left", "bottom", "right", "top"):
            plot.getAxis(ax).setStyle(tickLength=3, tickTextOffset=2)
        return plot

    @staticmethod
    def _fill_diagonal(plot: pg.PlotWidget, label: str) -> None:
        """Diagonal cell: show channel name, no data."""
        plot.hideAxis("left")
        plot.hideAxis("bottom")
        plot.setBackground("#f3f4f6")
        text = pg.TextItem(label, color="#374151", anchor=(0.5, 0.5))
        plot.addItem(text)
        plot.setXRange(-1, 1, padding=0)
        plot.setYRange(-1, 1, padding=0)
        text.setPos(0, 0)

    def _fill_scatter_cell(
        self,
        plot: pg.PlotWidget,
        r: int,
        c: int,
        xi: int,
        yi: int,
        *,
        edge_left: bool,
        edge_bottom: bool,
        ch_x: str,
        ch_y: str,
        show_raw: bool,
    ) -> None:
        """Off-diagonal cell: raw + compensated scatter."""
        if not edge_left:
            plot.hideAxis("left")
        else:
            plot.getAxis("left").setLabel(ch_y, size="7pt")

        if not edge_bottom:
            plot.hideAxis("bottom")
        else:
            plot.getAxis("bottom").setLabel(ch_x, size="7pt")

        raw_item: pg.ScatterPlotItem | None = None
        comp_item: pg.ScatterPlotItem | None = None

        if self._raw_sub is not None:
            raw_item = pg.ScatterPlotItem(
                x=self._raw_sub[:, xi],
                y=self._raw_sub[:, yi],
                size=2, pen=None,
                brush=pg.mkBrush(170, 170, 170, 55),
            )
            raw_item.setVisible(show_raw)
            plot.addItem(raw_item)

        if self._comp_sub is not None:
            comp_item = pg.ScatterPlotItem(
                x=self._comp_sub[:, xi],
                y=self._comp_sub[:, yi],
                size=2, pen=None,
                brush=pg.mkBrush(37, 99, 235, 90),
            )
            plot.addItem(comp_item)

        self._raw_items[r][c] = raw_item
        self._comp_items[r][c] = comp_item

    # ── In-place compensation update ───────────────────────────────────────────

    def _recompute_comp_sub(self) -> None:
        """Recompute compensated subsampled events using the current matrix."""
        if (
            self._fluoro_indices is None
            or self._spill_matrix is None
            or self._cached_sample_idx is None
            or self._workspace is None
            or self._sel is None
        ):
            self._comp_sub = None
            return

        if self._cached_sample_idx >= len(self._workspace.samples):
            self._comp_sub = None
            return

        n = len(self._cached_channels)
        matrix = self._spill_matrix[:n, :n]
        raw = self._workspace.samples[self._cached_sample_idx].sample.events
        try:
            comp_full = apply_compensation(raw, matrix, self._fluoro_indices)
            self._comp_sub = comp_full[self._sel]
        except Exception:
            self._comp_sub = None

    def _update_scatter_data(self) -> None:
        """Update compensated scatter item data in-place (no widget rebuild)."""
        n = self._n_grid
        for r in range(n):
            for c in range(n):
                if r == c:
                    continue
                xi = self._fluoro_indices[c]
                yi = self._fluoro_indices[r]
                item = self._comp_items[r][c]
                if item is not None:
                    if self._comp_sub is not None:
                        item.setData(
                            x=self._comp_sub[:, xi],
                            y=self._comp_sub[:, yi],
                        )
                    else:
                        item.setData(x=np.array([]), y=np.array([]))


# ── Control detail / setup panel (right pane) ──────────────────────────────────

class _ControlSetupPanel(QWidget):
    """Edit metadata and population assignment for one compensation sample."""

    changed = Signal()  # emitted when user saves changes

    def __init__(self, workspace: WorkspaceState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.workspace = workspace
        self._sample_index: int | None = None
        self._build_ui()
        self.clear()

    # ── Public API ─────────────────────────────────────────────────────────────

    def load_sample(self, workspace_index: int) -> None:
        self._sample_index = workspace_index
        ws = self.workspace.samples[workspace_index]
        comp = ws.compensation
        sample = ws.sample

        # Metadata
        ct_key = comp.control_type
        ct_idx = next((i for i, (_, k) in enumerate(_CONTROL_TYPES) if k == ct_key), 0)
        self._type_combo.setCurrentIndex(ct_idx)
        self._fluoro_edit.setText(comp.fluorochrome)

        channel_names = [ch.display_name for ch in sample.channels]
        self._channel_combo.blockSignals(True)
        self._channel_combo.clear()
        self._channel_combo.addItem("— not set —", "")
        self._channel_combo.addItems(channel_names)
        if comp.target_channel and comp.target_channel in channel_names:
            self._channel_combo.setCurrentIndex(channel_names.index(comp.target_channel) + 1)
        else:
            self._channel_combo.setCurrentIndex(0)
        self._channel_combo.blockSignals(False)

        self._notes_edit.setPlainText(comp.notes)

        # Gate names for this sample
        gate_names = [g.name for g in ws.gates]
        self._pos_gate_combo.blockSignals(True)
        self._pos_gate_combo.clear()
        self._pos_gate_combo.addItem("— (all events) —", "")
        self._pos_gate_combo.addItems(gate_names)
        pos_pop = ws.compensation_positive.population_name
        if pos_pop in gate_names:
            self._pos_gate_combo.setCurrentIndex(gate_names.index(pos_pop) + 1)
        self._pos_gate_combo.blockSignals(False)

        # Negative population
        use_univ = ws.use_universal_negative
        (self._neg_universal_radio if use_univ else self._neg_local_radio).setChecked(True)
        self._refresh_neg_area(ws)

        self.setEnabled(True)
        self._save_btn.setEnabled(True)

    def clear(self) -> None:
        self._sample_index = None
        self.setEnabled(False)

    # ── Build UI ───────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setSpacing(10)
        layout.setContentsMargins(4, 4, 4, 4)

        # Metadata group
        meta_box = QGroupBox("Control details")
        meta_form_layout = QVBoxLayout(meta_box)
        meta_form_layout.setSpacing(6)

        def _row(label: str, widget: QWidget) -> QHBoxLayout:
            row = QHBoxLayout()
            lbl = QLabel(label)
            lbl.setFixedWidth(100)
            row.addWidget(lbl)
            row.addWidget(widget, stretch=1)
            return row

        self._type_combo = QComboBox()
        for label, _ in _CONTROL_TYPES:
            self._type_combo.addItem(label)
        meta_form_layout.addLayout(_row("Control type:", self._type_combo))

        self._fluoro_edit = QLineEdit()
        self._fluoro_edit.setPlaceholderText("e.g. FITC, PE, APC")
        meta_form_layout.addLayout(_row("Fluorochrome:", self._fluoro_edit))

        self._channel_combo = QComboBox()
        meta_form_layout.addLayout(_row("Target channel:", self._channel_combo))

        self._notes_edit = QTextEdit()
        self._notes_edit.setPlaceholderText("Optional notes…")
        self._notes_edit.setFixedHeight(56)
        meta_form_layout.addLayout(_row("Notes:", self._notes_edit))

        layout.addWidget(meta_box)

        # Population assignment group
        pop_box = QGroupBox("Population assignment")
        pop_layout = QVBoxLayout(pop_box)
        pop_layout.setSpacing(8)

        pos_row = QHBoxLayout()
        pos_row.addWidget(QLabel("Positive pop.:"))
        self._pos_gate_combo = QComboBox()
        self._pos_gate_combo.setMinimumWidth(160)
        pos_row.addWidget(self._pos_gate_combo, stretch=1)
        pop_layout.addLayout(pos_row)

        neg_label = QLabel("Negative source:")
        pop_layout.addWidget(neg_label)

        self._neg_local_radio = QRadioButton("Gate in this sample")
        self._neg_universal_radio = QRadioButton("Universal negative sample")
        self._neg_local_radio.setChecked(True)
        neg_grp = QButtonGroup(self)
        neg_grp.addButton(self._neg_local_radio)
        neg_grp.addButton(self._neg_universal_radio)
        self._neg_local_radio.toggled.connect(self._on_neg_mode_changed)
        pop_layout.addWidget(self._neg_local_radio)
        pop_layout.addWidget(self._neg_universal_radio)

        self._neg_local_combo = QComboBox()
        self._neg_local_combo.setMinimumWidth(160)
        self._neg_universal_sample_combo = QComboBox()
        self._neg_universal_sample_combo.setMinimumWidth(160)
        self._neg_universal_gate_combo = QComboBox()
        self._neg_universal_gate_combo.setMinimumWidth(160)
        self._neg_universal_sample_combo.currentIndexChanged.connect(
            self._on_universal_sample_changed
        )

        self._neg_local_widget = QWidget()
        nlocal_l = QHBoxLayout(self._neg_local_widget)
        nlocal_l.setContentsMargins(16, 0, 0, 0)
        nlocal_l.addWidget(QLabel("Gate:"))
        nlocal_l.addWidget(self._neg_local_combo, stretch=1)

        self._neg_universal_widget = QWidget()
        nuniv_l = QVBoxLayout(self._neg_universal_widget)
        nuniv_l.setContentsMargins(16, 0, 0, 0)
        nuniv_l.setSpacing(4)
        sample_row = QHBoxLayout()
        sample_row.addWidget(QLabel("Sample:"))
        sample_row.addWidget(self._neg_universal_sample_combo, stretch=1)
        gate_row = QHBoxLayout()
        gate_row.addWidget(QLabel("Gate:"))
        gate_row.addWidget(self._neg_universal_gate_combo, stretch=1)
        nuniv_l.addLayout(sample_row)
        nuniv_l.addLayout(gate_row)

        pop_layout.addWidget(self._neg_local_widget)
        pop_layout.addWidget(self._neg_universal_widget)
        layout.addWidget(pop_box)

        # Save button
        self._save_btn = QPushButton("Save changes")
        self._save_btn.setProperty("variant", "primary")
        self._save_btn.clicked.connect(self._on_save)
        layout.addWidget(self._save_btn)
        layout.addStretch(1)

        scroll.setWidget(inner)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # ── Negative population helpers ────────────────────────────────────────────

    def _on_neg_mode_changed(self) -> None:
        use_univ = self._neg_universal_radio.isChecked()
        self._neg_local_widget.setVisible(not use_univ)
        self._neg_universal_widget.setVisible(use_univ)
        if use_univ and self._neg_universal_sample_combo.count() == 0:
            self._populate_universal_sample_combo()

    def _refresh_neg_area(self, ws) -> None:
        use_univ = ws.use_universal_negative
        self._neg_local_widget.setVisible(not use_univ)
        self._neg_universal_widget.setVisible(use_univ)

        # Local gate combo
        gate_names = [g.name for g in ws.gates]
        self._neg_local_combo.blockSignals(True)
        self._neg_local_combo.clear()
        self._neg_local_combo.addItem("— (all events) —", "")
        self._neg_local_combo.addItems(gate_names)
        neg_pop = ws.compensation_negative.population_name
        if not use_univ and neg_pop in gate_names:
            self._neg_local_combo.setCurrentIndex(gate_names.index(neg_pop) + 1)
        self._neg_local_combo.blockSignals(False)

        if use_univ:
            self._populate_universal_sample_combo()
            # Restore saved selection
            univ_idx = ws.workspace.universal_negative_sample_index if hasattr(ws, 'workspace') else None
            neg_si = ws.compensation_negative.sample_index
            if neg_si is not None:
                for i in range(self._neg_universal_sample_combo.count()):
                    if self._neg_universal_sample_combo.itemData(i) == neg_si:
                        self._neg_universal_sample_combo.setCurrentIndex(i)
                        break
            self._on_universal_sample_changed()
            if neg_pop:
                for i in range(self._neg_universal_gate_combo.count()):
                    if self._neg_universal_gate_combo.itemText(i) == neg_pop:
                        self._neg_universal_gate_combo.setCurrentIndex(i)
                        break

    def _populate_universal_sample_combo(self) -> None:
        cur = self._neg_universal_sample_combo.currentData()
        self._neg_universal_sample_combo.blockSignals(True)
        self._neg_universal_sample_combo.clear()
        for i, ws_s in enumerate(self.workspace.samples):
            if ws_s.group_name != COMPENSATION_GROUP_NAME:
                self._neg_universal_sample_combo.addItem(ws_s.sample_name, i)
        # Restore
        if cur is not None:
            for j in range(self._neg_universal_sample_combo.count()):
                if self._neg_universal_sample_combo.itemData(j) == cur:
                    self._neg_universal_sample_combo.setCurrentIndex(j)
                    break
        self._neg_universal_sample_combo.blockSignals(False)

    def _on_universal_sample_changed(self) -> None:
        sidx = self._neg_universal_sample_combo.currentData()
        self._neg_universal_gate_combo.clear()
        if sidx is not None and sidx < len(self.workspace.samples):
            gates = self.workspace.samples[sidx].gates
            self._neg_universal_gate_combo.addItem("— (all events) —", "")
            self._neg_universal_gate_combo.addItems([g.name for g in gates])

    # ── Save ───────────────────────────────────────────────────────────────────

    def _on_save(self) -> None:
        if self._sample_index is None:
            return
        ws = self.workspace.samples[self._sample_index]

        # Metadata
        _, ct_key = _CONTROL_TYPES[self._type_combo.currentIndex()]
        ws.compensation.control_type = ct_key
        ws.compensation.fluorochrome = self._fluoro_edit.text().strip()
        ch_data = self._channel_combo.currentData()
        ws.compensation.target_channel = (
            self._channel_combo.currentText().strip() if ch_data != "" else ""
        )
        ws.compensation.notes = self._notes_edit.toPlainText().strip()

        # Positive population
        pos_gate = self._pos_gate_combo.currentData()
        if pos_gate:
            ws.compensation_positive.sample_index = self._sample_index
            ws.compensation_positive.population_name = pos_gate
        else:
            ws.compensation_positive.sample_index = None
            ws.compensation_positive.population_name = ""

        # Negative population
        use_univ = self._neg_universal_radio.isChecked()
        ws.use_universal_negative = use_univ
        if use_univ:
            univ_sample_idx = self._neg_universal_sample_combo.currentData()
            gate_name = self._neg_universal_gate_combo.currentText()
            if gate_name == "— (all events) —":
                gate_name = ""
            ws.compensation_negative.sample_index = univ_sample_idx
            ws.compensation_negative.population_name = gate_name
            self.workspace.universal_negative_sample_index = univ_sample_idx
        else:
            local_gate = self._neg_local_combo.currentData()
            if local_gate:
                ws.compensation_negative.sample_index = self._sample_index
                ws.compensation_negative.population_name = local_gate
            else:
                ws.compensation_negative.sample_index = None
                ws.compensation_negative.population_name = ""

        self.changed.emit()

    # Fix: gate data stored as gate name (not userData)
    def load_sample(self, workspace_index: int) -> None:  # noqa: F811
        self._sample_index = workspace_index
        ws = self.workspace.samples[workspace_index]
        comp = ws.compensation
        sample = ws.sample

        self._type_combo.blockSignals(True)
        ct_key = comp.control_type
        ct_idx = next((i for i, (_, k) in enumerate(_CONTROL_TYPES) if k == ct_key), 0)
        self._type_combo.setCurrentIndex(ct_idx)
        self._type_combo.blockSignals(False)

        self._fluoro_edit.setText(comp.fluorochrome)

        channel_names = [ch.display_name for ch in sample.channels]
        self._channel_combo.blockSignals(True)
        self._channel_combo.clear()
        self._channel_combo.addItem("— not set —", "")
        for cn in channel_names:
            self._channel_combo.addItem(cn, cn)
        if comp.target_channel and comp.target_channel in channel_names:
            self._channel_combo.setCurrentIndex(channel_names.index(comp.target_channel) + 1)
        else:
            self._channel_combo.setCurrentIndex(0)
        self._channel_combo.blockSignals(False)

        self._notes_edit.setPlainText(comp.notes)

        # Positive gate combo
        gate_names = [g.name for g in ws.gates]
        self._pos_gate_combo.blockSignals(True)
        self._pos_gate_combo.clear()
        self._pos_gate_combo.addItem("— (all events) —", "")
        for gn in gate_names:
            self._pos_gate_combo.addItem(gn, gn)
        pos_pop = ws.compensation_positive.population_name
        if pos_pop in gate_names:
            self._pos_gate_combo.setCurrentIndex(gate_names.index(pos_pop) + 1)
        self._pos_gate_combo.blockSignals(False)

        use_univ = ws.use_universal_negative
        if use_univ:
            self._neg_universal_radio.setChecked(True)
        else:
            self._neg_local_radio.setChecked(True)
        self._refresh_neg_area(ws)

        self.setEnabled(True)
        self._save_btn.setEnabled(True)


# ── Matrix tab ─────────────────────────────────────────────────────────────────

class _MatrixTab(QWidget):
    matrix_updated = Signal(list, np.ndarray)  # channels, matrix

    def __init__(self, workspace: WorkspaceState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.workspace = workspace
        self._channels: list[str] = []
        self._matrix: np.ndarray | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Top bar
        top = QHBoxLayout()
        top.setSpacing(6)

        top.addWidget(QLabel("Sample:"))
        self._sample_combo = QComboBox()
        self._sample_combo.setMinimumWidth(220)
        self._sample_combo.currentIndexChanged.connect(self._on_sample_changed)
        top.addWidget(self._sample_combo)

        self._load_fcs_btn = QPushButton("Load from FCS")
        self._load_fcs_btn.setToolTip("Read $SPILL / $SPILLOVER from the selected FCS file")
        self._load_fcs_btn.clicked.connect(self._on_load_from_fcs)
        top.addWidget(self._load_fcs_btn)

        self._load_ws_btn = QPushButton("Load from workspace")
        self._load_ws_btn.setToolTip("Reload the matrix saved in the workspace")
        self._load_ws_btn.clicked.connect(self._on_load_from_workspace)
        top.addWidget(self._load_ws_btn)

        top.addStretch(1)
        self._status_lbl = QLabel()
        self._status_lbl.setStyleSheet("color: #6b7280; font-size: 11px;")
        top.addWidget(self._status_lbl)

        layout.addLayout(top)

        # Table
        self._table = _MatrixTable()
        self._table.matrix_changed.connect(self._on_matrix_edited)
        layout.addWidget(self._table, stretch=1)

        # Legend
        note = QLabel(
            "Rows = detector · Columns = fluorochrome.  "
            "Diagonal (green) = 100 %, read-only.  Off-diagonal = spillover %."
        )
        note.setStyleSheet("color: #6b7280; font-size: 11px;")
        note.setWordWrap(True)
        layout.addWidget(note)

        # Apply button
        apply_btn = QPushButton("Apply to workspace")
        apply_btn.setProperty("variant", "primary")
        apply_btn.setToolTip("Save this matrix so it is used for statistics and exports")
        apply_btn.clicked.connect(self._on_apply)
        clear_btn = QPushButton("Clear workspace matrix")
        clear_btn.setProperty("variant", "danger")
        clear_btn.clicked.connect(self._on_clear)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        btn_row.addWidget(apply_btn)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

    def refresh(self) -> None:
        cur = self._sample_combo.currentData()
        self._sample_combo.blockSignals(True)
        self._sample_combo.clear()
        if self.workspace:
            for i, ws in enumerate(self.workspace.samples):
                self._sample_combo.addItem(ws.sample_name, i)
        # Restore selection
        if cur is not None:
            for j in range(self._sample_combo.count()):
                if self._sample_combo.itemData(j) == cur:
                    self._sample_combo.setCurrentIndex(j)
                    break
        self._sample_combo.blockSignals(False)
        if self._matrix is None and self.workspace.has_spillover:
            self._load_from_workspace_data()

    def _on_sample_changed(self) -> None:
        pass  # user must click Load from FCS explicitly

    def _on_load_from_fcs(self) -> None:
        idx = self._sample_combo.currentData()
        if idx is None or idx >= len(self.workspace.samples):
            self._status_lbl.setText("No sample selected.")
            return
        sample = self.workspace.samples[idx].sample
        result = extract_spillover(sample.metadata)
        if result is None:
            self._status_lbl.setText(f"No $SPILL found in {sample.file_name}.")
            return
        channels, matrix = result
        self._set_matrix(channels, matrix, source=f"FCS ({sample.file_name})")

    def _on_load_from_workspace(self) -> None:
        if not self.workspace.has_spillover:
            self._status_lbl.setText("No matrix saved in workspace yet.")
            return
        self._load_from_workspace_data()

    def _load_from_workspace_data(self) -> None:
        n = len(self.workspace.spillover_channels)
        matrix = flat_to_matrix(self.workspace.spillover_values, n)
        self._set_matrix(self.workspace.spillover_channels, matrix, source="workspace")

    def _set_matrix(self, channels: list[str], matrix: np.ndarray, source: str = "") -> None:
        self._channels = channels
        self._matrix = matrix.copy()
        self._table.load(channels, matrix)
        self._status_lbl.setText(
            f"{len(channels)}×{len(channels)} matrix" + (f" — from {source}" if source else "")
        )
        self.matrix_updated.emit(channels, matrix)

    def _on_matrix_edited(self) -> None:
        result = self._table.current_matrix()
        if result is None:
            return
        channels, matrix = result
        self._channels = channels
        self._matrix = matrix
        self.matrix_updated.emit(channels, matrix)

    def _on_apply(self) -> None:
        result = self._table.current_matrix()
        if result is None:
            QMessageBox.warning(self, "No matrix", "Load or define a spillover matrix first.")
            return
        channels, matrix = result
        self.workspace.set_spillover(channels, matrix_to_flat(matrix))
        self._status_lbl.setText(f"Matrix saved to workspace ({len(channels)}×{len(channels)}).")

    def _on_clear(self) -> None:
        self.workspace.clear_spillover()
        self._status_lbl.setText("Workspace matrix cleared.")

    def current_spillover(self) -> tuple[list[str], np.ndarray] | None:
        if self._matrix is None or not self._channels:
            return None
        return self._channels, self._matrix


# ── Add-from-workspace dialog ──────────────────────────────────────────────────

class _AddFromWorkspaceDialog(QDialog):
    """Pick existing workspace samples to move into the Compensation group."""

    def __init__(self, workspace: WorkspaceState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.workspace = workspace
        self.setWindowTitle("Add existing samples to Compensation")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Select samples to add to the Compensation group:"))

        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        for i, ws in enumerate(workspace.samples):
            if ws.group_name == COMPENSATION_GROUP_NAME:
                continue
            item = QListWidgetItem(f"{ws.sample_name}  [{ws.group_name}]")
            item.setData(Qt.UserRole, i)
            self._list.addItem(item)
        layout.addWidget(self._list, stretch=1)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def selected_indices(self) -> list[int]:
        return [item.data(Qt.UserRole) for item in self._list.selectedItems()]


# ── Main compensation window ───────────────────────────────────────────────────

class CompensationWindow(QDialog):
    """Comprehensive compensation manager window."""

    add_fcs_to_group_requested = Signal(str)   # group_name
    workspace_changed = Signal()

    def __init__(
        self,
        workspace: WorkspaceState,
        on_workspace_changed: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.workspace = workspace
        self._on_workspace_changed = on_workspace_changed

        self.setWindowTitle("Compensation Manager")
        self.setMinimumSize(1100, 680)
        self.resize(1360, 780)
        self.setWindowFlags(
            Qt.Window
            | Qt.WindowCloseButtonHint
            | Qt.WindowMinimizeButtonHint
            | Qt.WindowMaximizeButtonHint
        )

        self._build_ui()
        self._refresh_controls_table()

    # ── Build UI ───────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 10)
        root.setSpacing(8)

        # ── Action bar ──────────────────────────────────────────────────────
        bar = QHBoxLayout()
        bar.setSpacing(5)

        self._add_ws_btn = QPushButton("+ From workspace")
        self._add_ws_btn.setToolTip("Move existing workspace samples into the Compensation group")
        self._add_ws_btn.clicked.connect(self._on_add_from_workspace)

        self._import_btn = QPushButton("+ Import FCS…")
        self._import_btn.setProperty("variant", "primary")
        self._import_btn.setToolTip("Import new FCS files directly into the Compensation group")
        self._import_btn.clicked.connect(self._on_import_fcs)

        self._remove_btn = QPushButton("Remove selected")
        self._remove_btn.setProperty("variant", "danger")
        self._remove_btn.setToolTip("Move the selected control back to the Ungrouped group")
        self._remove_btn.clicked.connect(self._on_remove_selected)
        self._remove_btn.setEnabled(False)

        self._status_lbl = QLabel()
        self._status_lbl.setStyleSheet("color: #6b7280; font-size: 11px;")

        bar.addWidget(self._add_ws_btn)
        bar.addWidget(self._import_btn)
        bar.addWidget(_vline())
        bar.addWidget(self._remove_btn)
        bar.addStretch(1)
        bar.addWidget(self._status_lbl)

        root.addLayout(bar)

        # ── Main splitter: controls table | right panels ─────────────────────
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        # Left: controls table
        left = QGroupBox("Controls")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(8, 12, 8, 8)

        self._ctrl_table = QTableWidget(0, 7)
        self._ctrl_table.setHorizontalHeaderLabels(
            ["Name", "Type", "Fluorochrome", "Channel", "Positive", "Negative", "✓"]
        )
        self._ctrl_table.verticalHeader().setVisible(False)
        self._ctrl_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._ctrl_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._ctrl_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._ctrl_table.horizontalHeader().setStretchLastSection(True)
        self._ctrl_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._ctrl_table.itemSelectionChanged.connect(self._on_ctrl_table_selection_changed)
        left_layout.addWidget(self._ctrl_table, stretch=1)

        splitter.addWidget(left)

        # Right: tab widget
        self._tabs = QTabWidget()

        # Tab 1: Setup
        self._setup_panel = _ControlSetupPanel(self.workspace)
        self._setup_panel.changed.connect(self._on_setup_saved)
        self._tabs.addTab(self._setup_panel, "Control setup")

        # Tab 2: Matrix
        self._matrix_tab = _MatrixTab(self.workspace)
        self._matrix_tab.matrix_updated.connect(self._on_matrix_updated)
        self._tabs.addTab(self._matrix_tab, "Spillover matrix")

        # Tab 3: Pairwise scatter grid
        self._scatter = _PairScatterGrid()
        self._scatter.set_workspace(self.workspace)
        self._tabs.addTab(self._scatter, "Pairwise scatter")

        splitter.addWidget(self._tabs)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([440, 700])

        root.addWidget(splitter, stretch=1)

        # Bottom close button
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #d4dde7;")
        root.addWidget(sep)

        bottom = QHBoxLayout()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        bottom.addStretch(1)
        bottom.addWidget(close_btn)
        root.addLayout(bottom)

    # ── Controls table ─────────────────────────────────────────────────────────

    def _refresh_controls_table(self) -> None:
        comp_samples = self.workspace.compensation_samples()
        self._ctrl_table.setRowCount(len(comp_samples))

        configured = 0
        for row, (ws_idx, ws) in enumerate(comp_samples):
            comp = ws.compensation
            has_pos = ws.compensation_positive.is_configured
            has_neg = bool(ws.compensation_negative.population_name)
            ok = has_pos and has_neg
            if ok:
                configured += 1

            def _cell(text: str, *, color: str | None = None) -> QTableWidgetItem:
                item = QTableWidgetItem(text)
                item.setData(Qt.UserRole, ws_idx)
                if color:
                    item.setForeground(QColor(color))
                return item

            self._ctrl_table.setItem(row, 0, _cell(ws.sample_name))
            self._ctrl_table.setItem(row, 1, _cell(comp.control_type.replace("_", " ").title()))
            self._ctrl_table.setItem(row, 2, _cell(comp.fluorochrome or "—"))
            self._ctrl_table.setItem(row, 3, _cell(comp.target_channel or "—"))
            self._ctrl_table.setItem(row, 4, _cell(
                ws.compensation_positive.population_name or "—",
                color="#166534" if has_pos else "#9aaabb",
            ))
            neg_pop = ws.compensation_negative.population_name
            self._ctrl_table.setItem(row, 5, _cell(
                neg_pop or "—",
                color="#166534" if has_neg else "#9aaabb",
            ))
            self._ctrl_table.setItem(row, 6, _cell("✓" if ok else "…", color="#166534" if ok else "#c2410c"))

        total = len(comp_samples)
        self._status_lbl.setText(
            f"{configured}/{total} controls fully configured."
            if total else "No compensation controls added yet."
        )
        self._matrix_tab.refresh()

    def _on_ctrl_table_selection_changed(self) -> None:
        rows = self._ctrl_table.selectedItems()
        if not rows:
            self._setup_panel.clear()
            self._remove_btn.setEnabled(False)
            return
        ws_idx = rows[0].data(Qt.UserRole)
        self._remove_btn.setEnabled(True)
        self._setup_panel.load_sample(ws_idx)

    def _selected_workspace_index(self) -> int | None:
        rows = self._ctrl_table.selectedItems()
        if not rows:
            return None
        return rows[0].data(Qt.UserRole)

    # ── Add / remove ───────────────────────────────────────────────────────────

    def _on_add_from_workspace(self) -> None:
        dlg = _AddFromWorkspaceDialog(self.workspace, self)
        if dlg.exec() != QDialog.Accepted:
            return
        indices = dlg.selected_indices()
        if not indices:
            return
        for idx in indices:
            self.workspace.samples[idx].group_name = COMPENSATION_GROUP_NAME
        self._refresh_controls_table()
        self._emit_changed()

    def _on_import_fcs(self) -> None:
        self.add_fcs_to_group_requested.emit(COMPENSATION_GROUP_NAME)

    def _on_remove_selected(self) -> None:
        ws_idx = self._selected_workspace_index()
        if ws_idx is None:
            return
        ws = self.workspace.samples[ws_idx]
        ws.group_name = DEFAULT_GROUP_NAME
        # Clear compensation metadata
        ws.compensation = CompensationSampleMetadata()
        ws.compensation_positive.sample_index = None
        ws.compensation_positive.population_name = ""
        ws.compensation_negative.sample_index = None
        ws.compensation_negative.population_name = ""
        ws.use_universal_negative = False
        self._setup_panel.clear()
        self._refresh_controls_table()
        self._emit_changed()

    # ── Callbacks from child widgets ───────────────────────────────────────────

    def _on_setup_saved(self) -> None:
        self._refresh_controls_table()
        self._emit_changed()

    def _on_matrix_updated(self, channels: list[str], matrix: np.ndarray) -> None:
        self._scatter.update_spillover(channels, matrix)

    def _emit_changed(self) -> None:
        if self._on_workspace_changed:
            self._on_workspace_changed()
        self.workspace_changed.emit()

    # ── Public refresh (called by main window when workspace changes) ───────────

    def refresh(self) -> None:
        self._refresh_controls_table()
        self._scatter.set_workspace(self.workspace)
