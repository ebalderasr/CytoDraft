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
        self.plot_scatter(x, y, "FSC-A", "SSC-A", title="Placeholder scatter")

    def show_empty_message(self, title: str = "No data loaded") -> None:
        self.plot_widget.clear()
        self.plot_widget.setTitle(title)
        self.plot_widget.setLabel("bottom", "")
        self.plot_widget.setLabel("left", "")

    def _downsample(
        self,
        x: np.ndarray,
        y: np.ndarray,
        max_points: int | None,
    ) -> tuple[np.ndarray, np.ndarray, int, int]:
        total = len(x)

        if max_points is None or total <= max_points:
            return x, y, total, total

        rng = np.random.default_rng(42)
        indices = rng.choice(total, size=max_points, replace=False)
        return x[indices], y[indices], max_points, total

    def plot_scatter(
        self,
        x: np.ndarray,
        y: np.ndarray,
        x_label: str,
        y_label: str,
        *,
        title: str | None = None,
        max_points: int | None = None,
    ) -> tuple[int, int]:
        x_plot, y_plot, displayed_count, total_count = self._downsample(x, y, max_points)

        self.plot_widget.clear()
        self.plot_widget.setLabel("bottom", x_label)
        self.plot_widget.setLabel("left", y_label)

        plot_title = title or f"{y_label} vs {x_label}"
        if displayed_count < total_count:
            plot_title = f"{plot_title} (showing {displayed_count:,} / {total_count:,})"
        self.plot_widget.setTitle(plot_title)

        self._scatter_item = pg.ScatterPlotItem(
            x=x_plot,
            y=y_plot,
            size=4,
            pen=None,
            brush=(50, 100, 180, 120),
        )
        self.plot_widget.addItem(self._scatter_item)
        self.plot_widget.enableAutoRange()

        return displayed_count, total_count
