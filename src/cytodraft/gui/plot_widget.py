from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import QVBoxLayout, QWidget


class CytometryPlotWidget(QWidget):
    """Central plotting area for 1D/2D cytometry views."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground("w")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.2)
        self.plot_widget.setLabel("bottom", "X")
        self.plot_widget.setLabel("left", "Y")
        self.plot_widget.setTitle("CytoDraft plot area")

        layout = QVBoxLayout()
        layout.addWidget(self.plot_widget)
        self.setLayout(layout)

        self._scatter_item: pg.ScatterPlotItem | None = None
        self.show_placeholder_data()

    def clear_plot(self) -> None:
        self.plot_widget.clear()
        self._scatter_item = None

    def show_placeholder_data(self) -> None:
        rng = np.random.default_rng(42)
        x = rng.normal(loc=5_000, scale=1_200, size=1200)
        y = rng.normal(loc=8_000, scale=1_800, size=1200)

        self.plot_widget.clear()
        self.plot_widget.setLabel("bottom", "FSC-A")
        self.plot_widget.setLabel("left", "SSC-A")
        self.plot_widget.setTitle("Placeholder scatter")

        self._scatter_item = pg.ScatterPlotItem(
            x=x,
            y=y,
            size=4,
            pen=None,
            brush=(50, 100, 180, 120),
        )
        self.plot_widget.addItem(self._scatter_item)
        self.plot_widget.enableAutoRange()

    def plot_scatter(self, x: np.ndarray, y: np.ndarray, x_label: str, y_label: str) -> None:
        self.plot_widget.clear()
        self.plot_widget.setLabel("bottom", x_label)
        self.plot_widget.setLabel("left", y_label)
        self.plot_widget.setTitle(f"{y_label} vs {x_label}")

        self._scatter_item = pg.ScatterPlotItem(
            x=x,
            y=y,
            size=4,
            pen=None,
            brush=(50, 100, 180, 120),
        )
        self.plot_widget.addItem(self._scatter_item)
        self.plot_widget.enableAutoRange()
