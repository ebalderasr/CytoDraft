"""workspace_io.py — save and load a complete CytoDraft workspace.

No Qt imports are allowed here; this is pure logic.
"""

from __future__ import annotations

import json
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np

from cytodraft.core.fcs_reader import read_fcs
from cytodraft.core.gating import (
    circle_mask_from_parent,
    polygon_mask_from_parent,
    range_mask_from_parent,
    rectangle_mask_from_parent,
)
from cytodraft.core.transforms import apply_scale
from cytodraft.models.gate import (
    CircleGate,
    DEFAULT_GATE_COLOR,
    PolygonGate,
    RangeGate,
    RectangleGate,
)
from cytodraft.models.workspace import (
    COMPENSATION_GROUP_COLOR,
    COMPENSATION_GROUP_NAME,
    COMPENSATION_GROUP_NOTES,
    CompensationPopulationSelection,
    CompensationSampleMetadata,
    DEFAULT_GROUP_COLOR,
    WorkspaceGroup,
    WorkspaceSample,
    WorkspaceState,
    WorkspaceStatisticColumn,
)

WORKSPACE_EXTENSION = ".cytodraft"
_FORMAT_VERSION = "1"


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------


def _gate_to_dict(gate: RectangleGate | RangeGate | PolygonGate | CircleGate) -> dict:
    common = {
        "name": gate.name,
        "parent_name": gate.parent_name,
        "color_hex": gate.color_hex,
        "event_count": gate.event_count,
        "percentage_parent": gate.percentage_parent,
        "percentage_total": gate.percentage_total,
    }
    if isinstance(gate, RectangleGate):
        return {
            **common,
            "type": "rectangle",
            "x_channel_index": gate.x_channel_index,
            "y_channel_index": gate.y_channel_index,
            "x_label": gate.x_label,
            "y_label": gate.y_label,
            "x_min": gate.x_min,
            "x_max": gate.x_max,
            "y_min": gate.y_min,
            "y_max": gate.y_max,
            "x_scale": gate.x_scale,
            "y_scale": gate.y_scale,
        }
    if isinstance(gate, RangeGate):
        return {
            **common,
            "type": "range",
            "channel_index": gate.channel_index,
            "channel_label": gate.channel_label,
            "x_min": gate.x_min,
            "x_max": gate.x_max,
            "x_scale": gate.x_scale,
        }
    if isinstance(gate, PolygonGate):
        return {
            **common,
            "type": "polygon",
            "x_channel_index": gate.x_channel_index,
            "y_channel_index": gate.y_channel_index,
            "x_label": gate.x_label,
            "y_label": gate.y_label,
            "vertices": [list(v) for v in gate.vertices],
            "x_scale": gate.x_scale,
            "y_scale": gate.y_scale,
        }
    if isinstance(gate, CircleGate):
        return {
            **common,
            "type": "circle",
            "x_channel_index": gate.x_channel_index,
            "y_channel_index": gate.y_channel_index,
            "x_label": gate.x_label,
            "y_label": gate.y_label,
            "center_x": gate.center_x,
            "center_y": gate.center_y,
            "radius": gate.radius,
            "radius_x": gate.radius_x,
            "radius_y": gate.radius_y,
            "x_scale": gate.x_scale,
            "y_scale": gate.y_scale,
        }
    raise TypeError(f"Unknown gate type: {type(gate)}")


def _sample_to_dict(ws: WorkspaceSample, workspace_dir: Path) -> dict:
    abs_path = str(ws.sample.file_path.resolve())
    try:
        rel_path = str(ws.sample.file_path.resolve().relative_to(workspace_dir))
    except ValueError:
        rel_path = abs_path

    comp = ws.compensation
    comp_pos = ws.compensation_positive
    comp_neg = ws.compensation_negative

    return {
        "file_path": abs_path,
        "file_path_relative": rel_path,
        "group_name": ws.group_name,
        "display_name_override": ws.display_name_override,
        "active_gate_name": ws.active_gate_name,
        "keywords": dict(ws.keywords),
        "use_universal_negative": ws.use_universal_negative,
        "compensation": {
            "control_type": comp.control_type,
            "fluorochrome": comp.fluorochrome,
            "target_channel": comp.target_channel,
            "notes": comp.notes,
        },
        "compensation_positive": {
            "sample_index": comp_pos.sample_index,
            "population_name": comp_pos.population_name,
        },
        "compensation_negative": {
            "sample_index": comp_neg.sample_index,
            "population_name": comp_neg.population_name,
        },
        "gates": [_gate_to_dict(g) for g in ws.gates],
    }


def save_workspace(workspace: WorkspaceState, path: Path) -> None:
    """Serialise *workspace* to *path* as JSON."""
    workspace_dir = path.parent.resolve()

    doc: dict = {
        "version": _FORMAT_VERSION,
        "saved_at": datetime.now(tz=timezone.utc).isoformat(),
        "active_sample_index": workspace.active_sample_index,
        "universal_negative_sample_index": workspace.universal_negative_sample_index,
        "keyword_columns": list(workspace.keyword_columns),
        "spillover_channels": list(workspace.spillover_channels),
        "spillover_values": list(workspace.spillover_values),
        "statistic_columns": [
            {
                "statistic_key": col.statistic_key,
                "statistic_label": col.statistic_label,
                "population_name": col.population_name,
                "channel_name": col.channel_name,
                "group_name": col.group_name,
            }
            for col in workspace.statistic_columns
        ],
        "groups": {
            name: {
                "name": grp.name,
                "color_hex": grp.color_hex,
                "notes": grp.notes,
            }
            for name, grp in workspace.groups.items()
        },
        "samples": [_sample_to_dict(ws, workspace_dir) for ws in workspace.samples],
    }

    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


def _topo_sort_gates(gate_dicts: list[dict]) -> list[dict]:
    """Topological sort so parents always come before children (Kahn's algorithm)."""
    names = {g["name"] for g in gate_dicts}
    in_degree: dict[str, int] = {g["name"]: 0 for g in gate_dicts}
    children: dict[str, list[str]] = {g["name"]: [] for g in gate_dicts}

    for g in gate_dicts:
        parent = g.get("parent_name", "All events")
        if parent in names:
            in_degree[g["name"]] += 1
            children[parent].append(g["name"])

    by_name = {g["name"]: g for g in gate_dicts}
    queue: deque[str] = deque(name for name, deg in in_degree.items() if deg == 0)
    result: list[dict] = []

    while queue:
        name = queue.popleft()
        result.append(by_name[name])
        for child in children[name]:
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)

    # Append any remaining (cyclic or unreachable) gates at the end
    added = {g["name"] for g in result}
    for g in gate_dicts:
        if g["name"] not in added:
            result.append(g)

    return result


def _recompute_gates(
    gate_dicts: list[dict],
    events: np.ndarray,
) -> list[RectangleGate | RangeGate | PolygonGate | CircleGate]:
    """Rebuild gate objects with correct full_mask from raw events."""
    n = events.shape[0]
    population_masks: dict[str, np.ndarray] = {"All events": np.ones(n, dtype=bool)}
    sorted_dicts = _topo_sort_gates(gate_dicts)
    gates: list[RectangleGate | RangeGate | PolygonGate | CircleGate] = []

    for gd in sorted_dicts:
        parent_name = gd.get("parent_name", "All events")
        parent_mask = population_masks.get(parent_name, np.ones(n, dtype=bool))
        total_events = int(np.sum(population_masks["All events"]))
        parent_events = int(np.sum(parent_mask))

        gate_type = gd["type"]
        gate_name = gd["name"]
        color = gd.get("color_hex", DEFAULT_GATE_COLOR)

        if gate_type == "rectangle":
            x_idx: int = gd["x_channel_index"]
            y_idx: int = gd["y_channel_index"]
            x_scale: str = gd.get("x_scale", "linear")
            y_scale: str = gd.get("y_scale", "linear")
            x_vals = apply_scale(events[:, x_idx], x_scale)
            y_vals = apply_scale(events[:, y_idx], y_scale)
            full_mask = rectangle_mask_from_parent(
                x_vals,
                y_vals,
                parent_mask,
                x_min=gd["x_min"],
                x_max=gd["x_max"],
                y_min=gd["y_min"],
                y_max=gd["y_max"],
            )
            count = int(np.sum(full_mask))
            gate: RectangleGate | RangeGate | PolygonGate | CircleGate = RectangleGate(
                name=gate_name,
                parent_name=parent_name,
                x_channel_index=x_idx,
                y_channel_index=y_idx,
                x_label=gd.get("x_label", ""),
                y_label=gd.get("y_label", ""),
                x_min=gd["x_min"],
                x_max=gd["x_max"],
                y_min=gd["y_min"],
                y_max=gd["y_max"],
                event_count=count,
                percentage_parent=100.0 * count / parent_events if parent_events else 0.0,
                percentage_total=100.0 * count / total_events if total_events else 0.0,
                full_mask=full_mask,
                x_scale=x_scale,
                y_scale=y_scale,
                color_hex=color,
            )

        elif gate_type == "range":
            ch_idx: int = gd["channel_index"]
            x_scale = gd.get("x_scale", "linear")
            x_vals = apply_scale(events[:, ch_idx], x_scale)
            full_mask = range_mask_from_parent(
                x_vals,
                parent_mask,
                x_min=gd["x_min"],
                x_max=gd["x_max"],
            )
            count = int(np.sum(full_mask))
            gate = RangeGate(
                name=gate_name,
                parent_name=parent_name,
                channel_index=ch_idx,
                channel_label=gd.get("channel_label", ""),
                x_min=gd["x_min"],
                x_max=gd["x_max"],
                event_count=count,
                percentage_parent=100.0 * count / parent_events if parent_events else 0.0,
                percentage_total=100.0 * count / total_events if total_events else 0.0,
                full_mask=full_mask,
                x_scale=x_scale,
                color_hex=color,
            )

        elif gate_type == "polygon":
            x_idx = gd["x_channel_index"]
            y_idx = gd["y_channel_index"]
            x_scale = gd.get("x_scale", "linear")
            y_scale = gd.get("y_scale", "linear")
            x_vals = apply_scale(events[:, x_idx], x_scale)
            y_vals = apply_scale(events[:, y_idx], y_scale)
            raw_verts = gd.get("vertices", [])
            vertices: list[tuple[float, float]] = [
                (float(v[0]), float(v[1])) for v in raw_verts
            ]
            full_mask = polygon_mask_from_parent(
                x_vals,
                y_vals,
                parent_mask,
                vertices,
            )
            count = int(np.sum(full_mask))
            gate = PolygonGate(
                name=gate_name,
                parent_name=parent_name,
                x_channel_index=x_idx,
                y_channel_index=y_idx,
                x_label=gd.get("x_label", ""),
                y_label=gd.get("y_label", ""),
                vertices=vertices,
                event_count=count,
                percentage_parent=100.0 * count / parent_events if parent_events else 0.0,
                percentage_total=100.0 * count / total_events if total_events else 0.0,
                full_mask=full_mask,
                x_scale=x_scale,
                y_scale=y_scale,
                color_hex=color,
            )

        elif gate_type == "circle":
            x_idx = gd["x_channel_index"]
            y_idx = gd["y_channel_index"]
            x_scale = gd.get("x_scale", "linear")
            y_scale = gd.get("y_scale", "linear")
            x_vals = apply_scale(events[:, x_idx], x_scale)
            y_vals = apply_scale(events[:, y_idx], y_scale)
            full_mask = circle_mask_from_parent(
                x_vals,
                y_vals,
                parent_mask,
                center_x=gd["center_x"],
                center_y=gd["center_y"],
                radius=gd.get("radius"),
                radius_x=gd.get("radius_x"),
                radius_y=gd.get("radius_y"),
            )
            count = int(np.sum(full_mask))
            gate = CircleGate(
                name=gate_name,
                parent_name=parent_name,
                x_channel_index=x_idx,
                y_channel_index=y_idx,
                x_label=gd.get("x_label", ""),
                y_label=gd.get("y_label", ""),
                center_x=gd["center_x"],
                center_y=gd["center_y"],
                radius=gd.get("radius", 0.0),
                event_count=count,
                percentage_parent=100.0 * count / parent_events if parent_events else 0.0,
                percentage_total=100.0 * count / total_events if total_events else 0.0,
                full_mask=full_mask,
                radius_x=gd.get("radius_x"),
                radius_y=gd.get("radius_y"),
                x_scale=x_scale,
                y_scale=y_scale,
                color_hex=color,
            )

        else:
            # Unknown gate type — skip
            continue

        population_masks[gate_name] = full_mask
        gates.append(gate)

    return gates


def load_workspace(
    path: Path,
    *,
    missing_file_handler: Callable[[str], Path | None] | None = None,
) -> tuple[WorkspaceState, list[str]]:
    """Deserialise a workspace from *path*.

    Returns ``(workspace, warnings)`` where *warnings* is a list of non-fatal
    problem strings.  Raises on fatal errors (bad JSON, unsupported version).
    """
    raw = path.read_text(encoding="utf-8")
    doc: dict = json.loads(raw)

    version = doc.get("version", "")
    if version != _FORMAT_VERSION:
        raise ValueError(
            f"Unsupported workspace version '{version}'. "
            f"Expected '{_FORMAT_VERSION}'."
        )

    workspace_dir = path.parent.resolve()
    warnings: list[str] = []

    # ---- Rebuild WorkspaceState shell ----
    workspace = WorkspaceState()

    # Groups
    for grp_data in doc.get("groups", {}).values():
        name = grp_data["name"]
        grp = workspace.ensure_group(name)
        grp.color_hex = grp_data.get("color_hex", DEFAULT_GROUP_COLOR)
        grp.notes = grp_data.get("notes", "")

    # Statistic columns
    for col_data in doc.get("statistic_columns", []):
        workspace.add_statistic_column(
            WorkspaceStatisticColumn(
                statistic_key=col_data["statistic_key"],
                statistic_label=col_data["statistic_label"],
                population_name=col_data["population_name"],
                channel_name=col_data["channel_name"],
                group_name=col_data.get("group_name"),
            )
        )

    # Keyword columns
    for kw in doc.get("keyword_columns", []):
        workspace.add_keyword_column(kw)

    # Spillover / compensation matrix
    spill_channels = doc.get("spillover_channels", [])
    spill_values = doc.get("spillover_values", [])
    if spill_channels and len(spill_values) == len(spill_channels) ** 2:
        workspace.set_spillover(spill_channels, spill_values)

    # ---- Load samples ----
    original_to_loaded: dict[int, int] = {}
    loaded_index = 0

    for original_index, sd in enumerate(doc.get("samples", [])):
        abs_path_str: str = sd.get("file_path", "")
        rel_path_str: str = sd.get("file_path_relative", "")

        # Resolve FCS file
        fcs_path: Path | None = None
        candidates = []
        if abs_path_str:
            candidates.append(Path(abs_path_str))
        if rel_path_str:
            candidates.append(workspace_dir / rel_path_str)

        for candidate in candidates:
            if candidate.is_file():
                fcs_path = candidate
                break

        if fcs_path is None:
            original = abs_path_str or rel_path_str
            if missing_file_handler is not None:
                fcs_path = missing_file_handler(original)
            if fcs_path is None:
                warnings.append(
                    f"Sample skipped — file not found: {original}"
                )
                continue

        # Read FCS
        try:
            sample_data = read_fcs(fcs_path)
        except Exception as exc:
            warnings.append(
                f"Sample skipped — could not read '{fcs_path}': {exc}"
            )
            continue

        # Recompute gates
        gate_dicts: list[dict] = sd.get("gates", [])
        try:
            gates = _recompute_gates(gate_dicts, sample_data.events)
        except Exception as exc:
            warnings.append(
                f"Gates could not be recomputed for '{fcs_path.name}': {exc}"
            )
            gates = []

        # Build compensation metadata
        comp_raw = sd.get("compensation", {})
        comp = CompensationSampleMetadata(
            control_type=comp_raw.get("control_type", "single_stain"),
            fluorochrome=comp_raw.get("fluorochrome", ""),
            target_channel=comp_raw.get("target_channel", ""),
            notes=comp_raw.get("notes", ""),
        )

        comp_pos_raw = sd.get("compensation_positive", {})
        comp_neg_raw = sd.get("compensation_negative", {})
        comp_pos = CompensationPopulationSelection(
            sample_index=comp_pos_raw.get("sample_index"),
            population_name=comp_pos_raw.get("population_name", ""),
        )
        comp_neg = CompensationPopulationSelection(
            sample_index=comp_neg_raw.get("sample_index"),
            population_name=comp_neg_raw.get("population_name", ""),
        )

        ws_sample = WorkspaceSample(
            sample=sample_data,
            group_name=sd.get("group_name", "Ungrouped"),
            gates=gates,
            active_gate_name=sd.get("active_gate_name"),
            display_name_override=sd.get("display_name_override"),
            compensation=comp,
            compensation_positive=comp_pos,
            compensation_negative=comp_neg,
            use_universal_negative=sd.get("use_universal_negative", False),
            keywords=dict(sd.get("keywords", {})),
        )

        workspace.samples.append(ws_sample)
        workspace.ensure_group(ws_sample.group_name)
        original_to_loaded[original_index] = loaded_index
        loaded_index += 1

    # ---- Remap indices ----
    saved_active: int | None = doc.get("active_sample_index")
    if saved_active is not None:
        workspace.active_sample_index = original_to_loaded.get(saved_active)
    else:
        workspace.active_sample_index = None

    if not workspace.samples:
        workspace.active_sample_index = None

    saved_universal: int | None = doc.get("universal_negative_sample_index")
    if saved_universal is not None:
        workspace.universal_negative_sample_index = original_to_loaded.get(saved_universal)
    else:
        workspace.universal_negative_sample_index = None

    # Remap compensation cross-references
    for ws_sample in workspace.samples:
        for sel in (ws_sample.compensation_positive, ws_sample.compensation_negative):
            if sel.sample_index is not None:
                remapped = original_to_loaded.get(sel.sample_index)
                if remapped is None:
                    sel.sample_index = None
                    sel.population_name = ""
                    warnings.append(
                        "A compensation cross-reference pointed to a sample that "
                        "could not be loaded and has been cleared."
                    )
                else:
                    sel.sample_index = remapped

    return workspace, warnings
