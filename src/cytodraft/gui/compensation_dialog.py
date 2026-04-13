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


def _find_channel_idx(sample, channel_name: str) -> int | None:
    """Return the column index in sample.events for a channel, matched by display
    name, PNS (fluorochrome label) or PNN (detector name), case-insensitive."""
    lo = channel_name.strip().lower()
    for ch in sample.channels:
        for label in (ch.display_name, ch.pns, ch.pnn):
            if label.strip().lower() == lo:
                return ch.index
    return None


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
                if r == c:
                    item = QTableWidgetItem("—")
                    item.setTextAlignment(Qt.AlignCenter)
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    item.setBackground(_DIAG_BG)
                    item.setForeground(QColor("#9ca3af"))
                else:
                    item = QTableWidgetItem(f"{matrix[r, c]:.4f}")
                    item.setTextAlignment(Qt.AlignCenter)
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
                    txt = item.text() if item else ""
                    if r == c or txt == "—":
                        values.append(1.0 if r == c else 0.0)
                    else:
                        values.append(float(txt))
                except ValueError:
                    values.append(1.0 if r == c else 0.0)
        return headers, flat_to_matrix(values, n)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if item.row() == item.column():
            return
        try:
            val = float(item.text())
        except ValueError:
            val = 0.0
            item.setText("0.0000")
        val = max(-2.0, min(2.0, val))
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

        # Grid state: keyed by (ch_x_list_index, ch_y_list_index)
        self._n_grid: int = 0
        self._scatter_items: dict[
            tuple[int, int],
            tuple[pg.ScatterPlotItem | None, pg.ScatterPlotItem | None],
        ] = {}

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
        for raw_item, _ in self._scatter_items.values():
            if raw_item is not None:
                raw_item.setVisible(checked)

    # ── Grid build ─────────────────────────────────────────────────────────────

    def _clear_grid(self) -> None:
        while self._grid_layout.count():
            child = self._grid_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self._scatter_items = {}
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
        self._scatter_items = {}

        # Lower-triangle layout: (N-1)×(N-1) grid.
        # grid_col c  → X axis = channels[c]
        # grid_row r  → Y axis = channels[r+1]
        # Show cell only when c <= r  (X-channel index < Y-channel index)
        grid_n = n - 1
        if grid_n < 1:
            self._info_lbl.setText("Need at least 2 channels to show scatter plots.")
            return

        # Cell size scales with grid size
        cell_size = max(100, min(220, 700 // grid_n))
        show_raw = self._raw_check.isChecked()

        for grid_r in range(grid_n):
            for grid_c in range(grid_n):
                if grid_c > grid_r:
                    # Upper triangle: empty placeholder keeps grid alignment
                    ph = QWidget()
                    ph.setFixedSize(cell_size, cell_size)
                    self._grid_layout.addWidget(ph, grid_r, grid_c)
                    continue

                ch_x_idx = grid_c        # index into channels / indices
                ch_y_idx = grid_r + 1    # index into channels / indices
                xi = indices[ch_x_idx]
                yi = indices[ch_y_idx]

                plot = self._make_cell_plot(cell_size)
                raw_item, comp_item = self._fill_scatter_cell(
                    plot, xi, yi,
                    edge_left=(grid_c == 0),
                    edge_bottom=(grid_r == grid_n - 1),
                    ch_x=channels[ch_x_idx],
                    ch_y=channels[ch_y_idx],
                    show_raw=show_raw,
                )
                self._scatter_items[(ch_x_idx, ch_y_idx)] = (raw_item, comp_item)
                self._grid_layout.addWidget(plot, grid_r, grid_c)

        pairs = n * (n - 1) // 2
        suffix = ""
        if len(self._spill_channels) > n:
            suffix = f" (first {n} of {len(self._spill_channels)} channels shown)"
        self._info_lbl.setText(
            f"{pairs} scatter plots · {len(self._sel):,} events per plot{suffix}"
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
        xi: int,
        yi: int,
        *,
        edge_left: bool,
        edge_bottom: bool,
        ch_x: str,
        ch_y: str,
        show_raw: bool,
    ) -> tuple[pg.ScatterPlotItem | None, pg.ScatterPlotItem | None]:
        """Fill an off-diagonal scatter cell; return (raw_item, comp_item)."""
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

        return raw_item, comp_item

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
        for (ch_x_idx, ch_y_idx), (_, comp_item) in self._scatter_items.items():
            if comp_item is None:
                continue
            xi = self._fluoro_indices[ch_x_idx]
            yi = self._fluoro_indices[ch_y_idx]
            if self._comp_sub is not None:
                comp_item.setData(x=self._comp_sub[:, xi], y=self._comp_sub[:, yi])
            else:
                comp_item.setData(x=np.array([]), y=np.array([]))


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
    """Unified matrix + scatter pane.

    Layout
    ------
    Top toolbar:
        [Compute from controls]  [Load from FCS $SPILL]
        Saved matrices: [combo] [Load] [Delete] [Save current as…] [Export CSV]
        [Apply to data]   status label

    Body (horizontal splitter):
        Left  — spillover matrix table + legend
        Right — pairwise scatter grid (_PairScatterGrid)

    Live updates
    ------------
    Editing the matrix immediately refreshes the scatter preview but does NOT
    change the active compensation applied to the data.  Click "Apply to data"
    to commit the change; this emits ``matrix_updated`` which the
    CompensationWindow relays to the main window to trigger recomputation.
    """

    # Emitted ONLY when "Apply to data" is clicked (not on every keystroke).
    matrix_updated = Signal(list, np.ndarray)  # channels, matrix (applied)

    def __init__(self, workspace: WorkspaceState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.workspace = workspace
        self._channels: list[str] = []
        self._matrix: np.ndarray | None = None
        self._applied = False          # True when editor matrix == active workspace matrix
        self._build_ui()

    # ── Build UI ───────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        # ── Toolbar row 1: compute + load ────────────────────────────────────
        row1 = QHBoxLayout()
        row1.setSpacing(5)

        self._compute_btn = QPushButton("Compute from controls")
        self._compute_btn.setProperty("variant", "primary")
        self._compute_btn.setToolTip(
            "Calculate the spillover matrix from the configured single-stain controls\n"
            "using the median-positive / median-negative method.\n"
            "Result is saved automatically and applied to the data."
        )
        self._compute_btn.clicked.connect(self._on_compute_from_controls)
        row1.addWidget(self._compute_btn)

        row1.addWidget(_vline())

        load_lbl = QLabel("Load:")
        load_lbl.setStyleSheet("color: #6b7280;")
        row1.addWidget(load_lbl)

        self._sample_combo = QComboBox()
        self._sample_combo.setMinimumWidth(180)
        self._sample_combo.setToolTip("Sample to read $SPILL from")
        row1.addWidget(self._sample_combo)

        self._load_fcs_btn = QPushButton("From FCS $SPILL")
        self._load_fcs_btn.setToolTip("Read the $SPILL / $SPILLOVER keyword from the selected FCS")
        self._load_fcs_btn.clicked.connect(self._on_load_from_fcs)
        row1.addWidget(self._load_fcs_btn)

        row1.addStretch(1)
        root.addLayout(row1)

        # ── Toolbar row 2: saved matrix manager + apply ──────────────────────
        row2 = QHBoxLayout()
        row2.setSpacing(5)

        saved_lbl = QLabel("Saved:")
        saved_lbl.setStyleSheet("color: #6b7280;")
        row2.addWidget(saved_lbl)

        self._saved_combo = QComboBox()
        self._saved_combo.setMinimumWidth(220)
        self._saved_combo.setToolTip("Named matrix snapshots — load to compare / roll back")
        row2.addWidget(self._saved_combo)

        self._load_saved_btn = QPushButton("Load")
        self._load_saved_btn.setToolTip("Load selected matrix into the editor (preview only)")
        self._load_saved_btn.clicked.connect(self._on_load_saved)
        row2.addWidget(self._load_saved_btn)

        self._delete_saved_btn = QPushButton("Delete")
        self._delete_saved_btn.setProperty("variant", "danger")
        self._delete_saved_btn.setToolTip("Remove selected matrix from the saved list")
        self._delete_saved_btn.clicked.connect(self._on_delete_saved)
        row2.addWidget(self._delete_saved_btn)

        self._save_as_btn = QPushButton("Save current as…")
        self._save_as_btn.setToolTip("Save the matrix currently in the editor with a name")
        self._save_as_btn.clicked.connect(self._on_save_as)
        row2.addWidget(self._save_as_btn)

        self._export_btn = QPushButton("Export CSV")
        self._export_btn.setToolTip("Export the current editor matrix to a CSV file")
        self._export_btn.clicked.connect(self._on_export_csv)
        row2.addWidget(self._export_btn)

        row2.addWidget(_vline())

        self._apply_btn = QPushButton("Apply to data")
        self._apply_btn.setProperty("variant", "primary")
        self._apply_btn.setToolTip(
            "Apply the current matrix to all samples — updates gating, statistics and plots"
        )
        self._apply_btn.clicked.connect(self._on_apply)
        row2.addWidget(self._apply_btn)

        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setProperty("variant", "danger")
        self._clear_btn.setToolTip("Remove the active compensation matrix from the workspace")
        self._clear_btn.clicked.connect(self._on_clear)
        row2.addWidget(self._clear_btn)

        row2.addStretch(1)
        self._status_lbl = QLabel("No matrix loaded.")
        self._status_lbl.setStyleSheet("color: #6b7280; font-size: 11px;")
        row2.addWidget(self._status_lbl)

        root.addLayout(row2)

        # ── Body: matrix table (left) + scatter grid (right) ─────────────────
        body = QSplitter(Qt.Horizontal)
        body.setChildrenCollapsible(False)

        # Left: matrix table
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)

        self._table = _MatrixTable()
        self._table.matrix_changed.connect(self._on_matrix_edited)
        left_layout.addWidget(self._table, stretch=1)

        note = QLabel(
            "Rows = detector · Columns = fluorochrome.  "
            "Diagonal = read-only (—).  Off-diagonal = spillover fraction (0–1)."
        )
        note.setStyleSheet("color: #6b7280; font-size: 11px;")
        note.setWordWrap(True)
        left_layout.addWidget(note)
        body.addWidget(left)

        # Right: pairwise scatter grid (preview updates live)
        self._scatter = _PairScatterGrid()
        self._scatter.set_workspace(self.workspace)
        body.addWidget(self._scatter)

        body.setSizes([380, 700])
        root.addWidget(body, stretch=1)

        self._refresh_saved_combo()

    # ── Saved-matrix combo ─────────────────────────────────────────────────────

    def _refresh_saved_combo(self) -> None:
        prev = self._saved_combo.currentText()
        self._saved_combo.blockSignals(True)
        self._saved_combo.clear()
        for m in self.workspace.saved_spillover_matrices:
            label = m.name + (f"  [{m.created_at}]" if m.created_at else "")
            self._saved_combo.addItem(label, m.name)
        # Restore previous selection if still present
        for j in range(self._saved_combo.count()):
            if self._saved_combo.itemText(j).startswith(prev.split("  [")[0]):
                self._saved_combo.setCurrentIndex(j)
                break
        self._saved_combo.blockSignals(False)
        has = self._saved_combo.count() > 0
        self._load_saved_btn.setEnabled(has)
        self._delete_saved_btn.setEnabled(has)

    # ── Public API ─────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Called when workspace changes (samples added/removed, workspace loaded)."""
        cur = self._sample_combo.currentData()
        self._sample_combo.blockSignals(True)
        self._sample_combo.clear()
        for i, ws in enumerate(self.workspace.samples):
            self._sample_combo.addItem(ws.sample_name, i)
        if cur is not None:
            for j in range(self._sample_combo.count()):
                if self._sample_combo.itemData(j) == cur:
                    self._sample_combo.setCurrentIndex(j)
                    break
        self._sample_combo.blockSignals(False)

        self._refresh_saved_combo()
        self._scatter.set_workspace(self.workspace)

        # Auto-load active workspace matrix on first open
        if self._matrix is None and self.workspace.has_spillover:
            self._load_from_workspace_data()

    # ── Load actions ───────────────────────────────────────────────────────────

    def _on_load_from_fcs(self) -> None:
        idx = self._sample_combo.currentData()
        if idx is None or idx >= len(self.workspace.samples):
            self._set_status("No sample selected.", error=True)
            return
        sample = self.workspace.samples[idx].sample
        result = extract_spillover(sample.metadata)
        if result is None:
            self._set_status(f"No $SPILL keyword in {sample.file_name}.", error=True)
            return
        channels, matrix = result
        self._preview_matrix(channels, matrix, label=f"from FCS ({sample.file_name})")

    def _load_from_workspace_data(self) -> None:
        n = len(self.workspace.spillover_channels)
        matrix = flat_to_matrix(self.workspace.spillover_values, n)
        self._preview_matrix(self.workspace.spillover_channels, matrix, label="from workspace")
        self._applied = True
        self._refresh_status()

    def _on_load_saved(self) -> None:
        name = self._saved_combo.currentData()
        if name is None:
            return
        for m in self.workspace.saved_spillover_matrices:
            if m.name == name:
                matrix = flat_to_matrix(m.values, len(m.channels))
                self._preview_matrix(m.channels, matrix, label=f"loaded '{name}' (preview)")
                return

    def _on_delete_saved(self) -> None:
        name = self._saved_combo.currentData()
        if name is None:
            return
        self.workspace.delete_spillover_matrix(name)
        self._refresh_saved_combo()

    # ── Save / export ──────────────────────────────────────────────────────────

    def _on_save_as(self) -> None:
        from PySide6.QtWidgets import QInputDialog
        if self._matrix is None:
            self._set_status("No matrix to save.", error=True)
            return
        name, ok = QInputDialog.getText(self, "Save matrix", "Name for this matrix:")
        if not ok or not name.strip():
            return
        name = name.strip()
        from datetime import datetime as _dt
        ts = _dt.now().strftime("%Y-%m-%d %H:%M")
        self.workspace.save_spillover_matrix(name, self._channels, matrix_to_flat(self._matrix), ts)
        self._refresh_saved_combo()
        # Select the just-saved entry
        for j in range(self._saved_combo.count()):
            if self._saved_combo.itemData(j) == name:
                self._saved_combo.setCurrentIndex(j)
                break
        self._set_status(f"Saved as '{name}'.")

    def _on_export_csv(self) -> None:
        from PySide6.QtWidgets import QFileDialog
        if self._matrix is None:
            self._set_status("No matrix to export.", error=True)
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export spillover matrix", "spillover_matrix.csv", "CSV files (*.csv)"
        )
        if not path:
            return
        import csv
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([""] + self._channels)
            n = len(self._channels)
            for r in range(n):
                row = [self._channels[r]]
                for c in range(n):
                    row.append("—" if r == c else f"{self._matrix[r, c]:.6f}")
                writer.writerow(row)
        self._set_status(f"Exported to {path}")

    # ── Apply / clear ──────────────────────────────────────────────────────────

    def _on_apply(self) -> None:
        result = self._table.current_matrix()
        if result is None:
            self._set_status("No matrix to apply.", error=True)
            return
        channels, matrix = result
        self._channels = channels
        self._matrix = matrix.copy()
        self.workspace.set_spillover(channels, matrix_to_flat(matrix))
        self._applied = True
        self._refresh_status()
        self.matrix_updated.emit(channels, matrix)

    def _on_clear(self) -> None:
        self.workspace.clear_spillover()
        self._applied = False
        self._scatter.clear_spillover()
        self._set_status("Compensation cleared from workspace.")
        self.matrix_updated.emit([], np.zeros((0, 0)))

    # ── Matrix editor callbacks ────────────────────────────────────────────────

    def _preview_matrix(self, channels: list[str], matrix: np.ndarray, label: str = "") -> None:
        """Load matrix into editor and refresh scatter preview (no data recompute)."""
        self._channels = list(channels)
        self._matrix = matrix.copy()
        self._table.load(channels, matrix)
        self._applied = False
        self._set_status(f"Preview: {label}" if label else "Preview")
        self._scatter.update_spillover(channels, matrix)

    def _on_matrix_edited(self) -> None:
        """Live preview: refresh scatter without recomputing data."""
        result = self._table.current_matrix()
        if result is None:
            return
        channels, matrix = result
        self._channels = channels
        self._matrix = matrix
        self._applied = False
        self._refresh_status()
        self._scatter.update_spillover(channels, matrix)

    # ── Compute from controls ──────────────────────────────────────────────────

    def _on_compute_from_controls(self) -> None:
        """Compute the spillover matrix from configured single-stain controls.

        Algorithm (per column c, single-stain control for fluorochrome c):
            spillover[r, c] = (median(pos[:, r]) - median(neg[:, r]))
                             / (median(pos[:, c]) - median(neg[:, c]))

        The result is auto-saved with a timestamp and immediately applied.
        """
        comp_samples = self.workspace.compensation_samples()
        configured = [
            (ws_idx, ws)
            for ws_idx, ws in comp_samples
            if ws.compensation.control_type == "single_stain"
            and ws.compensation.target_channel
            and ws.compensation_positive.is_configured
        ]

        if len(configured) < 2:
            QMessageBox.warning(
                self, "Not enough controls",
                "Need at least 2 fully configured single-stain controls.\n\n"
                "For each control, in the Control setup tab, set:\n"
                "  • Control type = Single stain\n"
                "  • Target channel (e.g. GFP-A)\n"
                "  • Positive population gate\n"
                "Then click Save changes.",
            )
            return

        # Build ordered channel list (first-occurrence order)
        channels: list[str] = []
        ch_set: set[str] = set()
        for _, ws in configured:
            ch = ws.compensation.target_channel
            if ch not in ch_set:
                channels.append(ch)
                ch_set.add(ch)

        n = len(channels)
        ch_to_col = {ch: i for i, ch in enumerate(channels)}
        matrix = np.eye(n, dtype=float)
        errors: list[str] = []

        for _ws_idx, ws in configured:
            col = ch_to_col[ws.compensation.target_channel]
            sample = ws.sample

            ch_indices: list[int | None] = [_find_channel_idx(sample, ch) for ch in channels]
            if None in ch_indices:
                missing = [ch for ch, idx in zip(channels, ch_indices) if idx is None]
                errors.append(f"• {ws.sample_name}: channels not found: {missing}")
                continue

            # Positive mask
            pos_mask: np.ndarray | None = None
            for gate in ws.gates:
                if gate.name == ws.compensation_positive.population_name:
                    pos_mask = gate.full_mask
                    break
            if pos_mask is None:
                pos_mask = np.ones(sample.event_count, dtype=bool)

            # Negative mask
            neg_sample = sample
            neg_ch_indices: list[int | None] = list(ch_indices)
            neg_mask: np.ndarray | None = None

            if ws.use_universal_negative and ws.compensation_negative.sample_index is not None:
                neg_si = ws.compensation_negative.sample_index
                if neg_si < len(self.workspace.samples):
                    neg_ws = self.workspace.samples[neg_si]
                    neg_sample = neg_ws.sample
                    neg_ch_indices = [_find_channel_idx(neg_sample, ch) for ch in channels]
                    for gate in neg_ws.gates:
                        if gate.name == ws.compensation_negative.population_name:
                            neg_mask = gate.full_mask
                            break
                    if neg_mask is None:
                        neg_mask = np.ones(neg_sample.event_count, dtype=bool)
            else:
                for gate in ws.gates:
                    if gate.name == ws.compensation_negative.population_name:
                        neg_mask = gate.full_mask
                        break
                if neg_mask is None:
                    neg_mask = ~pos_mask  # fallback: non-positive events

            pos_events = sample.effective_events[pos_mask]
            neg_events = neg_sample.effective_events[neg_mask]

            if pos_events.shape[0] == 0:
                errors.append(f"• {ws.sample_name}: positive population is empty.")
                continue

            src_idx = ch_indices[col]
            neg_src_idx = neg_ch_indices[col] if neg_ch_indices[col] is not None else src_idx
            pos_src = float(np.median(pos_events[:, src_idx]))
            neg_src = (
                float(np.median(neg_events[:, neg_src_idx]))
                if neg_events.shape[0] > 0 and neg_src_idx is not None else 0.0
            )
            denom = pos_src - neg_src

            if denom <= 0:
                errors.append(
                    f"• {ws.sample_name} ({channels[col]}): "
                    "positive ≤ negative — skipping this column."
                )
                continue

            for row in range(n):
                if row == col:
                    continue
                r_idx = ch_indices[row]
                neg_r_idx = neg_ch_indices[row] if neg_ch_indices[row] is not None else r_idx
                pos_r = float(np.median(pos_events[:, r_idx]))
                neg_r = (
                    float(np.median(neg_events[:, neg_r_idx]))
                    if neg_events.shape[0] > 0 and neg_r_idx is not None else 0.0
                )
                matrix[row, col] = (pos_r - neg_r) / denom

        if errors:
            QMessageBox.warning(
                self, "Computation warnings",
                "Matrix computed with issues:\n\n" + "\n".join(errors),
            )

        if n == 0:
            return

        # Auto-save the computed matrix with a timestamp
        from datetime import datetime as _dt
        ts = _dt.now().strftime("%Y-%m-%d %H:%M")
        save_name = f"Auto {ts}"
        self.workspace.save_spillover_matrix(save_name, channels, matrix_to_flat(matrix), ts)
        self._refresh_saved_combo()
        for j in range(self._saved_combo.count()):
            if self._saved_combo.itemData(j) == save_name:
                self._saved_combo.setCurrentIndex(j)
                break

        # Load into editor, apply to data
        self._table.load(channels, matrix)
        self._channels = list(channels)
        self._matrix = matrix.copy()
        self.workspace.set_spillover(channels, matrix_to_flat(matrix))
        self._applied = True
        self._refresh_status()
        self._scatter.update_spillover(channels, matrix)
        self.matrix_updated.emit(channels, matrix)

    # ── Status helpers ─────────────────────────────────────────────────────────

    def _set_status(self, msg: str, *, error: bool = False) -> None:
        color = "#dc2626" if error else "#6b7280"
        self._status_lbl.setStyleSheet(f"color: {color}; font-size: 11px;")
        self._status_lbl.setText(msg)

    def _refresh_status(self) -> None:
        if self._matrix is None:
            self._set_status("No matrix loaded.")
            return
        n = len(self._channels)
        if self._applied:
            self._set_status(f"Applied ✓  ({n}×{n})")
            self._status_lbl.setStyleSheet("color: #166534; font-size: 11px; font-weight: bold;")
        else:
            self._set_status(
                f"Preview — click 'Apply to data' to use for gating and statistics  ({n}×{n})"
            )
            self._status_lbl.setStyleSheet("color: #b45309; font-size: 11px;")

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

        # Tab 2: Matrix + pairwise scatter (unified view)
        self._matrix_tab = _MatrixTab(self.workspace)
        self._matrix_tab.matrix_updated.connect(self._on_matrix_updated)
        self._tabs.addTab(self._matrix_tab, "Spillover matrix & scatter")

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
        # matrix_updated is only emitted when "Apply to data" is clicked,
        # so always propagate to the main window to recompute compensation.
        self._emit_changed()

    def _emit_changed(self) -> None:
        if self._on_workspace_changed:
            self._on_workspace_changed()
        self.workspace_changed.emit()

    # ── Public refresh (called by main window when workspace changes) ───────────

    def refresh(self) -> None:
        self._refresh_controls_table()
