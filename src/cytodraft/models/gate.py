from __future__ import annotations

from dataclasses import dataclass

import numpy as np

DEFAULT_GATE_COLOR = "#d43c3c"


@dataclass(slots=True)
class RectangleGate:
    name: str
    parent_name: str
    x_channel_index: int
    y_channel_index: int
    x_label: str
    y_label: str
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    event_count: int
    percentage_parent: float
    percentage_total: float
    full_mask: np.ndarray
    x_scale: str = "linear"
    y_scale: str = "linear"
    color_hex: str = DEFAULT_GATE_COLOR

    @property
    def label(self) -> str:
        return (
            f"{self.name} | {self.event_count:,} events "
            f"({self.percentage_parent:.2f}% parent, {self.percentage_total:.2f}% total)"
        )


@dataclass(slots=True)
class RangeGate:
    name: str
    parent_name: str
    channel_index: int
    channel_label: str
    x_min: float
    x_max: float
    event_count: int
    percentage_parent: float
    percentage_total: float
    full_mask: np.ndarray
    x_scale: str = "linear"
    color_hex: str = DEFAULT_GATE_COLOR

    @property
    def label(self) -> str:
        return (
            f"{self.name} | {self.event_count:,} events "
            f"({self.percentage_parent:.2f}% parent, {self.percentage_total:.2f}% total)"
        )


@dataclass(slots=True)
class PolygonGate:
    name: str
    parent_name: str
    x_channel_index: int
    y_channel_index: int
    x_label: str
    y_label: str
    vertices: list[tuple[float, float]]
    event_count: int
    percentage_parent: float
    percentage_total: float
    full_mask: np.ndarray
    x_scale: str = "linear"
    y_scale: str = "linear"
    color_hex: str = DEFAULT_GATE_COLOR

    @property
    def label(self) -> str:
        return (
            f"{self.name} | {self.event_count:,} events "
            f"({self.percentage_parent:.2f}% parent, {self.percentage_total:.2f}% total)"
        )


@dataclass(slots=True)
class CircleGate:
    name: str
    parent_name: str
    x_channel_index: int
    y_channel_index: int
    x_label: str
    y_label: str
    center_x: float
    center_y: float
    radius: float
    event_count: int
    percentage_parent: float
    percentage_total: float
    full_mask: np.ndarray
    radius_x: float | None = None
    radius_y: float | None = None
    x_scale: str = "linear"
    y_scale: str = "linear"
    color_hex: str = DEFAULT_GATE_COLOR

    @property
    def label(self) -> str:
        return (
            f"{self.name} | {self.event_count:,} events "
            f"({self.percentage_parent:.2f}% parent, {self.percentage_total:.2f}% total)"
        )
