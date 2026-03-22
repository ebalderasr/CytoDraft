from __future__ import annotations

from dataclasses import dataclass, field

from cytodraft.models.gate import CircleGate, PolygonGate, RangeGate, RectangleGate
from cytodraft.models.sample import SampleData

GateModel = RectangleGate | RangeGate | PolygonGate | CircleGate
DEFAULT_GROUP_NAME = "Ungrouped"
DEFAULT_GROUP_COLOR = "#5a6b7a"
COMPENSATION_GROUP_NAME = "Compensation"
COMPENSATION_GROUP_COLOR = "#0f766e"
COMPENSATION_GROUP_NOTES = "Reserved for single-stain compensation controls."


@dataclass(slots=True)
class WorkspaceGroup:
    name: str
    color_hex: str = DEFAULT_GROUP_COLOR
    notes: str = ""


@dataclass(slots=True)
class CompensationSampleMetadata:
    control_type: str = "single_stain"
    fluorochrome: str = ""
    target_channel: str = ""
    notes: str = ""

    @property
    def summary(self) -> str:
        parts: list[str] = []
        if self.control_type:
            parts.append(self.control_type.replace("_", " ").title())
        if self.fluorochrome:
            parts.append(self.fluorochrome)
        if self.target_channel:
            parts.append(f"-> {self.target_channel}")
        return " | ".join(parts) if parts else "Compensation sample"


@dataclass(slots=True)
class CompensationPopulationSelection:
    sample_index: int | None = None
    population_name: str = ""

    @property
    def is_configured(self) -> bool:
        return self.sample_index is not None and bool(self.population_name.strip())


@dataclass(slots=True)
class WorkspaceSample:
    sample: SampleData
    group_name: str = DEFAULT_GROUP_NAME
    gates: list[GateModel] = field(default_factory=list)
    active_gate_name: str | None = None
    compensation: CompensationSampleMetadata = field(default_factory=CompensationSampleMetadata)
    compensation_positive: CompensationPopulationSelection = field(default_factory=CompensationPopulationSelection)
    compensation_negative: CompensationPopulationSelection = field(default_factory=CompensationPopulationSelection)
    use_universal_negative: bool = False
    keywords: dict[str, str] = field(default_factory=dict)

    @property
    def display_name(self) -> str:
        if self.group_name == COMPENSATION_GROUP_NAME:
            summary = self.compensation.summary
            return f"{self.sample.file_name} | {summary}"
        return self.sample.file_name


@dataclass(slots=True)
class WorkspaceState:
    samples: list[WorkspaceSample] = field(default_factory=list)
    groups: dict[str, WorkspaceGroup] = field(default_factory=dict)
    active_sample_index: int | None = None
    universal_negative_sample_index: int | None = None
    keyword_columns: list[str] = field(default_factory=list)

    def add_keyword_column(self, name: str) -> None:
        if name not in self.keyword_columns:
            self.keyword_columns.append(name)

    def remove_keyword_column(self, name: str) -> None:
        if name in self.keyword_columns:
            self.keyword_columns.remove(name)
            for ws in self.samples:
                ws.keywords.pop(name, None)

    def __post_init__(self) -> None:
        self.ensure_group(COMPENSATION_GROUP_NAME).color_hex = COMPENSATION_GROUP_COLOR
        self.groups[COMPENSATION_GROUP_NAME].notes = COMPENSATION_GROUP_NOTES

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
        if self.universal_negative_sample_index == index:
            self.universal_negative_sample_index = None
        elif self.universal_negative_sample_index is not None and self.universal_negative_sample_index > index:
            self.universal_negative_sample_index -= 1

        for sample in self.samples:
            for selection in (sample.compensation_positive, sample.compensation_negative):
                if selection.sample_index == index:
                    selection.sample_index = None
                    selection.population_name = ""
                elif selection.sample_index is not None and selection.sample_index > index:
                    selection.sample_index -= 1

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

    def compensation_samples(self) -> list[tuple[int, WorkspaceSample]]:
        return self.samples_in_group(COMPENSATION_GROUP_NAME)
