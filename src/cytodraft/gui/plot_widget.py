from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget


class CytometryPlotWidget(QWidget):
    """Central plotting area for 1D/2D cytometry views."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground("#fbfdff")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.12)
        self.plot_widget.setLabel("bottom", "X")
        self.plot_widget.setLabel("left", "Y")
        self.plot_widget.setTitle("CytoDraft plot area", color="#334155", size="12pt")
        self.plot_widget.setMenuEnabled(False)
        self.plot_widget.setAntialiasing(True)
        self.plot_widget.getPlotItem().getViewBox().setBorder(pg.mkPen("#d9e2ec"))
        self.plot_widget.getAxis("bottom").setPen(pg.mkPen("#94a3b8"))
        self.plot_widget.getAxis("left").setPen(pg.mkPen("#94a3b8"))
        self.plot_widget.getAxis("bottom").setTextPen(pg.mkPen("#475569"))
        self.plot_widget.getAxis("left").setTextPen(pg.mkPen("#475569"))

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.plot_widget)
        self.setLayout(layout)

        self._base_scatter_item: pg.ScatterPlotItem | None = None
        self._highlight_scatter_item: pg.ScatterPlotItem | None = None
        self._hist_item: pg.PlotDataItem | None = None
        self._rect_roi: pg.RectROI | None = None
        self._poly_roi: pg.PolyLineROI | None = None
        self._circle_roi: pg.CircleROI | None = None
        self._range_region: pg.LinearRegionItem | None = None

        self.show_placeholder_data()

    def clear_plot(self) -> None:
        self.plot_widget.clear()
        self._base_scatter_item = None
        self._highlight_scatter_item = None
        self._hist_item = None
        self._rect_roi = None
        self._poly_roi = None
        self._circle_roi = None
        self._range_region = None

    def show_placeholder_data(self) -> None:
        rng = np.random.default_rng(42)
        x = rng.normal(loc=5_000, scale=1_200, size=1200)
        y = rng.normal(loc=8_000, scale=1_800, size=1200)
        self.plot_scatter(x, y, "FSC-A", "SSC-A", title="Placeholder scatter")

    def show_empty_message(self, title: str = "No data loaded") -> None:
        self.plot_widget.clear()
        self._base_scatter_item = None
        self._highlight_scatter_item = None
        self._hist_item = None
        self._rect_roi = None
        self._poly_roi = None
        self._circle_roi = None
        self._range_region = None
        self.plot_widget.setTitle(title, color="#64748b", size="12pt")
        self.plot_widget.setLabel("bottom", "")
        self.plot_widget.setLabel("left", "")

    def _downsample(
        self,
        x: np.ndarray,
        y: np.ndarray,
        max_points: int | None,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
        total = len(x)

        if max_points is None or total <= max_points:
            indices = np.arange(total, dtype=int)
            return x, y, indices, total

        rng = np.random.default_rng(42)
        indices = rng.choice(total, size=max_points, replace=False)
        return x[indices], y[indices], indices, total

    def plot_scatter(
        self,
        x: np.ndarray,
        y: np.ndarray,
        x_label: str,
        y_label: str,
        *,
        title: str | None = None,
        max_points: int | None = None,
        selected_mask: np.ndarray | None = None,
        point_color: str = "#466ebe",
    ) -> tuple[int, int]:
        x_plot, y_plot, display_indices, total_count = self._downsample(x, y, max_points)
        displayed_count = len(display_indices)
        base_color = QColor(point_color)
        base_brush = (
            base_color.red(),
            base_color.green(),
            base_color.blue(),
            110,
        )
        highlight_pen = pg.mkPen(base_color.darker(140), width=1)
        highlight_brush = (
            base_color.red(),
            base_color.green(),
            base_color.blue(),
            190,
        )

        self.plot_widget.clear()
        self._rect_roi = None
        self._poly_roi = None
        self._circle_roi = None
        self._range_region = None
        self._base_scatter_item = None
        self._highlight_scatter_item = None
        self._hist_item = None

        self.plot_widget.setLabel("bottom", x_label)
        self.plot_widget.setLabel("left", y_label)

        plot_title = title or f"{y_label} vs {x_label}"
        if displayed_count < total_count:
            plot_title = f"{plot_title} (showing {displayed_count:,} / {total_count:,})"
        self.plot_widget.setTitle(plot_title, color="#334155", size="12pt")

        self._base_scatter_item = pg.ScatterPlotItem(
            x=x_plot,
            y=y_plot,
            size=4,
            pen=None,
            brush=base_brush,
        )
        self.plot_widget.addItem(self._base_scatter_item)

        if selected_mask is not None and len(selected_mask) == total_count:
            selected_display_mask = selected_mask[display_indices]
            if np.any(selected_display_mask):
                x_sel = x_plot[selected_display_mask]
                y_sel = y_plot[selected_display_mask]

                self._highlight_scatter_item = pg.ScatterPlotItem(
                    x=x_sel,
                    y=y_sel,
                    size=5,
                    pen=highlight_pen,
                    brush=highlight_brush,
                )
                self.plot_widget.addItem(self._highlight_scatter_item)

        self.plot_widget.enableAutoRange()
        return displayed_count, total_count

    def plot_histogram(
        self,
        values: np.ndarray,
        x_label: str,
        *,
        title: str | None = None,
        bins: int = 128,
    ) -> tuple[int, int]:
        self.plot_widget.clear()
        self._rect_roi = None
        self._poly_roi = None
        self._circle_roi = None
        self._range_region = None
        self._base_scatter_item = None
        self._highlight_scatter_item = None
        self._hist_item = None

        total_count = len(values)
        displayed_count = total_count

        if total_count == 0:
            self.show_empty_message("Histogram: no plottable events")
            return 0, 0

        bin_count = min(bins, max(16, int(np.sqrt(total_count))))
        counts, edges = np.histogram(values, bins=bin_count)

        self.plot_widget.setLabel("bottom", x_label)
        self.plot_widget.setLabel("left", "Count")
        self.plot_widget.setTitle(title or f"{x_label} histogram", color="#334155", size="12pt")

        self._hist_item = self.plot_widget.plot(
            edges,
            counts,
            stepMode="center",
            fillLevel=0,
            brush=(70, 110, 190, 100),
            pen=pg.mkPen((70, 110, 190), width=1),
        )

        self.plot_widget.enableAutoRange()
        return displayed_count, total_count

    def set_manual_ranges(
        self,
        *,
        x_min: float | None,
        x_max: float | None,
        y_min: float | None,
        y_max: float | None,
    ) -> None:
        if x_min is not None and x_max is not None and x_max > x_min:
            self.plot_widget.setXRange(x_min, x_max, padding=0.0)

        if y_min is not None and y_max is not None and y_max > y_min:
            self.plot_widget.setYRange(y_min, y_max, padding=0.0)

    def auto_range(self) -> None:
        self.plot_widget.autoRange()

    def create_rectangle_roi(self) -> bool:
        view_range = self.plot_widget.viewRange()
        if not view_range or len(view_range) != 2:
            return False

        (x_min, x_max), (y_min, y_max) = view_range

        if x_max <= x_min or y_max <= y_min:
            return False

        width = (x_max - x_min) * 0.35
        height = (y_max - y_min) * 0.35

        x0 = x_min + (x_max - x_min) * 0.325
        y0 = y_min + (y_max - y_min) * 0.325

        self.clear_all_rois()

        roi = pg.RectROI(
            [x0, y0],
            [width, height],
            pen=pg.mkPen((200, 60, 60), width=2),
            movable=True,
            removable=False,
            rotatable=False,
            resizable=True,
        )
        roi.addScaleHandle((0, 0), (1, 1))
        roi.addScaleHandle((1, 1), (0, 0))
        roi.addScaleHandle((0, 1), (1, 0))
        roi.addScaleHandle((1, 0), (0, 1))

        self.plot_widget.addItem(roi)
        self._rect_roi = roi
        return True

    def create_polygon_roi(self) -> bool:
        view_range = self.plot_widget.viewRange()
        if not view_range or len(view_range) != 2:
            return False

        (x_min, x_max), (y_min, y_max) = view_range
        if x_max <= x_min or y_max <= y_min:
            return False

        cx = x_min + (x_max - x_min) * 0.5
        cy = y_min + (y_max - y_min) * 0.5
        rx = (x_max - x_min) * 0.18
        ry = (y_max - y_min) * 0.18

        points = [
            (cx - rx, cy - ry * 0.3),
            (cx - rx * 0.25, cy - ry),
            (cx + rx, cy - ry * 0.2),
            (cx + rx * 0.65, cy + ry),
            (cx - rx * 0.85, cy + ry * 0.75),
        ]

        self.clear_all_rois()

        roi = pg.PolyLineROI(
            points,
            closed=True,
            pen=pg.mkPen((200, 60, 60), width=2),
            movable=True,
            removable=False,
            rotatable=False,
            resizable=False,
        )
        self.plot_widget.addItem(roi)
        self._poly_roi = roi
        return True

    def create_circle_roi(self) -> bool:
        view_range = self.plot_widget.viewRange()
        if not view_range or len(view_range) != 2:
            return False

        (x_min, x_max), (y_min, y_max) = view_range
        if x_max <= x_min or y_max <= y_min:
            return False

        size = min(x_max - x_min, y_max - y_min) * 0.28
        x0 = x_min + (x_max - x_min - size) * 0.5
        y0 = y_min + (y_max - y_min - size) * 0.5

        self.clear_all_rois()

        roi = pg.CircleROI(
            [x0, y0],
            [size, size],
            pen=pg.mkPen((200, 60, 60), width=2),
            movable=True,
            removable=False,
            rotatable=False,
            resizable=True,
        )
        roi.addScaleHandle((1, 0.5), (0, 0.5))
        roi.addScaleHandle((0.5, 1), (0.5, 0))

        self.plot_widget.addItem(roi)
        self._circle_roi = roi
        return True

    def create_range_region(self) -> bool:
        view_range = self.plot_widget.viewRange()
        if not view_range or len(view_range) != 2:
            return False

        (x_min, x_max), _ = view_range
        if x_max <= x_min:
            return False

        width = (x_max - x_min) * 0.35
        x0 = x_min + (x_max - x_min) * 0.325

        self.clear_all_rois()

        region = pg.LinearRegionItem(
            values=(x0, x0 + width),
            orientation="vertical",
            movable=True,
            brush=(255, 140, 0, 50),
            pen=pg.mkPen((200, 60, 60), width=2),
        )
        self.plot_widget.addItem(region)
        self._range_region = region
        return True

    def clear_all_rois(self) -> None:
        self.clear_rectangle_roi()
        self.clear_polygon_roi()
        self.clear_circle_roi()
        self.clear_range_region()

    def clear_rectangle_roi(self) -> None:
        if self._rect_roi is not None:
            self.plot_widget.removeItem(self._rect_roi)
            self._rect_roi = None

    def clear_polygon_roi(self) -> None:
        if self._poly_roi is not None:
            self.plot_widget.removeItem(self._poly_roi)
            self._poly_roi = None

    def clear_circle_roi(self) -> None:
        if self._circle_roi is not None:
            self.plot_widget.removeItem(self._circle_roi)
            self._circle_roi = None

    def clear_range_region(self) -> None:
        if self._range_region is not None:
            self.plot_widget.removeItem(self._range_region)
            self._range_region = None

    def rectangle_roi_bounds(self) -> tuple[float, float, float, float] | None:
        if self._rect_roi is None:
            return None

        pos = self._rect_roi.pos()
        size = self._rect_roi.size()

        x_min = float(pos.x())
        y_min = float(pos.y())
        x_max = float(pos.x() + size.x())
        y_max = float(pos.y() + size.y())

        return x_min, x_max, y_min, y_max

    def polygon_roi_points(self) -> list[tuple[float, float]] | None:
        if self._poly_roi is None:
            return None

        state = self._poly_roi.saveState()
        pos_x, pos_y = state["pos"]
        points = state["points"]

        return [
            (float(pos_x + px), float(pos_y + py))
            for px, py in points
        ]

    def range_region_bounds(self) -> tuple[float, float] | None:
        if self._range_region is None:
            return None

        x_min, x_max = self._range_region.getRegion()
        return float(x_min), float(x_max)

    def circle_roi_geometry(self) -> tuple[float, float, float] | None:
        if self._circle_roi is None:
            return None

        pos = self._circle_roi.pos()
        size = self._circle_roi.size()
        diameter = min(float(size.x()), float(size.y()))
        radius = diameter / 2.0
        center_x = float(pos.x()) + radius
        center_y = float(pos.y()) + radius
        return center_x, center_y, radius
