from __future__ import annotations

import numpy as np

from cytodraft.core.statistics import (
    CHANNEL_DEPENDENT_STATS,
    StatisticResult,
    calculate_population_statistics,
    statistic_label,
)
from cytodraft.models.workspace import WorkspaceSample, WorkspaceState, WorkspaceStatisticColumn


class StatisticsService:
    def available_groups(self, workspace: WorkspaceState) -> list[str]:
        return sorted(workspace.groups)

    def available_populations(self, workspace: WorkspaceState, group_name: str | None) -> list[str]:
        population_names = ["All events"]
        seen = {"All events"}
        for _, workspace_sample in workspace.samples_in_group(group_name):
            for gate in workspace_sample.gates:
                if gate.name not in seen:
                    seen.add(gate.name)
                    population_names.append(gate.name)
        return population_names

    def available_channels(self, workspace: WorkspaceState, group_name: str | None) -> list[str]:
        channel_names: list[str] = []
        seen: set[str] = set()
        for _, workspace_sample in workspace.samples_in_group(group_name):
            for channel in workspace_sample.sample.channels:
                display_name = channel.display_name
                if display_name not in seen:
                    seen.add(display_name)
                    channel_names.append(display_name)
        return channel_names

    def calculate_for_workspace_sample(
        self,
        workspace_sample: WorkspaceSample,
        *,
        population_name: str,
        channel_name: str,
        statistic_key: str,
    ) -> StatisticResult | None:
        sample = workspace_sample.sample
        gate_by_name = {gate.name: gate for gate in workspace_sample.gates}

        if population_name == "All events":
            population_mask = np.ones(sample.event_count, dtype=bool)
            parent_mask: np.ndarray | None = None
        else:
            gate = gate_by_name.get(population_name)
            if gate is None:
                return None
            population_mask = gate.full_mask
            parent_gate = gate_by_name.get(gate.parent_name)
            parent_mask = (
                parent_gate.full_mask
                if parent_gate is not None
                else np.ones(sample.event_count, dtype=bool)
            )

        if statistic_key in CHANNEL_DEPENDENT_STATS:
            channel_index = next(
                (
                    index
                    for index, channel in enumerate(sample.channels)
                    if channel.display_name == channel_name
                ),
                None,
            )
            if channel_index is None:
                return None
            values = sample.events[population_mask, channel_index]
        else:
            values = np.empty(0)

        return calculate_population_statistics(
            values,
            population_mask,
            total_event_count=sample.event_count,
            parent_mask=parent_mask,
            statistics=[statistic_key],
        )[0]

    def format_result(self, result: StatisticResult | None) -> str:
        if result is None:
            return "—"
        if result.key == "event_count":
            return f"{int(round(result.value)):,}"
        if np.isnan(result.value):
            return "NaN"
        return f"{result.value:.4f}"

    def make_columns(
        self,
        *,
        group_name: str | None,
        population_name: str,
        channel_name: str,
        statistic_keys: list[str],
    ) -> list[WorkspaceStatisticColumn]:
        return [
            WorkspaceStatisticColumn(
                statistic_key=statistic_key,
                statistic_label=statistic_label(statistic_key),
                population_name=population_name,
                channel_name=channel_name,
                group_name=group_name,
            )
            for statistic_key in statistic_keys
        ]
