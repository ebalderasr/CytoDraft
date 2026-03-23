from __future__ import annotations

import numpy as np

from cytodraft.core.gating import (
    circle_mask_from_parent,
    polygon_mask_from_parent,
    range_mask_from_parent,
    rectangle_mask_from_parent,
)
from cytodraft.core.transforms import apply_scale
from cytodraft.models.gate import CircleGate, PolygonGate, RangeGate, RectangleGate
from cytodraft.models.sample import SampleData
from cytodraft.models.workspace import WorkspaceSample, WorkspaceState

GateModel = RectangleGate | RangeGate | PolygonGate | CircleGate


class GateService:
    def propagate_gates(
        self,
        workspace: WorkspaceState,
        *,
        source_sample_index: int,
        gate_names: list[str],
        target_group_name: str | None = None,
    ) -> tuple[int, list[str], str]:
        if source_sample_index < 0 or source_sample_index >= len(workspace.samples):
            return 0, ["Invalid source sample."], "selected samples"

        source_sample = workspace.samples[source_sample_index]
        gates_to_apply = self.selected_gate_sequence(source_sample.gates, gate_names)
        if not gates_to_apply:
            return 0, ["The source sample has no matching gates to propagate."], "selected samples"

        if target_group_name is None:
            target_samples = [
                candidate
                for idx, candidate in enumerate(workspace.samples)
                if idx != source_sample_index
            ]
            scope_label = "all samples"
        else:
            target_samples = [
                candidate
                for idx, candidate in enumerate(workspace.samples)
                if idx != source_sample_index and candidate.group_name == target_group_name
            ]
            scope_label = f"group {target_group_name}"

        if not target_samples:
            return 0, [], scope_label

        applied_count = 0
        failures: list[str] = []
        for target in target_samples:
            try:
                self.replace_gates_on_sample(target, gates_to_apply)
                applied_count += 1
            except Exception as exc:
                failures.append(f"{target.sample.file_name}: {exc}")
        return applied_count, failures, scope_label

    def clone_gate_to_sample(
        self,
        gate: GateModel,
        sample: SampleData,
        existing_gates: list[GateModel],
    ) -> GateModel:
        parent_mask = self._parent_mask(sample, gate.parent_name, existing_gates)
        parent_count = int(parent_mask.sum())
        total_count = sample.event_count

        if isinstance(gate, RectangleGate):
            x_idx = self._resolve_channel_index(sample, gate.x_channel_index, gate.x_label)
            y_idx = self._resolve_channel_index(sample, gate.y_channel_index, gate.y_label)
            x = apply_scale(sample.events[:, x_idx], gate.x_scale)
            y = apply_scale(sample.events[:, y_idx], gate.y_scale)
            full_mask = rectangle_mask_from_parent(
                x,
                y,
                parent_mask,
                x_min=gate.x_min,
                x_max=gate.x_max,
                y_min=gate.y_min,
                y_max=gate.y_max,
            )
            return RectangleGate(
                name=gate.name,
                parent_name=gate.parent_name,
                x_channel_index=x_idx,
                y_channel_index=y_idx,
                x_label=sample.channel_label(x_idx),
                y_label=sample.channel_label(y_idx),
                x_min=gate.x_min,
                x_max=gate.x_max,
                y_min=gate.y_min,
                y_max=gate.y_max,
                event_count=int(full_mask.sum()),
                percentage_parent=self._percentage(int(full_mask.sum()), parent_count),
                percentage_total=self._percentage(int(full_mask.sum()), total_count),
                full_mask=full_mask,
                x_scale=gate.x_scale,
                y_scale=gate.y_scale,
                color_hex=gate.color_hex,
            )

        if isinstance(gate, PolygonGate):
            x_idx = self._resolve_channel_index(sample, gate.x_channel_index, gate.x_label)
            y_idx = self._resolve_channel_index(sample, gate.y_channel_index, gate.y_label)
            x = apply_scale(sample.events[:, x_idx], gate.x_scale)
            y = apply_scale(sample.events[:, y_idx], gate.y_scale)
            full_mask = polygon_mask_from_parent(
                x,
                y,
                parent_mask,
                gate.vertices,
            )
            return PolygonGate(
                name=gate.name,
                parent_name=gate.parent_name,
                x_channel_index=x_idx,
                y_channel_index=y_idx,
                x_label=sample.channel_label(x_idx),
                y_label=sample.channel_label(y_idx),
                vertices=[(float(px), float(py)) for px, py in gate.vertices],
                event_count=int(full_mask.sum()),
                percentage_parent=self._percentage(int(full_mask.sum()), parent_count),
                percentage_total=self._percentage(int(full_mask.sum()), total_count),
                full_mask=full_mask,
                x_scale=gate.x_scale,
                y_scale=gate.y_scale,
                color_hex=gate.color_hex,
            )

        if isinstance(gate, CircleGate):
            x_idx = self._resolve_channel_index(sample, gate.x_channel_index, gate.x_label)
            y_idx = self._resolve_channel_index(sample, gate.y_channel_index, gate.y_label)
            x = apply_scale(sample.events[:, x_idx], gate.x_scale)
            y = apply_scale(sample.events[:, y_idx], gate.y_scale)
            full_mask = circle_mask_from_parent(
                x,
                y,
                parent_mask,
                center_x=gate.center_x,
                center_y=gate.center_y,
                radius=gate.radius,
                radius_x=gate.radius_x,
                radius_y=gate.radius_y,
            )
            return CircleGate(
                name=gate.name,
                parent_name=gate.parent_name,
                x_channel_index=x_idx,
                y_channel_index=y_idx,
                x_label=sample.channel_label(x_idx),
                y_label=sample.channel_label(y_idx),
                center_x=gate.center_x,
                center_y=gate.center_y,
                radius=gate.radius,
                event_count=int(full_mask.sum()),
                percentage_parent=self._percentage(int(full_mask.sum()), parent_count),
                percentage_total=self._percentage(int(full_mask.sum()), total_count),
                full_mask=full_mask,
                radius_x=gate.radius_x,
                radius_y=gate.radius_y,
                x_scale=gate.x_scale,
                y_scale=gate.y_scale,
                color_hex=gate.color_hex,
            )

        x_idx = self._resolve_channel_index(sample, gate.channel_index, gate.channel_label)
        x = apply_scale(sample.events[:, x_idx], gate.x_scale)
        full_mask = range_mask_from_parent(
            x,
            parent_mask,
            x_min=gate.x_min,
            x_max=gate.x_max,
        )
        return RangeGate(
            name=gate.name,
            parent_name=gate.parent_name,
            channel_index=x_idx,
            channel_label=sample.channel_label(x_idx),
            x_min=gate.x_min,
            x_max=gate.x_max,
            event_count=int(full_mask.sum()),
            percentage_parent=self._percentage(int(full_mask.sum()), parent_count),
            percentage_total=self._percentage(int(full_mask.sum()), total_count),
            full_mask=full_mask,
            x_scale=gate.x_scale,
            color_hex=gate.color_hex,
        )

    def clone_gate_sequence_to_sample(
        self,
        gates: list[GateModel],
        sample: SampleData,
    ) -> list[GateModel]:
        cloned: list[GateModel] = []
        for gate in gates:
            cloned.append(self.clone_gate_to_sample(gate, sample, cloned))
        return cloned

    def selected_gate_sequence(
        self,
        gates: list[GateModel],
        root_names: list[str],
    ) -> list[GateModel]:
        selected_names: set[str] = set()
        for root_name in root_names:
            selected_names.update(self.gate_subtree_names(gates, root_name))
        return [gate for gate in gates if gate.name in selected_names]

    def replace_gates_on_sample(
        self,
        target_sample: WorkspaceSample,
        source_gates: list[GateModel],
    ) -> None:
        for gate in source_gates:
            self.delete_gate_subtree(target_sample.gates, gate.name)
        cloned_gates = self.clone_gate_sequence_to_sample(source_gates, target_sample.sample)
        target_sample.gates.extend(cloned_gates)
        if target_sample.active_gate_name and all(
            gate.name != target_sample.active_gate_name for gate in target_sample.gates
        ):
            target_sample.active_gate_name = None

    def upsert_gate_on_sample(self, target_sample: WorkspaceSample, gate: GateModel) -> None:
        self.delete_gate_subtree(target_sample.gates, gate.name)
        cloned_gate = self.clone_gate_to_sample(gate, target_sample.sample, target_sample.gates)
        target_sample.gates.append(cloned_gate)

    @staticmethod
    def gate_subtree_names(gates: list[GateModel], root_name: str) -> set[str]:
        names_to_delete = {root_name}
        changed = True
        while changed:
            changed = False
            for candidate in gates:
                if candidate.parent_name in names_to_delete and candidate.name not in names_to_delete:
                    names_to_delete.add(candidate.name)
                    changed = True
        return names_to_delete

    def delete_gate_subtree(self, gates: list[GateModel], root_name: str) -> None:
        names_to_delete = self.gate_subtree_names(gates, root_name)
        gates[:] = [candidate for candidate in gates if candidate.name not in names_to_delete]

    @staticmethod
    def _percentage(count: int, total: int) -> float:
        return (count / total * 100.0) if total else 0.0

    @staticmethod
    def _resolve_channel_index(sample: SampleData, preferred_index: int, expected_label: str) -> int:
        if 0 <= preferred_index < sample.channel_count and sample.channel_label(preferred_index) == expected_label:
            return preferred_index

        for index in range(sample.channel_count):
            if sample.channel_label(index) == expected_label:
                return index

        raise ValueError(f"Channel '{expected_label}' is not available in sample {sample.file_name}.")

    @staticmethod
    def _parent_mask(
        sample: SampleData,
        parent_name: str,
        existing_gates: list[GateModel],
    ) -> np.ndarray:
        if parent_name == "All events":
            return np.ones(sample.event_count, dtype=bool)

        for gate in existing_gates:
            if gate.name == parent_name:
                return gate.full_mask

        raise ValueError(f"Parent gate '{parent_name}' is not available in the target sample.")
