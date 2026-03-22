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


def range_mask(
    x: np.ndarray,
    *,
    x_min: float,
    x_max: float,
) -> np.ndarray:
    low, high = sorted((x_min, x_max))
    return (x >= low) & (x <= high)


def range_mask_from_parent(
    x: np.ndarray,
    parent_mask: np.ndarray,
    *,
    x_min: float,
    x_max: float,
) -> np.ndarray:
    if len(x) != len(parent_mask):
        raise ValueError("x and parent_mask must have the same length.")

    full_mask = np.zeros(len(parent_mask), dtype=bool)

    if not np.any(parent_mask):
        return full_mask

    parent_indices = np.flatnonzero(parent_mask)
    x_parent = x[parent_mask]

    child_mask_within_parent = range_mask(
        x_parent,
        x_min=x_min,
        x_max=x_max,
    )

    full_mask[parent_indices[child_mask_within_parent]] = True
    return full_mask


def polygon_mask(
    x: np.ndarray,
    y: np.ndarray,
    vertices: list[tuple[float, float]],
) -> np.ndarray:
    if len(vertices) < 3:
        raise ValueError("A polygon requires at least 3 vertices.")

    xv = np.asarray([p[0] for p in vertices], dtype=float)
    yv = np.asarray([p[1] for p in vertices], dtype=float)

    inside = np.zeros(len(x), dtype=bool)
    j = len(vertices) - 1
    eps = 1e-12

    for i in range(len(vertices)):
        xi, yi = xv[i], yv[i]
        xj, yj = xv[j], yv[j]

        intersects = ((yi > y) != (yj > y)) & (
            x < ((xj - xi) * (y - yi) / ((yj - yi) + eps) + xi)
        )
        inside ^= intersects
        j = i

    return inside


def polygon_mask_from_parent(
    x: np.ndarray,
    y: np.ndarray,
    parent_mask: np.ndarray,
    vertices: list[tuple[float, float]],
) -> np.ndarray:
    if len(x) != len(parent_mask) or len(y) != len(parent_mask):
        raise ValueError("x, y, and parent_mask must have the same length.")

    full_mask = np.zeros(len(parent_mask), dtype=bool)

    if not np.any(parent_mask):
        return full_mask

    parent_indices = np.flatnonzero(parent_mask)
    x_parent = x[parent_mask]
    y_parent = y[parent_mask]

    child_mask_within_parent = polygon_mask(
        x_parent,
        y_parent,
        vertices,
    )

    full_mask[parent_indices[child_mask_within_parent]] = True
    return full_mask


def circle_mask(
    x: np.ndarray,
    y: np.ndarray,
    *,
    center_x: float,
    center_y: float,
    radius: float | None = None,
    radius_x: float | None = None,
    radius_y: float | None = None,
) -> np.ndarray:
    resolved_radius_x = abs(radius_x) if radius_x is not None else abs(radius or 0.0)
    resolved_radius_y = abs(radius_y) if radius_y is not None else abs(radius or 0.0)
    if resolved_radius_x == 0 or resolved_radius_y == 0:
        return np.zeros(len(x), dtype=bool)

    dx = (x - center_x) / resolved_radius_x
    dy = (y - center_y) / resolved_radius_y
    return (dx * dx + dy * dy) <= 1.0


def circle_mask_from_parent(
    x: np.ndarray,
    y: np.ndarray,
    parent_mask: np.ndarray,
    *,
    center_x: float,
    center_y: float,
    radius: float | None = None,
    radius_x: float | None = None,
    radius_y: float | None = None,
) -> np.ndarray:
    if len(x) != len(parent_mask) or len(y) != len(parent_mask):
        raise ValueError("x, y, and parent_mask must have the same length.")

    full_mask = np.zeros(len(parent_mask), dtype=bool)

    if not np.any(parent_mask):
        return full_mask

    parent_indices = np.flatnonzero(parent_mask)
    x_parent = x[parent_mask]
    y_parent = y[parent_mask]

    child_mask_within_parent = circle_mask(
        x_parent,
        y_parent,
        center_x=center_x,
        center_y=center_y,
        radius=radius,
        radius_x=radius_x,
        radius_y=radius_y,
    )

    full_mask[parent_indices[child_mask_within_parent]] = True
    return full_mask
