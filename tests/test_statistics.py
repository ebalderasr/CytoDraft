import numpy as np

from cytodraft.core.statistics import calculate_population_statistics


def test_calculate_population_statistics_for_population_and_channel() -> None:
    values = np.array([10.0, 20.0, 30.0, 40.0])
    population_mask = np.array([False, True, True, False])
    parent_mask = np.array([True, True, True, False])

    results = calculate_population_statistics(
        values[population_mask],
        population_mask,
        total_event_count=4,
        parent_mask=parent_mask,
        statistics=["event_count", "percent_parent", "percent_total", "mean", "median", "cv"],
    )

    result_map = {result.key: result.value for result in results}
    assert result_map["event_count"] == 2.0
    assert result_map["percent_parent"] == 2 / 3 * 100.0
    assert result_map["percent_total"] == 50.0
    assert result_map["mean"] == 25.0
    assert result_map["median"] == 25.0
    assert np.isclose(result_map["cv"], 20.0)


def test_calculate_population_statistics_returns_nan_for_empty_channel_values() -> None:
    results = calculate_population_statistics(
        np.array([]),
        np.array([False, False]),
        total_event_count=2,
        parent_mask=np.array([True, True]),
        statistics=["mean", "percent_total"],
    )

    result_map = {result.key: result.value for result in results}
    assert np.isnan(result_map["mean"])
    assert result_map["percent_total"] == 0.0
