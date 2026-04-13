# CytoDraft — MVP Requirements and Status

This document tracks which features are required for the MVP, their current implementation state, and what remains to be done. Update this file whenever a feature is completed or its scope changes.

---

## Legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Done and working |
| 🔶 | Partially done — core logic exists, wiring or UI incomplete |
| ❌ | Not started |

---

## Feature areas

### 1. FCS file loading

| Feature | Status | Notes |
|---------|--------|-------|
| Read FCS 2.0 / 3.0 / 3.1 | ✅ | Via `flowio`. `core/fcs_reader.py`. |
| Expose channel metadata (PNN, PNS, PNR) | ✅ | `models/sample.py` `ChannelInfo`. |
| Auto-detect scatter / fluoro / time channels | ✅ | `flowio` provides `scatter_indices`, `fluoro_indices`, `time_index`. |
| Drag-and-drop FCS files onto the window | ✅ | `MainWindow.dropEvent`. |
| Multiple FCS files in one workspace | ✅ | `WorkspaceState.samples` list. |

### 2. Visualization

| Feature | Status | Notes |
|---------|--------|-------|
| Scatter plot (2D) | ✅ | `gui/plot_widget.py`, pyqtgraph. |
| Histogram (1D) | ✅ | Same widget, mode switch. |
| Linear / log10 / asinh scales per axis | ✅ | `core/transforms.py`. Scale applied before plotting. |
| Subsampling for large files | ✅ | Inspector panel sampling slider. |
| Auto-range button | ✅ | `InspectorPanel.auto_range_requested` signal. |
| Plot mode switch (scatter / histogram) | ✅ | `InspectorPanel` plot mode selector. |
| Gate overlays drawn on the plot | ✅ | `ScatterGateOverlay`, `HistogramGateOverlay`. |
| Gate overlay colors match gate color | ✅ | Color stored in `GateModel.color_hex`. |

### 3. Gating

| Feature | Status | Notes |
|---------|--------|-------|
| Rectangle gate (scatter) | ✅ | `RectangleGate`, `core/gating.py`. |
| Range gate (histogram) | ✅ | `RangeGate`. |
| Polygon gate (scatter) | ✅ | `PolygonGate`, ray-casting inside test. |
| Circle/ellipse gate (scatter) | ✅ | `CircleGate`, supports `radius_x`/`radius_y` for ellipses. |
| Gates nested inside a parent gate | ✅ | `gate.parent_name` + hierarchical mask. |
| Rename gate | ✅ | Context menu on left panel. |
| Recolor gate | ✅ | Context menu on left panel. |
| Delete gate (and its subtree) | ✅ | `GateService.delete_gate_subtree`. |
| Interactive gate editing (move / resize) | ✅ | ROI handles on the plot. `main_window.on_edit_gate`. |
| Propagate single gate to group | ✅ | `GateService.propagate_gates`. |
| Propagate all gates to all samples | ✅ | Same service, `scope="all"`. |
| Propagate selected gates to selected samples | ✅ | Batch ops in `SamplePanel`. |
| Export gate population to CSV | ✅ | `core/export.export_masked_events_to_csv`. |
| Export gate population to FCS | ✅ | `core/export.export_masked_events_to_fcs`. |

### 4. Statistics

| Feature | Status | Notes |
|---------|--------|-------|
| Event count per gate | ✅ | Stored on gate object and recalculated on demand. |
| % of parent / % of total | ✅ | `core/statistics.calculate_population_statistics`. |
| Mean, Median, Std, CV%, Min, Max, P5, P95 | ✅ | Same function, all stat keys defined in `STATISTIC_DEFINITIONS`. |
| Statistics table in Results window | ✅ | `gui/results_window.py` Statistics tab. |
| Configurable columns (group / population / channel / stat) | ✅ | `WorkspaceStatisticColumn`, managed in `SampleTableWindow`. |
| Export statistics to CSV | ✅ | `core/export.export_batch_statistics_to_csv`. |
| Export statistics to XLSX | ✅ | `results_window._write_stats_xlsx` via openpyxl. |
| Batch statistics export dialog | ✅ | `gui/batch_export_dialog.py`. |

### 5. Sample and group management

| Feature | Status | Notes |
|---------|--------|-------|
| Assign samples to groups | ✅ | Via context menu or `SampleTableWindow`. |
| Create / rename / recolor / delete groups | ✅ | `WorkspaceState.rename_group`, `delete_group`. |
| Display name override per sample | ✅ | `WorkspaceSample.display_name_override`. |
| Custom keyword columns on samples | ✅ | `WorkspaceSample.keywords`, managed in `SampleTableWindow`. |
| Multi-select samples for batch ops | ✅ | `SamplePanel` tree with Ctrl/Shift selection. |
| Collapse / expand groups in tree | ✅ | Left panel toolbar buttons. |
| "Select equivalent gates" across samples | ✅ | Button in left panel toolbar. |

### 6. Compensation

| Feature | Status | Notes |
|---------|--------|-------|
| Parse `$SPILL` / `$SPILLOVER` from FCS metadata | ✅ | `core/compensation.parse_spill_keyword`. |
| Spillover matrix editor (UI) | ✅ | `CompensationWindow._MatrixTable`. |
| Compensation controls manager (add / remove samples, set metadata) | ✅ | `CompensationWindow` main panel. |
| Scatter plot to verify compensation visually | ✅ | `CompensationWindow._ScatterPane`. |
| Spillover matrix saved in workspace file | ✅ | `WorkspaceState.spillover_channels/values`, `workspace_io.py`. |
| **Apply compensation to events before gating / plotting** | ✅ | `SampleData.compensated_events` is set by `MainWindow._recompute_all_compensation()` whenever the spillover matrix changes or samples are loaded. All plotting, gating, statistics, and export use `sample.effective_events` (compensated if available, raw otherwise). Gate masks are recomputed via `GateService.recompute_all_gate_masks()`. |

### 7. Workspace persistence

| Feature | Status | Notes |
|---------|--------|-------|
| Save workspace to `.cytodraft` (JSON) | ✅ | `core/workspace_io.save_workspace`. |
| Load workspace from `.cytodraft` | ✅ | `core/workspace_io.load_workspace`. |
| Handle missing FCS files on load | ✅ | `missing_file_handler` callback prompts user. |
| Relative + absolute paths in workspace file | ✅ | Both stored; relative tried first. |
| Gates recomputed from geometry on load (masks not stored) | ✅ | `_recompute_gates` in `workspace_io.py`. |

---

## What remains for a complete MVP

### Low priority / post-MVP

1. **Tests.** There are currently no automated tests. The `core/` layer (gating, statistics, compensation, workspace_io) is well-suited for unit tests.
2. **README / quick start guide** for new users.
3. **`interop` extra (`flowkit`)** for GatingML import/export — scaffolded in `pyproject.toml` but not implemented.
