import numpy as np

from cytodraft.core.gating import rectangle_mask, rectangle_mask_from_parent


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
