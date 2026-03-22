from pathlib import Path

import flowio
import numpy as np
import pandas as pd

from cytodraft.core.export import (
    export_masked_events_to_csv,
    export_masked_events_to_fcs,
    export_population_statistics_to_csv,
)
from cytodraft.core.statistics import StatisticResult
from cytodraft.models.sample import ChannelInfo, SampleData


def test_export_masked_events_to_csv(tmp_path: Path) -> None:
    channels = [
        ChannelInfo(index=0, number=1, pnn="FSC-A", pns="", pnr=1024.0),
        ChannelInfo(index=1, number=2, pnn="SSC-A", pns="", pnr=1024.0),
    ]
    events = np.array(
        [
            [10.0, 100.0],
            [20.0, 200.0],
            [30.0, 300.0],
        ]
    )
    sample = SampleData(
        file_path=Path("demo.fcs"),
        version="3.1",
        event_count=3,
        channels=channels,
        events=events,
        metadata={},
        scatter_indices=[0, 1],
        fluoro_indices=[],
        time_index=None,
    )

    mask = np.array([False, True, True])
    output_path = tmp_path / "gate.csv"

    export_masked_events_to_csv(sample, mask, output_path)

    df = pd.read_csv(output_path)
    assert list(df.columns) == ["event_index", "FSC-A", "SSC-A"]
    assert df["event_index"].tolist() == [1, 2]
    assert df["FSC-A"].tolist() == [20.0, 30.0]
    assert df["SSC-A"].tolist() == [200.0, 300.0]


def test_export_masked_events_to_fcs(tmp_path: Path) -> None:
    channels = [
        ChannelInfo(index=0, number=1, pnn="FSC-A", pns="FSC", pnr=1024.0),
        ChannelInfo(index=1, number=2, pnn="SSC-A", pns="SSC", pnr=2048.0),
    ]
    events = np.array(
        [
            [10.0, 100.0],
            [20.0, 200.0],
            [30.0, 300.0],
        ]
    )
    sample = SampleData(
        file_path=Path("demo.fcs"),
        version="3.1",
        event_count=3,
        channels=channels,
        events=events,
        metadata={},
        scatter_indices=[0, 1],
        fluoro_indices=[],
        time_index=None,
    )

    mask = np.array([False, True, True])
    output_path = tmp_path / "gate.fcs"

    export_masked_events_to_fcs(sample, mask, output_path)

    exported = flowio.FlowData(str(output_path))
    exported_events = np.array(exported.events, dtype=float).reshape(exported.event_count, 2)

    assert exported.event_count == 2
    assert np.allclose(exported_events, np.array([[20.0, 200.0], [30.0, 300.0]]))
    assert exported.channels[1]["pnn"] == "FSC-A"
    assert exported.channels[1]["pns"] == "FSC"
    assert exported.channels[1]["pnr"] == 1024.0


def test_export_population_statistics_to_csv(tmp_path: Path) -> None:
    output_path = tmp_path / "stats.csv"

    export_population_statistics_to_csv(
        sample_name="demo.fcs",
        population_name="Gate 1",
        channel_name="FSC-A",
        statistics=[
            StatisticResult(key="mean", label="Mean", value=12.5),
            StatisticResult(key="median", label="Median", value=11.0),
        ],
        output_path=output_path,
    )

    df = pd.read_csv(output_path)
    assert list(df.columns) == [
        "sample",
        "population",
        "channel",
        "statistic_key",
        "statistic_label",
        "value",
    ]
    assert df["sample"].tolist() == ["demo.fcs", "demo.fcs"]
    assert df["population"].tolist() == ["Gate 1", "Gate 1"]
    assert df["channel"].tolist() == ["FSC-A", "FSC-A"]
    assert df["statistic_key"].tolist() == ["mean", "median"]
    assert df["value"].tolist() == [12.5, 11.0]
