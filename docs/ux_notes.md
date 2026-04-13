# CytoDraft — UX Notes

This document describes the UI layout, the key interaction patterns, and design decisions that are not obvious from the code. Update it when the UI changes significantly.

---

## Main window layout

```
┌─────────────────────────────────────────────────────────────────────┐
│ Menu: File | View | Help                                            │
│ Toolbar: [Sample Manager] [Compensation] [Results]                  │
├─────────────────┬───────────────────────────────┬───────────────────┤
│  SamplePanel    │  GateToolbar                  │  InspectorPanel   │
│  (left)         │  [Draw] [Apply] [Clear]        │  (right)          │
│                 ├───────────────────────────────┤                   │
│  Tree:          │                               │  Axes:            │
│  ▼ Group A      │   CytometryPlotWidget         │   X-axis ▼        │
│    ○ sample1    │   (scatter or histogram)      │   Y-axis ▼        │
│      ○ Gate1    │                               │   X-scale ▼       │
│      ○ Gate2    │                               │   Y-scale ▼       │
│  ▼ Group B      │                               │   Sampling ─┤     │
│    ○ sample2    │                               │   [Auto range]    │
│                 │                               │                   │
│  Toolbar:       │                               │  Statistics:      │
│  [+][-][⋮]      │                               │   Population ▼    │
│                 │                               │   Channel ▼       │
│                 │                               │   [Calculate]     │
│                 │                               │   [Export]        │
└─────────────────┴───────────────────────────────┴───────────────────┘
│ Status bar                                                          │
└─────────────────────────────────────────────────────────────────────┘
```

The three panels are in a `QSplitter` (horizontal). Proportions: left 340 / center 700 / right 340 (initial, user-resizable).

---

## Left panel (`SamplePanel`)

### Tree structure

Each sample is a top-level tree item under its group header. Gates are children of the sample. Clicking a sample selects it and loads it into the plot. Clicking a gate sets it as the active gate for the plot context.

Group headers are not selectable — they are visual separators.

### Toolbar buttons

- `+` — Add FCS files
- `-` — Remove selected samples
- `⋮` — More options (context-dependent): rename, recolor group, delete group, propagate gates, batch operations

The toolbar also has:
- **Collapse all** / **Expand all** buttons
- **Select equivalent gates** — selects the gate with the same name across all visible samples (useful for batch propagation)

### Multi-select

Ctrl+click and Shift+click for multi-selection. When multiple items are selected, the toolbar and context menu show batch operations (delete samples, assign group, propagate gates).

### Context menu (right-click on sample)

- Rename sample
- Assign to group (submenu of existing groups + "New group…")
- Edit compensation metadata (only shown for Compensation group samples)
- Add keyword
- Apply active gate to group / all
- Apply all gates to group / all
- Export active gate

### Context menu (right-click on gate)

- Rename
- Recolor
- Edit (opens gate for interactive reshape on plot)
- Export gate population
- Delete gate (and children)

---

## Center panel (plot)

### Gate drawing workflow

1. User selects gate type in `GateToolbar` (rectangle, range, polygon, circle)
2. Clicks **Draw** — the plot enters drawing mode
3. User draws the ROI on the plot
4. Clicks **Apply** — the gate is computed and added to the active sample
5. A name dialog appears; user names the gate
6. Gate appears in the left panel tree under the current sample

**Parent gate**: the currently selected gate in the left panel becomes the parent. If nothing is selected, the parent is "All events".

### Gate editing workflow

Right-click a gate in the left panel → Edit. The gate's ROI becomes interactive on the plot (handles visible). The user reshapes it and clicks **Apply** to update.

### Right-click on plot

Right-clicking inside an existing gate on the plot opens a context menu with: rename, recolor, edit, export, delete — same actions as the left panel context menu.

---

## Auxiliary windows

### Sample Manager (`Ctrl+T`)

A separate window with a table of all samples. Columns include group, display name, and any configured keyword or statistic columns. From here the user can:
- Add / remove columns (keywords, statistics)
- Bulk rename, regroup, or delete samples
- Add more FCS files to a specific group

### Compensation (`Ctrl+M`)

A separate window with three tabs for managing the spillover matrix:

**Tab 1 — Controls**: list of compensation control samples (single-stain, FMO, beads, unstained). Each row shows the sample name and editable metadata: target channel, control type, and notes.

**Tab 2 — Matrix**: spillover matrix table (editable off-diagonal cells; diagonal always 100). Columns are source fluorochromes, rows are detector channels. Values are percentage spillover. Changing a value immediately updates the pairwise scatter grid in tab 3.

**Tab 3 — Pairwise scatter**: an N×N grid of scatter plots, one per channel pair (class `_PairScatterGrid`). For N spillover channels (capped at 10):
- Column c = source fluorochrome on X axis
- Row r = detector channel on Y axis
- Diagonal cells show the channel name only (X vs. itself is meaningless)
- Off-diagonal cells show: raw events in gray (optional, toggled by "Show raw" checkbox) and compensated events in blue
- Labels appear only on the left column (Y-axis name) and bottom row (X-axis name) to reduce clutter
- Subsampled to ≤ 4 000 points per cell for performance
- Updates live as the user edits matrix values: only scatter point data is refreshed (no widget rebuild), so the UI stays responsive

The scatter grid visualizes the classic compensation diagnostic: in an uncompensated sample the off-diagonal cloud is tilted (spillover tail); after correct compensation it collapses to a vertical/horizontal axis-aligned cluster with no diagonal tilt.

Changes to the matrix are saved into `WorkspaceState` and immediately applied to all samples in the workspace (compensated events are recomputed and gate masks are refreshed).

### Results (`Ctrl+R`)

A separate window with two tabs:

**Statistics tab**: configurable table. Rows are samples; columns are user-defined (group, population, channel, statistic). Multiple columns can be added. Supports CSV and XLSX export.

**Events tab**: select a group, sample, and population to export the raw event data as CSV or FCS.

---

## Design decisions

### Why gates store `full_mask` instead of computing it lazily

Mask computation (especially for polygon gates with many events) is not free. Storing it pre-computed means the plot, statistics, and export all read the same array without re-running the ray-casting algorithm. Masks are recomputed when:
- A gate is created or edited
- A workspace is loaded from disk
- A gate is propagated to a new sample

### Why scales are applied before gate evaluation

The user draws a gate on the **visual** representation of the data (e.g., log10 scale). The gate boundaries are stored in **transformed** coordinates. When evaluating the mask, the same transform is applied to the raw event values before checking whether each event falls inside the gate. This means the raw FCS values are never modified; the transform is always applied on-the-fly.

### Why `WorkspaceState` is mutable and shared

The alternative (immutable state + rebuild on every change) would require deep-copying large numpy arrays on every gate draw or rename. For the data sizes typical in cytometry (10k–500k events, 20–40 channels), mutable shared state is the practical choice. The trade-off is that `MainWindow` must explicitly call `_refresh_*` methods to keep the UI in sync after mutations.
