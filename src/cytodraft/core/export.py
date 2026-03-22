from __future__ import annotations

from pathlib import Path

import pandas as pd

from cytodraft.models.sample import SampleData


def export_masked_events_to_csv(
    sample: SampleData,
    mask,
    output_path: str | Path,
) -> Path:
    output = Path(output_path)

    if len(mask) != sample.event_count:
        raise ValueError("Mask length does not match the number of sample events.")

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
