from pathlib import Path

import numpy as np

from cytodraft.core.fcs_reader import choose_default_axes
from cytodraft.models.sample import ChannelInfo, SampleData


def make_sample(scatter_indices: list[int], channel_count: int = 4) -> SampleData:
    channels = [
        ChannelInfo(index=i, number=i + 1, pnn=f"Ch{i+1}", pns="", pnr=1024.0)
        for i in range(channel_count)
    ]
    events = np.zeros((10, channel_count), dtype=float)
    return SampleData(
        file_path=Path("demo.fcs"),
        version="3.1",
        event_count=10,
        channels=channels,
        events=events,
        metadata={},
        scatter_indices=scatter_indices,
        fluoro_indices=[],
        time_index=None,
    )


def test_choose_default_axes_prefers_scatter_indices() -> None:
    sample = make_sample([2, 3])
    assert choose_default_axes(sample) == (2, 3)


def test_choose_default_axes_falls_back_to_first_two_channels() -> None:
    sample = make_sample([], channel_count=3)
    assert choose_default_axes(sample) == (0, 1)
