from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QWidget,
)

# Stylesheets applied when buttons are active vs inactive
_BTN_BASE = (
    "QPushButton {"
    "  border-radius: 8px;"
    "  padding: 7px 16px;"
    "  font-weight: 600;"
    "  font-size: 13px;"
    "  min-height: 32px;"
    "}"
)

_DRAW_DEFAULT = _BTN_BASE + (
    "QPushButton { background: #f4f7fb; color: #314255; border: 1px solid #d4dde7; }"
    "QPushButton:hover { background: #e9eff6; }"
    "QPushButton:pressed { background: #dce4ee; }"
)

_APPLY_INACTIVE = _BTN_BASE + (
    "QPushButton { background: #eef2f6; color: #97a4b2; border: 1px solid #d4dde7; }"
)

_APPLY_ACTIVE = _BTN_BASE + (
    "QPushButton { background: #2b6ef3; color: #ffffff; border: 1px solid #1f5fe0; }"
    "QPushButton:hover { background: #1f5fe0; }"
    "QPushButton:pressed { background: #194eb8; }"
)

_CLEAR_INACTIVE = _BTN_BASE + (
    "QPushButton { background: #eef2f6; color: #97a4b2; border: 1px solid #d4dde7; }"
)

_CLEAR_ACTIVE = _BTN_BASE + (
    "QPushButton { background: #fff2f3; color: #b42318; border: 1px solid #f5c2c7; }"
    "QPushButton:hover { background: #ffe7ea; }"
    "QPushButton:pressed { background: #ffd5db; }"
)


class GateToolbar(QWidget):
    """Horizontal toolbar displayed above the plot for gate drawing actions.

    Signals
    -------
    draw_requested(gate_type)
        Emitted when the user picks a gate type.  ``gate_type`` is one of
        ``"rectangle"``, ``"polygon"``, ``"circle"``, ``"range"``.
    apply_requested
        Emitted when the user clicks Apply Gate.
    clear_requested
        Emitted when the user clicks Clear Draft.
    """

    draw_requested = Signal(str)
    apply_requested = Signal()
    clear_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(58)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._plot_mode = "scatter"

        # ── Draw Gate button ──────────────────────────────────────────
        self._draw_btn = QPushButton("Draw Gate  ▾")
        self._draw_btn.setToolTip(
            "Scatter: pick a gate shape from the menu.\n"
            "Histogram: immediately start selecting a range."
        )
        self._draw_btn.setStyleSheet(_DRAW_DEFAULT)
        self._draw_btn.clicked.connect(self._on_draw_clicked)

        # Popup menu shown in scatter mode
        self._gate_menu = QMenu(self)
        self._gate_menu.setToolTipsVisible(True)
        self._gate_menu.addAction("Rectangle").triggered.connect(
            lambda: self.draw_requested.emit("rectangle")
        )
        self._gate_menu.addAction("Polygon").triggered.connect(
            lambda: self.draw_requested.emit("polygon")
        )
        self._gate_menu.addAction("Circle").triggered.connect(
            lambda: self.draw_requested.emit("circle")
        )

        # ── Apply Gate button ─────────────────────────────────────────
        self._apply_btn = QPushButton("Apply Gate")
        self._apply_btn.setEnabled(False)
        self._apply_btn.setStyleSheet(_APPLY_INACTIVE)
        self._apply_btn.setToolTip("Confirm the current ROI as a named gate")
        self._apply_btn.clicked.connect(self.apply_requested.emit)

        # ── Clear Draft button ────────────────────────────────────────
        self._clear_btn = QPushButton("Clear Draft")
        self._clear_btn.setEnabled(False)
        self._clear_btn.setStyleSheet(_CLEAR_INACTIVE)
        self._clear_btn.setToolTip("Discard the current draft ROI")
        self._clear_btn.clicked.connect(self.clear_requested.emit)

        # ── Status label (right side) ─────────────────────────────────
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #6b7280; font-size: 12px;")

        # ── Layout ────────────────────────────────────────────────────
        layout = QHBoxLayout()
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)
        layout.addWidget(self._draw_btn)
        layout.addWidget(self._apply_btn)
        layout.addWidget(self._clear_btn)
        layout.addSpacing(12)
        layout.addWidget(self._status_label)
        layout.addStretch(1)
        self.setLayout(layout)

        # Separator line at bottom
        self.setStyleSheet(
            "GateToolbar { background: #fbfcfe; border-bottom: 1px solid #d7e0ea; }"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_plot_mode(self, mode: str) -> None:
        """Switch between scatter (shows type menu) and histogram (direct range)."""
        self._plot_mode = mode
        if mode == "histogram":
            self._draw_btn.setText("Draw Gate")
            self._draw_btn.setToolTip("Start selecting a range region on the histogram")
        else:
            self._draw_btn.setText("Draw Gate  ▾")
            self._draw_btn.setToolTip(
                "Click to choose gate shape: Rectangle, Polygon, or Circle"
            )

    def set_drawing_active(self, active: bool) -> None:
        """Enable Apply / Clear and change their colors when a draft ROI exists."""
        self._apply_btn.setEnabled(active)
        self._clear_btn.setEnabled(active)

        self._apply_btn.setStyleSheet(_APPLY_ACTIVE if active else _APPLY_INACTIVE)
        self._clear_btn.setStyleSheet(_CLEAR_ACTIVE if active else _CLEAR_INACTIVE)

        if active:
            self._status_label.setText("ROI ready — adjust it on the plot, then click Apply Gate.")
        else:
            self._status_label.setText("")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_draw_clicked(self) -> None:
        if self._plot_mode == "histogram":
            self.draw_requested.emit("range")
        else:
            pos = self._draw_btn.mapToGlobal(self._draw_btn.rect().bottomLeft())
            self._gate_menu.exec(pos)
