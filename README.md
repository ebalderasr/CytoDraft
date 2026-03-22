<div align="center">

# CytoDraft

### Desktop cytometry analysis for interactive gating, sample grouping, and export

<br>

[![Stack](https://img.shields.io/badge/Stack-Python_·_PySide6_·_pyqtgraph-4A90D9?style=for-the-badge)]()
[![Focus](https://img.shields.io/badge/Focus-Flow_Cytometry_·_Gating-34C759?style=for-the-badge)]()
[![License](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)](./LICENSE)
[![Status](https://img.shields.io/badge/Status-Desktop_MVP-5856D6?style=for-the-badge)]()

</div>

---

## What is CytoDraft?

CytoDraft is a **desktop application for flow cytometry data analysis**. It loads `.fcs` files, displays scatter plots and histograms, and lets the user define interactive gates directly on the plot.

The current MVP is focused on the core manual workflow used during exploratory cytometry analysis:

- Load one or many FCS samples into the same workspace
- Organize samples into groups such as specimens, controls, unstained, or compensation
- Create hierarchical gates interactively on scatter and histogram views
- Reuse gates across samples, across a group, or across the full workspace
- Calculate per-population statistics and export gated events

CytoDraft is meant to be fast to use at the bench or during analysis sessions, with minimal setup and a UI centered on the gating workflow rather than on pipeline scripting.

---

## Why it matters

Flow cytometry analysis often begins with repetitive manual operations:

- Opening one sample at a time and rebuilding the same gates repeatedly
- Keeping controls, unstained samples, and biological replicates organized by hand
- Comparing subpopulations visually without a quick way to propagate the same gate logic
- Exporting gated events or summary statistics through fragmented tools

CytoDraft reduces that friction by combining plotting, gating, grouping, propagation, and export in a single desktop workspace.

---

## How it works

### 1. Load and organize samples

CytoDraft reads FCS files and keeps them in a workspace. Samples can be assigned to explicit groups such as:

- `Specimen 1`
- `Specimen 2`
- `Specimen 3`
- `Controls`
- `Unstained`
- `Compensation`

Groups are first-class objects in the UI: they have color, notes, and can be used as targets for batch gate application.

### 2. Visualize populations

The app supports:

- **Scatter (2D)** plots for pairwise channel gating
- **Histogram (1D)** plots for range gating
- Linear, log10, and asinh axis scaling
- Optional display of direct subpopulations
- Overlay of gate outlines when compatible with the current view

### 3. Apply hierarchical gates

CytoDraft currently supports four gate types:

- **Rectangle**
- **Polygon**
- **Ellipse** (used as the circular/oval gate tool)
- **Range**

Gates are hierarchical. A gate can be created on `All events` or on an existing parent population, and child populations are tracked in the workspace tree.

### 4. Reuse gates across samples

Once a gate is created on one sample, it can be:

- Applied to all samples in the same group
- Applied to every loaded sample
- Propagated as a single gate or as a full gate hierarchy

When propagated, CytoDraft rebuilds the gate on the target sample using channel labels and the original gate geometry.

### 5. Quantify and export

For the selected population, CytoDraft can compute summary statistics and export:

- gated events to CSV
- gated events to FCS
- statistics tables to CSV

---

## Current feature set

| | |
|---|---|
| **Multi-sample workspace** | Load multiple FCS files into one session and switch between them without losing gates |
| **Sample grouping** | Organize samples into named groups with color and notes |
| **Batch gate propagation** | Apply one gate or an entire gate tree to a group or to all samples |
| **Interactive gating** | Draw rectangle, polygon, ellipse, and range gates directly on the plot |
| **Hierarchical populations** | Gates can be nested and browsed as parent/child populations |
| **Population overlays** | Show direct subpopulations on scatter and histogram views |
| **Gate outline overlays** | Display the gate geometry itself, not only the gated cells |
| **Statistics export** | Compute per-population statistics and export them to CSV |
| **Event export** | Export gated populations as CSV or FCS |
| **Compensation groundwork** | Default `Compensation` group with per-sample metadata for single-stain controls, target channel, and notes |

---

## Compensation roadmap

CytoDraft now includes the first structural step toward compensation:

- a default **`Compensation`** group is created automatically
- compensation samples can store metadata such as:
  - control type
  - fluorochrome
  - target channel
  - notes

This does **not** yet compute a spillover matrix. The current implementation prepares the workspace model and UI so the next phase can build:

1. a compensation setup table from that group
2. spillover matrix estimation
3. compensated vs raw visualization
4. application of the matrix to analysis samples

---

## Tech stack

**Core**

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)
![NumPy](https://img.shields.io/badge/NumPy-013243?style=flat-square&logo=numpy&logoColor=white)
![Pandas](https://img.shields.io/badge/Pandas-150458?style=flat-square&logo=pandas&logoColor=white)

**Desktop UI**

![PySide6](https://img.shields.io/badge/PySide6-41CD52?style=flat-square&logo=qt&logoColor=white)
![pyqtgraph](https://img.shields.io/badge/pyqtgraph-222222?style=flat-square&logo=plotly&logoColor=white)

**Cytometry I/O**

![FlowIO](https://img.shields.io/badge/FlowIO-FCS_IO-6C5CE7?style=flat-square)
![FlowUtils](https://img.shields.io/badge/FlowUtils-Transforms_·_Support-00A8E8?style=flat-square)

CytoDraft is a local desktop app. There is no backend, no remote service, and no browser dependency for core usage.

---

## Installation

```bash
cd /path/to/CytoDraft
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

Run the app with:

```bash
cytodraft
```

or:

```bash
python -m cytodraft.app
```

---

## Project structure

```text
CytoDraft/
├── README.md
├── pyproject.toml
├── docs/
├── examples/
├── tests/
└── src/
    └── cytodraft/
        ├── app.py                  ← application entry point
        ├── core/
        │   ├── compensation.py     ← compensation module scaffold
        │   ├── export.py           ← CSV/FCS export helpers
        │   ├── fcs_reader.py       ← FCS loading and preprocessing
        │   ├── gating.py           ← geometric mask calculations
        │   ├── statistics.py       ← population statistics
        │   └── transforms.py       ← axis scaling transforms
        ├── gui/
        │   ├── main_window.py      ← main application workflow
        │   ├── panels.py           ← left/right control panels
        │   ├── plot_widget.py      ← central plotting and ROI drawing
        │   └── theme.py            ← UI styling
        ├── models/
        │   ├── gate.py             ← gate models
        │   ├── sample.py           ← sample and channel models
        │   └── workspace.py        ← workspace, groups, compensation metadata
        └── services/
            ├── gate_service.py     ← gate propagation across samples
            └── sample_service.py   ← sample loading service
```

---

## Author

**Emiliano Balderas Ramírez**  
Bioengineer · PhD Candidate in Biochemical Sciences  
Instituto de Biotecnología (IBt), UNAM

[![LinkedIn](https://img.shields.io/badge/LinkedIn-emilianobalderas-0A66C2?style=flat-square&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/emilianobalderas/)
[![Email](https://img.shields.io/badge/Email-ebalderas%40live.com.mx-D14836?style=flat-square&logo=gmail&logoColor=white)](mailto:ebalderas@live.com.mx)

---

## Related

[**CellSplit**](https://github.com/ebalderasr/CellSplit) — Neubauer cell counting and passage planning for CHO cultures.

[**CellBlock**](https://github.com/ebalderasr/CellBlock) — shared biosafety cabinet scheduling for cell culture research groups.

[**Clonalyzer 2**](https://github.com/ebalderasr/Clonalyzer-2) — browser-based kinetics analysis for CHO fed-batch cultures.

---

<div align="center"><i>CytoDraft — load, gate, compare, export.</i></div>
