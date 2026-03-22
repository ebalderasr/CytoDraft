from __future__ import annotations

from pathlib import Path

import flowio
import numpy as np

from cytodraft.models.sample import ChannelInfo, SampleData


def _build_channel_info(flow_data: flowio.FlowData) -> list[ChannelInfo]:
    channels: list[ChannelInfo] = []

    for zero_based_index, (channel_number, meta) in enumerate(sorted(flow_data.channels.items())):
        channels.append(
            ChannelInfo(
                index=zero_based_index,
                number=int(channel_number),
                pnn=str(meta.get("pnn", "")),
                pns=str(meta.get("pns", "")),
                pnr=float(meta["pnr"]) if meta.get("pnr") is not None else None,
            )
        )

    return channels


def choose_default_axes(sample: SampleData) -> tuple[int, int]:
    if len(sample.scatter_indices) >= 2:
        return sample.scatter_indices[0], sample.scatter_indices[1]

    if sample.channel_count >= 2:
        return 0, 1

    raise ValueError("Sample must contain at least two channels to plot a scatter view.")


def read_fcs(file_path: str | Path, *, preprocess: bool = True) -> SampleData:
    path = Path(file_path)

    flow_data = flowio.FlowData(path)
    events = np.asarray(flow_data.as_array(preprocess=preprocess), dtype=float)
    channels = _build_channel_info(flow_data)

    event_count = int(flow_data.text.get("tot", events.shape[0]))

    return SampleData(
        file_path=path,
        version=str(flow_data.version),
        event_count=event_count,
        channels=channels,
        events=events,
        metadata={str(k): str(v) for k, v in flow_data.text.items()},
        scatter_indices=list(flow_data.scatter_indices),
        fluoro_indices=list(flow_data.fluoro_indices),
        time_index=flow_data.time_index,
    )
