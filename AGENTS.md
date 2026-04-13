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

## Documentation maintenance (MANDATORY)

The `docs/` folder is the single source of truth for any developer or AI agent picking up this project. Every non-trivial code change must be reflected in the relevant doc file in the same commit or PR. Specifically:

| What changed | Which doc to update |
|---|---|
| New module, renamed file, or changed layering | `docs/architecture.md` |
| New feature started, completed, or scoped out | `docs/requirements_mvp.md` (update the status symbol and notes) |
| UI layout, new window, or changed interaction | `docs/ux_notes.md` |
| Change to product scope or goals | `docs/product_vision.md` |

**The compensation feature** (`requirements_mvp.md` line marked 🔶) is the main pending item. When it is wired in, update the status to ✅ and remove the "What remains for a complete MVP" entry for it.

Do not leave docs stale. A doc that describes old behavior is worse than no doc.

## Safe workflow
- Before major edits, inspect the relevant files.
- When a task is large, propose a short plan in the response.
- Mention tradeoffs when introducing new dependencies or formats.
