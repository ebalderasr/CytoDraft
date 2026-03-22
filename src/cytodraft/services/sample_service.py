from __future__ import annotations

from pathlib import Path

from cytodraft.core.fcs_reader import read_fcs
from cytodraft.models.sample import SampleData


class SampleService:
    def load_sample(self, file_path: str | Path) -> SampleData:
        return read_fcs(file_path, preprocess=True)
