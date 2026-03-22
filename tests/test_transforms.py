import numpy as np

from cytodraft.core.transforms import apply_scale, axis_label


def test_apply_scale_linear_returns_same_values() -> None:
    values = np.array([1.0, 2.0, 3.0])
    result = apply_scale(values, "linear")
    assert np.allclose(result, values)


def test_apply_scale_log10_sets_nonpositive_to_nan() -> None:
    values = np.array([-1.0, 0.0, 1.0, 10.0, 100.0])
    result = apply_scale(values, "log10")

    assert np.isnan(result[0])
    assert np.isnan(result[1])
    assert np.isclose(result[2], 0.0)
    assert np.isclose(result[3], 1.0)
    assert np.isclose(result[4], 2.0)


def test_apply_scale_asinh_handles_negative_values() -> None:
    values = np.array([-10.0, 0.0, 10.0])
    result = apply_scale(values, "asinh")

    assert np.isfinite(result).all()
    assert np.isclose(result[1], 0.0)


def test_axis_label_appends_scale_for_non_linear_modes() -> None:
    assert axis_label("FSC-A", "linear") == "FSC-A"
    assert axis_label("FSC-A", "log10") == "FSC-A [log10]"
    assert axis_label("FSC-A", "asinh") == "FSC-A [asinh]"
