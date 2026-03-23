"""Fluorescence spillover / compensation utilities.

Math is delegated to ``flowutils.compensate`` (already a project dependency).
This module handles:
- Parsing the ``$SPILL`` / ``$SPILLOVER`` FCS keyword into structured data.
- Mapping spillover channel names to sample channel indices.
- Applying the resulting matrix to a raw event array.
"""

from __future__ import annotations

import numpy as np
from flowutils import compensate as _fu_compensate

from cytodraft.models.sample import SampleData


# ── Spillover keyword parsing ──────────────────────────────────────────────────

def parse_spill_keyword(spill_str: str) -> tuple[list[str], np.ndarray] | None:
    """Parse an FCS ``$SPILL`` / ``$SPILLOVER`` string.

    Format: ``n,c1,c2,...,cn,v11,v12,...,vnn``
    where *n* is the number of channels, *c1..cn* are channel names and
    *v11..vnn* are the matrix values in row-major order.

    Returns ``(channel_names, matrix)`` or *None* if the string is missing /
    malformed.
    """
    if not spill_str:
        return None

    parts = [p.strip() for p in spill_str.split(",")]
    try:
        n = int(parts[0])
    except (ValueError, IndexError):
        return None

    if n <= 0:
        return None

    expected = 1 + n + n * n
    if len(parts) < expected:
        return None

    channel_names = parts[1 : 1 + n]
    try:
        values = [float(v) for v in parts[1 + n : expected]]
    except ValueError:
        return None

    matrix = np.array(values, dtype=float).reshape(n, n)
    return channel_names, matrix


def extract_spillover(metadata: dict[str, str]) -> tuple[list[str], np.ndarray] | None:
    """Try all common FCS keyword variants and return the first valid spillover."""
    for key in ("$SPILL", "$SPILLOVER", "SPILL", "SPILLOVER"):
        val = metadata.get(key, "").strip()
        if val and val != "0":
            result = parse_spill_keyword(val)
            if result is not None:
                return result
    return None


# ── Channel index resolution ───────────────────────────────────────────────────

def resolve_fluoro_indices(
    spill_channels: list[str],
    sample: SampleData,
) -> list[int] | None:
    """Map spillover channel names to zero-based column indices in *sample.events*.

    Matching is case-insensitive and falls back to PNN (detector name) when PNS
    (fluorochrome label) does not match.

    Returns a list of indices in the same order as *spill_channels*, or *None*
    if any channel cannot be resolved.
    """
    name_to_index: dict[str, int] = {}
    for ch in sample.channels:
        for label in (ch.pnn.strip(), ch.pns.strip()):
            if label:
                name_to_index[label.lower()] = ch.index

    indices: list[int] = []
    for name in spill_channels:
        idx = name_to_index.get(name.strip().lower())
        if idx is None:
            return None
        indices.append(idx)

    return indices


# ── Compensation application ───────────────────────────────────────────────────

def apply_compensation(
    events: np.ndarray,
    spill_matrix: np.ndarray,
    fluoro_indices: list[int],
) -> np.ndarray:
    """Return a compensated copy of *events*.

    Uses ``flowutils.compensate.compensate`` which computes::

        compensated_fluoro = raw_fluoro @ inv(spill_matrix)

    Non-fluorescence columns are returned unchanged.
    """
    return _fu_compensate.compensate(events, spill_matrix, fluoro_indices)


def apply_compensation_to_sample(
    sample: SampleData,
    spill_channels: list[str],
    spill_matrix: np.ndarray,
) -> np.ndarray | None:
    """Convenience wrapper: resolve indices then compensate.

    Returns the compensated event array or *None* if channel mapping fails.
    """
    indices = resolve_fluoro_indices(spill_channels, sample)
    if indices is None:
        return None
    return apply_compensation(sample.events, spill_matrix, indices)


# ── Spillover matrix serialisation helpers ─────────────────────────────────────

def matrix_to_flat(matrix: np.ndarray) -> list[float]:
    """Flatten an n×n ndarray to a plain Python list (row-major)."""
    return matrix.flatten().tolist()


def flat_to_matrix(values: list[float], n: int) -> np.ndarray:
    """Reconstruct an n×n ndarray from a flat row-major list."""
    return np.array(values, dtype=float).reshape(n, n)
