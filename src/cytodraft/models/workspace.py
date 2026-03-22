from __future__ import annotations

from dataclasses import dataclass, field

from cytodraft.models.gate import CircleGate, PolygonGate, RangeGate, RectangleGate
from cytodraft.models.sample import SampleData

GateModel = RectangleGate | RangeGate | PolygonGate | CircleGate
DEFAULT_GROUP_NAME = "Ungrouped"
DEFAULT_GROUP_COLOR = "#5a6b7a"


@dataclass(slots=True)
class WorkspaceGroup:
    name: str
    color_hex: str = DEFAULT_GROUP_COLOR
    notes: str = ""


@dataclass(slots=True)
class WorkspaceSample:
    sample: SampleData
    group_name: str = DEFAULT_GROUP_NAME
    gates: list[GateModel] = field(default_factory=list)
    active_gate_name: str | None = None

    @property
    def display_name(self) -> str:
        return f"{self.sample.file_name} [{self.group_name}]"


@dataclass(slots=True)
class WorkspaceState:
    samples: list[WorkspaceSample] = field(default_factory=list)
    groups: dict[str, WorkspaceGroup] = field(default_factory=dict)
    active_sample_index: int | None = None

    @property
    def active_sample(self) -> WorkspaceSample | None:
        if self.active_sample_index is None:
            return None
        if self.active_sample_index < 0 or self.active_sample_index >= len(self.samples):
            return None
        return self.samples[self.active_sample_index]

    def add_sample(self, sample: SampleData, *, group_name: str = DEFAULT_GROUP_NAME) -> WorkspaceSample:
        self.ensure_group(group_name)
        workspace_sample = WorkspaceSample(sample=sample, group_name=group_name)
        self.samples.append(workspace_sample)
        self.active_sample_index = len(self.samples) - 1
        return workspace_sample

    def remove_sample(self, index: int) -> WorkspaceSample:
        removed = self.samples.pop(index)
        if not self.samples:
            self.active_sample_index = None
        elif self.active_sample_index is None:
            self.active_sample_index = min(index, len(self.samples) - 1)
        elif self.active_sample_index > index:
            self.active_sample_index -= 1
        elif self.active_sample_index == index:
            self.active_sample_index = min(index, len(self.samples) - 1)
        return removed

    def ensure_group(self, group_name: str) -> WorkspaceGroup:
        normalized_name = group_name.strip() or DEFAULT_GROUP_NAME
        group = self.groups.get(normalized_name)
        if group is None:
            group = WorkspaceGroup(name=normalized_name)
            self.groups[normalized_name] = group
        return group

    def rename_group(self, old_name: str, new_name: str) -> WorkspaceGroup:
        normalized_old = old_name.strip() or DEFAULT_GROUP_NAME
        normalized_new = new_name.strip() or DEFAULT_GROUP_NAME
        if normalized_old not in self.groups:
            raise ValueError(f"Unknown group '{normalized_old}'.")

        existing_target = self.groups.get(normalized_new)
        source_group = self.groups.pop(normalized_old)
        if existing_target is None:
            source_group.name = normalized_new
            self.groups[normalized_new] = source_group
            target_group = source_group
        else:
            target_group = existing_target
            if not target_group.notes and source_group.notes:
                target_group.notes = source_group.notes

        for sample in self.samples:
            if sample.group_name == normalized_old:
                sample.group_name = normalized_new

        return target_group

    def samples_in_group(self, group_name: str | None) -> list[tuple[int, WorkspaceSample]]:
        if group_name is None:
            return list(enumerate(self.samples))
        return [
            (index, sample)
            for index, sample in enumerate(self.samples)
            if sample.group_name == group_name
        ]
