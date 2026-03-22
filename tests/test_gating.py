import numpy as np

from cytodraft.core.gating import (
    circle_mask,
    circle_mask_from_parent,
    polygon_mask,
    polygon_mask_from_parent,
    range_mask,
    range_mask_from_parent,
    rectangle_mask,
    rectangle_mask_from_parent,
)


def test_rectangle_mask_selects_points_inside_bounds() -> None:
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    y = np.array([1.0, 2.0, 3.0, 4.0, 5.0])

    mask = rectangle_mask(
        x,
        y,
        x_min=2.0,
        x_max=4.0,
        y_min=2.0,
        y_max=4.0,
    )

    assert mask.tolist() == [False, True, True, True, False]


def test_rectangle_mask_sorts_inverted_bounds() -> None:
    x = np.array([1.0, 2.0, 3.0])
    y = np.array([1.0, 2.0, 3.0])

    mask = rectangle_mask(
        x,
        y,
        x_min=3.0,
        x_max=1.5,
        y_min=3.0,
        y_max=1.5,
    )

    assert mask.tolist() == [False, True, True]


def test_rectangle_mask_from_parent_only_selects_within_parent() -> None:
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    y = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    parent_mask = np.array([False, True, True, False, True])

    child_mask = rectangle_mask_from_parent(
        x,
        y,
        parent_mask,
        x_min=2.5,
        x_max=5.5,
        y_min=2.5,
        y_max=5.5,
    )

    assert child_mask.tolist() == [False, False, True, False, True]


def test_range_mask_selects_interval() -> None:
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    mask = range_mask(x, x_min=2.0, x_max=4.0)
    assert mask.tolist() == [False, True, True, True, False]


def test_range_mask_from_parent_only_selects_within_parent() -> None:
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    parent_mask = np.array([False, True, True, False, True])

    child_mask = range_mask_from_parent(
        x,
        parent_mask,
        x_min=2.5,
        x_max=5.5,
    )

    assert child_mask.tolist() == [False, False, True, False, True]


def test_polygon_mask_selects_points_inside_polygon() -> None:
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    y = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    vertices = [(1.5, 1.5), (4.5, 1.5), (4.5, 4.5), (1.5, 4.5)]

    mask = polygon_mask(x, y, vertices)
    assert mask.tolist() == [False, True, True, True, False]


def test_polygon_mask_from_parent_only_selects_within_parent() -> None:
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    y = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    parent_mask = np.array([False, True, True, False, True])
    vertices = [(1.5, 1.5), (5.5, 1.5), (5.5, 5.5), (1.5, 5.5)]

    child_mask = polygon_mask_from_parent(x, y, parent_mask, vertices)
    assert child_mask.tolist() == [False, True, True, False, True]


def test_circle_mask_selects_points_inside_radius() -> None:
    x = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    y = np.array([0.0, 1.0, 2.0, 3.0, 4.0])

    mask = circle_mask(x, y, center_x=2.0, center_y=2.0, radius=np.sqrt(2.0))

    assert mask.tolist() == [False, True, True, True, False]


def test_circle_mask_from_parent_only_selects_within_parent() -> None:
    x = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    y = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    parent_mask = np.array([False, True, True, False, True])

    child_mask = circle_mask_from_parent(
        x,
        y,
        parent_mask,
        center_x=2.0,
        center_y=2.0,
        radius=2.0,
    )

    assert child_mask.tolist() == [False, True, True, False, False]
