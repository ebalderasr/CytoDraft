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


def rectangle_mask_from_parent(
    x: np.ndarray,
    y: np.ndarray,
    parent_mask: np.ndarray,
    *,
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
) -> np.ndarray:
    if len(x) != len(parent_mask) or len(y) != len(parent_mask):
        raise ValueError("x, y, and parent_mask must have the same length.")

    full_mask = np.zeros(len(parent_mask), dtype=bool)

    if not np.any(parent_mask):
        return full_mask

    parent_indices = np.flatnonzero(parent_mask)
    x_parent = x[parent_mask]
    y_parent = y[parent_mask]

    child_mask_within_parent = rectangle_mask(
        x_parent,
        y_parent,
        x_min=x_min,
        x_max=x_max,
        y_min=y_min,
        y_max=y_max,
    )

    full_mask[parent_indices[child_mask_within_parent]] = True
    return full_mask
