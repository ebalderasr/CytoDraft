from __future__ import annotations

from pathlib import Path

import pandas as pd
from flowio import create_fcs

from cytodraft.core.statistics import StatisticResult
from cytodraft.models.sample import SampleData


def _validate_mask(sample: SampleData, mask) -> None:
    if len(mask) != sample.event_count:
        raise ValueError("Mask length does not match the number of sample events.")


def export_masked_events_to_csv(
    sample: SampleData,
    mask,
    output_path: str | Path,
) -> Path:
    output = Path(output_path)

    _validate_mask(sample, mask)

    selected_events = sample.events[mask]
    selected_indices = [i for i, keep in enumerate(mask) if keep]

    data = {
        "event_index": selected_indices,
    }

    for column_index, channel in enumerate(sample.channels):
        data[channel.display_name] = selected_events[:, column_index]

    df = pd.DataFrame(data)
    df.to_csv(output, index=False)

    return output


def export_masked_events_to_fcs(
    sample: SampleData,
    mask,
    output_path: str | Path,
) -> Path:
    output = Path(output_path)

    _validate_mask(sample, mask)

    selected_events = sample.events[mask]
    flattened_events = selected_events.astype("float32", copy=False).ravel(order="C").tolist()
    channel_names = [channel.pnn.strip() or f"Channel {channel.number}" for channel in sample.channels]
    opt_channel_names = [channel.pns.strip() or None for channel in sample.channels]
    metadata = {
        f"$P{index}R": str(channel.pnr)
        for index, channel in enumerate(sample.channels, start=1)
        if channel.pnr is not None
    }

    with output.open("wb") as handle:
        create_fcs(
            handle,
            flattened_events,
            channel_names,
            opt_channel_names=opt_channel_names,
            metadata_dict=metadata,
        )

    return output


def export_batch_statistics_to_csv(
    rows: list[dict],
    output_path: str | Path,
) -> Path:
    """Export a batch of statistics rows to CSV.

    Each row dict must have keys: group, sample, population, channel,
    statistic_key, statistic_label, value.
    """
    output = Path(output_path)
    col_order = [
        "group",
        "sample",
        "population",
        "channel",
        "statistic_key",
        "statistic_label",
        "value",
    ]
    df = pd.DataFrame(rows, columns=col_order)
    df.to_csv(output, index=False)
    return output


def export_population_statistics_to_csv(
    *,
    sample_name: str,
    population_name: str,
    channel_name: str,
    statistics: list[StatisticResult],
    output_path: str | Path,
) -> Path:
    output = Path(output_path)
    df = pd.DataFrame(
        {
            "sample": [sample_name] * len(statistics),
            "population": [population_name] * len(statistics),
            "channel": [channel_name] * len(statistics),
            "statistic_key": [result.key for result in statistics],
            "statistic_label": [result.label for result in statistics],
            "value": [result.value for result in statistics],
        }
    )
    df.to_csv(output, index=False)
    return output
