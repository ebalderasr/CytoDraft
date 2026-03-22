from __future__ import annotations

from dataclasses import dataclass

import numpy as np


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

    @property
    def label(self) -> str:
        return (
            f"{self.name} | {self.event_count:,} events "
            f"({self.percentage_parent:.2f}% parent, {self.percentage_total:.2f}% total)"
        )
