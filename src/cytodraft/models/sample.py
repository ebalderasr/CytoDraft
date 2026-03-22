from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(slots=True)
class ChannelInfo:
    index: int
    number: int
    pnn: str
    pns: str
    pnr: float | None = None

    @property
    def display_name(self) -> str:
        return self.pns.strip() or self.pnn.strip() or f"Channel {self.number}"


@dataclass(slots=True)
class SampleData:
    file_path: Path
    version: str
    event_count: int
    channels: list[ChannelInfo]
    events: np.ndarray
    metadata: dict[str, str]
    scatter_indices: list[int]
    fluoro_indices: list[int]
    time_index: int | None = None

    @property
    def file_name(self) -> str:
        return self.file_path.name

    @property
    def channel_count(self) -> int:
        return len(self.channels)

    def channel_label(self, index: int) -> str:
        return self.channels[index].display_name
