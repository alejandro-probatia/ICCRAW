from __future__ import annotations

import numpy as np
import colour


def delta_e76(lab_a: np.ndarray, lab_b: np.ndarray) -> np.ndarray:
    return colour.delta_E(lab_a, lab_b, method="CIE 1976")


def delta_e2000(lab_a: np.ndarray, lab_b: np.ndarray) -> np.ndarray:
    return colour.delta_E(lab_a, lab_b, method="CIE 2000")


def summarize(values: np.ndarray) -> dict[str, float]:
    values = np.asarray(values, dtype=np.float64)
    return {
        "mean": float(np.mean(values)) if values.size else 0.0,
        "median": float(np.median(values)) if values.size else 0.0,
        "p95": float(np.percentile(values, 95)) if values.size else 0.0,
        "max": float(np.max(values)) if values.size else 0.0,
    }
