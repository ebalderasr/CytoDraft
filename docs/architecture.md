# CytoDraft — Architecture

## Overview

CytoDraft is a single-process PySide6 desktop application. There is no server, no database, and no background threads. All data lives in a single `WorkspaceState` object that lives in `MainWindow` and is passed by reference to every subsystem that needs it.

## Layer diagram

```
┌─────────────────────────────────────────────────────────┐
│                        gui/                             │
│  MainWindow ──► SamplePanel   InspectorPanel            │
│             ──► CytometryPlotWidget  GateToolbar         │
│             ──► ResultsWindow  CompensationWindow        │
│             ──► SampleTableWindow  BatchExportDialog     │
└─────────────────┬───────────────────────────────────────┘
                  │ calls
┌─────────────────▼───────────────────────────────────────┐
│                     services/                           │
│  GateService   StatisticsService   SampleService        │
└─────────────────┬───────────────────────────────────────┘
                  │ calls
┌─────────────────▼───────────────────────────────────────┐
│                      core/                              │
│  fcs_reader   gating   statistics   compensation        │
│  transforms   export   workspace_io                     │
└─────────────────┬───────────────────────────────────────┘
                  │ uses
┌─────────────────▼───────────────────────────────────────┐
│                     models/                             │
│  SampleData   ChannelInfo   WorkspaceState              │
│  WorkspaceSample   WorkspaceGroup   GateModel           │
└─────────────────────────────────────────────────────────┘
```

**Rules enforced across the project:**
- `core/` has no Qt imports. It is fully reusable without the GUI.
- `models/` is pure data. No business logic, no Qt, no numpy operations.
- `services/` orchestrates `core/` functions and operates on `models/`. No Qt.
- `gui/` is the only layer that may import PySide6 / pyqtgraph.

## Key files and responsibilities

### `models/`

| File | What it contains |
|------|-----------------|
| `sample.py` | `SampleData` (events ndarray + channel metadata), `ChannelInfo` |
| `gate.py` | `RectangleGate`, `RangeGate`, `PolygonGate`, `CircleGate` — immutable dataclasses that each carry a `full_mask: np.ndarray` (boolean mask over all events) |
| `workspace.py` | `WorkspaceState` (root), `WorkspaceSample`, `WorkspaceGroup`, `WorkspaceStatisticColumn`, `CompensationSampleMetadata`, `CompensationPopulationSelection` |

### `core/`

| File | What it does |
|------|-------------|
| `fcs_reader.py` | Reads `.fcs` files via `flowio`. Returns `SampleData`. |
| `gating.py` | Pure numpy mask functions: `rectangle_mask`, `range_mask`, `polygon_mask`, `circle_mask`, each with a `_from_parent` variant that constrains results to an existing mask. |
| `statistics.py` | `calculate_population_statistics()` — given a values array and a boolean mask, computes the full stat list (count, %, mean, median, std, CV, min, max, P5, P95). |
| `compensation.py` | Parses `$SPILL`/`$SPILLOVER` keyword, resolves channel names to column indices, applies the spillover matrix using `flowutils.compensate`. |
| `transforms.py` | `apply_scale(arr, mode)` — applies `linear`, `log10`, or `asinh` transform to a numpy array. Used before drawing and before gate mask evaluation. |
| `export.py` | `export_masked_events_to_csv`, `export_masked_events_to_fcs`, `export_batch_statistics_to_csv`, `export_population_statistics_to_csv`. |
| `workspace_io.py` | `save_workspace` / `load_workspace` — serialises/deserialises the full `WorkspaceState` to/from a `.cytodraft` JSON file. On load, FCS files are re-read from disk and all gate masks are recomputed. |

### `services/`

| File | What it does |
|------|-------------|
| `gate_service.py` | `GateService` — propagates gates across samples. Channel matching by label with index fallback. Rebuilds masks on the target sample. Handles the full gate subtree (parents before children). |
| `statistics_service.py` | `StatisticsService` — thin wrapper around `core/statistics.py` that resolves population masks and channel indices from a `WorkspaceSample`. |
| `sample_service.py` | Minimal helpers for loading and naming samples. |

### `gui/`

| File | What it does |
|------|-------------|
| `main_window.py` | `MainWindow` — central orchestrator (~2870 lines). Owns `WorkspaceState`, all services, and all sub-windows. Handles all user interactions: loading FCS files, drawing/editing/propagating gates, exporting, workspace save/load. |
| `panels.py` | `SamplePanel` (left tree: samples grouped, with gates as children) and `InspectorPanel` (right: axis selectors, scale, statistics tab). |
| `plot_widget.py` | `CytometryPlotWidget` — scatter and histogram plots via pyqtgraph. Draws gate overlays (ROIs). Handles interactive gate drawing and editing (move/resize). |
| `gate_toolbar.py` | `GateToolbar` — button bar above the plot for gate type selection, draw, apply, clear. |
| `gate_tools.py` | ROI helper objects used by `plot_widget.py` for interactive drawing. |
| `results_window.py` | `ResultsWindow` — modal-less dialog with two tabs: **Statistics** (configurable table across samples/groups) and **Events** (event export per population). Exports to CSV and XLSX. |
| `compensation_dialog.py` | `CompensationWindow` — manages compensation controls: lists single-stain / FMO / bead samples, exposes spillover matrix editor, shows a live scatter pane to verify compensation visually. |
| `sample_table_window.py` | `SampleTableWindow` — full sample manager: rename, group assign, keyword columns, statistic columns, bulk operations. |
| `batch_export_dialog.py` | `BatchExportDialog` — selects groups, populations, channels, and statistics for a batch CSV export. |
| `theme.py` | Application-wide stylesheet constants. |

## Central data flow

```
FCS file on disk
    │  read_fcs()
    ▼
SampleData  ──────────────────────────────────────────┐
    │                                                  │
    │ added to                                         │
    ▼                                                  │
WorkspaceSample.sample                                 │
WorkspaceSample.gates ◄── gate masks computed here     │
    │                    (gating.py + transforms.py)   │
    │                                                  │
    ▼                                                  │
WorkspaceState  (the single source of truth)           │
    │                                                  │
    ├──► gui/plot_widget.py  (renders events + gates)  │
    ├──► gui/panels.py       (shows tree)              │
    ├──► gui/results_window.py (stats + export)        │
    ├──► gui/compensation_dialog.py                    │
    └──► core/workspace_io.py (save to .cytodraft)─────┘
                                 (load: re-reads FCS
                                  and recomputes masks)
```

## Gate hierarchy model

Gates form a tree rooted at the virtual node **"All events"**. Each gate stores:
- `parent_name` — name of the parent gate (or `"All events"`)
- `full_mask` — boolean array of length `sample.event_count`, `True` for events that fall inside this gate **and** inside all ancestors

The `full_mask` is always absolute (relative to the full sample), not relative to the parent. This means statistics can be computed with a single array index, and parent-relative percentages only require knowing the parent's `full_mask.sum()`.

When propagating a gate to another sample (`GateService.propagate_gates`), the sequence is topologically sorted so parents are always cloned before their children.

## Compensation

The spillover matrix is stored in `WorkspaceState.spillover_channels` / `spillover_values`.

`SampleData` carries two event arrays:
- `events` — raw values, never modified after loading
- `compensated_events` — set by `MainWindow._recompute_all_compensation()`, or `None` when no matrix is active
- `effective_events` (property) — returns `compensated_events` if set, else `events`

All plotting, gate evaluation, statistics, and export use `sample.effective_events`. Raw values are always preserved in `sample.events` so compensation can be toggled without reloading FCS files.

`_recompute_all_compensation()` is called in three situations:
1. After new FCS files are loaded (`load_samples`)
2. After a workspace is loaded from disk (`_apply_loaded_workspace`)
3. After the user edits the spillover matrix in `CompensationWindow` (`_on_compensation_workspace_changed`)

After updating `compensated_events`, it also calls `GateService.recompute_all_gate_masks()` for each sample so that gate masks reflect the current `effective_events`.

## Workspace file format

`.cytodraft` files are UTF-8 JSON. Format version is `"1"`. The file stores:
- Groups (name, color, notes)
- Statistic and keyword column definitions
- Spillover matrix
- Per-sample: file path (absolute + relative), group, display name override, gates (geometry only — masks are recomputed on load), compensation metadata, keyword values

FCS files are not embedded in the workspace file; they must remain accessible on disk at the stored paths.

## Scales

Three scale modes are supported: `linear`, `log10`, `asinh`. The scale is applied **before** plotting and **before** gate mask evaluation — gates store raw boundary values in the transformed space. This means a log10 gate boundary of `3.0` corresponds to `10^3 = 1000` in raw fluorescence units.
