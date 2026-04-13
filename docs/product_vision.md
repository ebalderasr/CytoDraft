# CytoDraft — Product Vision

## What is CytoDraft?

CytoDraft is a local desktop application for flow cytometry data analysis. It targets cytometrists and researchers who need to inspect FCS files, define cell populations through gating, extract statistics, and export results — without depending on cloud infrastructure or expensive commercial software.

The primary audience is someone who works with cytometry data regularly, understands what a gate is, and wants a fast, reliable tool they can run entirely on their own machine.

## Core workflow

The tool is built around a single, linear workflow:

```
Load FCS files
    → Organize into groups
    → Visualize: scatter or histogram
    → Draw gates to define populations
    → Propagate gates to other samples
    → Calculate and inspect statistics
    → Export results (CSV, FCS, XLSX)
    → Save / load workspace
```

Every feature decision should ask: does this support this workflow?

## Non-goals (MVP)

- **No server or cloud sync.** Everything runs locally.
- **No FlowJo / Diva workspace import.** The workspace format is CytoDraft's own JSON.
- **No automated gating algorithms.** All gates are drawn by hand.
- **No live/streaming data.** FCS files only.
- **No publication-quality figure export.** The plot panel is for analysis, not for making figures for papers.

## Guiding principles

1. **Correctness over features.** A wrong count is worse than a missing feature.
2. **Cytometry-first UX.** Conventions should match what cytometrists already know (FSC/SSC axes, gating hierarchy, compensation controls).
3. **Self-contained.** The workspace file + the FCS files on disk = everything needed to reproduce any result.
4. **Readable code.** Another developer should be able to understand and extend any module without needing to understand the whole app.
