from __future__ import annotations

import numpy as np


def rectangle_mask(
    x: np.ndarray,
    y: np.ndarray,
    *,
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
) -> np.ndarray:
    x_low, x_high = sorted((x_min, x_max))
    y_low, y_high = sorted((y_min, y_max))

    return (x >= x_low) & (x <= x_high) & (y >= y_low) & (y <= y_high)
