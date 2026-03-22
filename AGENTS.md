# CytoDraft repository instructions

## Mission
CytoDraft is a local desktop application for cytometry data analysis.
The first milestone is a robust MVP that can:
- open FCS files
- inspect channel metadata
- visualize 1D/2D distributions
- apply basic transforms
- create rectangle and polygon gates
- compute counts and percentages
- export gated populations
- save/load workspaces in JSON

## Architecture rules
- Keep scientific logic out of Qt widgets.
- Put domain logic in `src/cytodraft/core/`.
- Put UI code in `src/cytodraft/gui/`.
- Put thin orchestration code in `src/cytodraft/services/`.
- Keep models/data structures in `src/cytodraft/models/`.
- The core must be reusable without the GUI.

## Coding rules
- Use Python 3.11+.
- Prefer small, reviewable changes.
- Add type hints in new or modified public functions.
- Avoid premature abstraction.
- Do not add heavy dependencies unless justified.
- Do not silently change file formats or public APIs.

## Testing rules
- Add or update tests for core logic changes.
- Prefer unit tests for transforms, gating, and FCS parsing behavior.
- Keep GUI tests light unless necessary.

## Product rules
- Prioritize correctness and clarity over flashy UI.
- Optimize for real cytometry workflows, not generic dashboards.
- Avoid implementing advanced FlowJo compatibility in the MVP.
- Prefer JSON workspace first; interoperability can come later.

## Safe workflow
- Before major edits, inspect the relevant files.
- When a task is large, propose a short plan in the response.
- Mention tradeoffs when introducing new dependencies or formats.
