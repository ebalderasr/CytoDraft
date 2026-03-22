from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(slots=True)
class StatisticResult:
    key: str
    label: str
    value: float


STATISTIC_DEFINITIONS: list[tuple[str, str]] = [
    ("event_count", "Event count"),
    ("percent_parent", "% of parent"),
    ("percent_total", "% of total"),
    ("mean", "Mean"),
    ("median", "Median"),
    ("std", "Std dev"),
    ("cv", "CV %"),
    ("min", "Min"),
    ("max", "Max"),
    ("p5", "P5"),
    ("p95", "P95"),
]

CHANNEL_DEPENDENT_STATS = {"mean", "median", "std", "cv", "min", "max", "p5", "p95"}


def statistic_label(stat_key: str) -> str:
    for key, label in STATISTIC_DEFINITIONS:
        if key == stat_key:
            return label
    return stat_key


def available_statistic_keys() -> list[str]:
    return [key for key, _ in STATISTIC_DEFINITIONS]


def calculate_population_statistics(
    values: np.ndarray,
    population_mask: np.ndarray,
    *,
    total_event_count: int,
    parent_mask: np.ndarray | None = None,
    statistics: list[str] | None = None,
) -> list[StatisticResult]:
    selected_statistics = statistics or available_statistic_keys()
    finite_values = values[np.isfinite(values)]
    event_count = int(population_mask.sum())
    parent_count = int(parent_mask.sum()) if parent_mask is not None else total_event_count

    results: list[StatisticResult] = []
    for stat_key in selected_statistics:
        if stat_key == "event_count":
            value = float(event_count)
        elif stat_key == "percent_parent":
            value = (event_count / parent_count * 100.0) if parent_count else 0.0
        elif stat_key == "percent_total":
            value = (event_count / total_event_count * 100.0) if total_event_count else 0.0
        elif len(finite_values) == 0:
            value = float("nan")
        elif stat_key == "mean":
            value = float(np.mean(finite_values))
        elif stat_key == "median":
            value = float(np.median(finite_values))
        elif stat_key == "std":
            value = float(np.std(finite_values))
        elif stat_key == "cv":
            mean_value = float(np.mean(finite_values))
            std_value = float(np.std(finite_values))
            value = (std_value / mean_value * 100.0) if mean_value != 0.0 else float("nan")
        elif stat_key == "min":
            value = float(np.min(finite_values))
        elif stat_key == "max":
            value = float(np.max(finite_values))
        elif stat_key == "p5":
            value = float(np.percentile(finite_values, 5))
        elif stat_key == "p95":
            value = float(np.percentile(finite_values, 95))
        else:
            raise ValueError(f"Unsupported statistic: {stat_key}")

        results.append(StatisticResult(key=stat_key, label=statistic_label(stat_key), value=value))

    return results
