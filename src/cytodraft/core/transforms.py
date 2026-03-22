from __future__ import annotations

from typing import Literal

import numpy as np

ScaleMode = Literal["linear", "log10", "asinh"]


def apply_scale(values: np.ndarray, mode: ScaleMode) -> np.ndarray:
    arr = np.asarray(values, dtype=float)

    if mode == "linear":
        return arr

    if mode == "log10":
        out = np.full(arr.shape, np.nan, dtype=float)
        positive = arr > 0
        out[positive] = np.log10(arr[positive])
        return out

    if mode == "asinh":
        return np.arcsinh(arr)

    raise ValueError(f"Unsupported scale mode: {mode}")


def axis_label(base_label: str, mode: ScaleMode) -> str:
    if mode == "linear":
        return base_label
    return f"{base_label} [{mode}]"
