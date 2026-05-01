from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import cv2
import numpy as np


@dataclass(frozen=True)
class MTFResult:
    roi: tuple[int, int, int, int]
    roi_shape: tuple[int, int]
    edge_angle_degrees: float
    edge_contrast: float
    overshoot: float
    undershoot: float
    mtf50: float | None
    mtf30: float | None
    mtf10: float | None
    acutance: float
    esf_distance: list[float]
    esf: list[float]
    lsf_distance: list[float]
    lsf: list[float]
    frequency: list[float]
    mtf: list[float]
    frequency_extended: list[float]
    mtf_extended: list[float]
    warnings: list[str]

    def summary(self) -> dict[str, Any]:
        return {
            "roi": list(self.roi),
            "roi_shape": list(self.roi_shape),
            "edge_angle_degrees": self.edge_angle_degrees,
            "edge_contrast": self.edge_contrast,
            "overshoot": self.overshoot,
            "undershoot": self.undershoot,
            "mtf50": self.mtf50,
            "mtf30": self.mtf30,
            "mtf10": self.mtf10,
            "acutance": self.acutance,
            "frequency_range_cycles_per_pixel": [
                self.frequency[0] if self.frequency else None,
                self.frequency[-1] if self.frequency else None,
            ],
            "extended_frequency_range_cycles_per_pixel": [
                self.frequency_extended[0] if self.frequency_extended else None,
                self.frequency_extended[-1] if self.frequency_extended else None,
            ],
            "warnings": list(self.warnings),
        }


def analyze_slanted_edge_mtf(
    image_rgb: np.ndarray,
    roi: tuple[int, int, int, int] | None = None,
    *,
    oversampling: int = 4,
    min_size: int = 24,
) -> MTFResult:
    """Estimate slanted-edge ESF, LSF and MTF from an RGB image or ROI.

    The implementation is intentionally self-contained and deterministic. It is
    not a full ISO 12233 conformance harness, but it follows the same practical
    slanted-edge idea: fit the edge, oversample the edge spread function from
    pixel distances to that edge, differentiate into an LSF, then transform the
    LSF into an MTF curve up to Nyquist.
    """
    gray_full = _luminance_image(image_rgb)
    crop, normalized_roi = _crop_roi(gray_full, roi)
    h, w = crop.shape[:2]
    if h < int(min_size) or w < int(min_size):
        raise ValueError(f"La ROI MTF debe medir al menos {min_size}x{min_size} píxeles.")

    contrast_hint = float(np.percentile(crop, 95) - np.percentile(crop, 5))
    if contrast_hint < 0.03:
        raise ValueError("La ROI seleccionada tiene demasiado poco contraste para estimar MTF.")

    edge = _fit_edge(crop)
    bin_width = 1.0 / max(1, int(oversampling))
    distances, esf = _edge_spread_function(crop, edge["normal"], edge["centroid"], bin_width=bin_width)
    distances, esf = _regularize_esf(distances, esf)

    edge_count = max(4, len(esf) // 10)
    low = float(np.median(esf[:edge_count]))
    high = float(np.median(esf[-edge_count:]))
    if high < low:
        distances = -distances[::-1]
        esf = esf[::-1]
        low, high = high, low
    contrast = float(high - low)
    if abs(contrast) < 0.03:
        raise ValueError("No se pudo separar un lado oscuro y uno claro del borde seleccionado.")

    esf_normalized = np.clip((esf - low) / contrast, -0.5, 1.5)
    esf_smooth = _smooth_esf(esf_normalized)
    lsf_distance, lsf = _line_spread_function(distances, esf_smooth)
    frequency, mtf, frequency_extended, mtf_extended = _mtf_from_lsf(lsf, bin_width=bin_width)

    mtf50 = _mtf_crossing(frequency, mtf, 0.50)
    mtf30 = _mtf_crossing(frequency, mtf, 0.30)
    mtf10 = _mtf_crossing(frequency, mtf, 0.10)
    acutance = _mtf_acutance(frequency, mtf)
    overshoot = float(max(0.0, np.max(esf_normalized) - 1.0))
    undershoot = float(max(0.0, -np.min(esf_normalized)))

    warnings: list[str] = []
    angle = float(edge["angle"])
    near_axis = min(abs(angle % 90.0), abs(90.0 - (angle % 90.0)))
    if near_axis < 2.0:
        warnings.append("El borde está casi alineado con la rejilla; una inclinación de 3-7° suele ser más estable.")
    if overshoot > 0.10 or undershoot > 0.10:
        warnings.append("Se detecta sobreimpulso visible; puede indicar exceso de nitidez.")

    return MTFResult(
        roi=normalized_roi,
        roi_shape=(int(h), int(w)),
        edge_angle_degrees=angle,
        edge_contrast=contrast,
        overshoot=overshoot,
        undershoot=undershoot,
        mtf50=mtf50,
        mtf30=mtf30,
        mtf10=mtf10,
        acutance=acutance,
        esf_distance=_finite_list(distances),
        esf=_finite_list(esf_smooth),
        lsf_distance=_finite_list(lsf_distance),
        lsf=_finite_list(lsf),
        frequency=_finite_list(frequency),
        mtf=_finite_list(mtf),
        frequency_extended=_finite_list(frequency_extended),
        mtf_extended=_finite_list(mtf_extended),
        warnings=warnings,
    )


def _luminance_image(image_rgb: np.ndarray) -> np.ndarray:
    image = np.asarray(image_rgb, dtype=np.float32)
    if image.ndim == 2:
        gray = image
    elif image.ndim == 3 and image.shape[2] >= 3:
        rgb = np.clip(image[..., :3], 0.0, 1.0)
        gray = (
            0.2126 * rgb[..., 0]
            + 0.7152 * rgb[..., 1]
            + 0.0722 * rgb[..., 2]
        )
    else:
        raise ValueError(f"Imagen inesperada para MTF: shape={image.shape}")
    gray = np.asarray(gray, dtype=np.float32)
    if not np.isfinite(gray).all():
        gray = np.nan_to_num(gray, nan=0.0, posinf=1.0, neginf=0.0)
    return np.clip(gray, 0.0, 1.0)


def _crop_roi(gray: np.ndarray, roi: tuple[int, int, int, int] | None) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    h, w = gray.shape[:2]
    if roi is None:
        return gray.copy(), (0, 0, int(w), int(h))
    x, y, rw, rh = [int(round(v)) for v in roi]
    x0 = int(np.clip(x, 0, max(0, w - 1)))
    y0 = int(np.clip(y, 0, max(0, h - 1)))
    x1 = int(np.clip(x + max(1, rw), x0 + 1, w))
    y1 = int(np.clip(y + max(1, rh), y0 + 1, h))
    return gray[y0:y1, x0:x1].copy(), (x0, y0, x1 - x0, y1 - y0)


def _fit_edge(gray: np.ndarray) -> dict[str, np.ndarray | float]:
    blurred = cv2.GaussianBlur(gray.astype(np.float32), (0, 0), sigmaX=0.6, sigmaY=0.6)
    gx = cv2.Sobel(blurred, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(blurred, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = np.hypot(gx, gy)
    positive = magnitude[magnitude > 1e-6]
    threshold = float(np.percentile(positive, 70)) if positive.size else 0.0
    if threshold <= 1e-6:
        raise ValueError("No se detecta un borde con gradiente suficiente en la ROI.")
    mask = magnitude >= threshold
    y_idx, x_idx = np.nonzero(mask)
    if len(x_idx) < 16:
        raise ValueError("No hay suficientes muestras de borde en la ROI seleccionada.")

    weights = magnitude[mask].astype(np.float64)
    weights = np.maximum(weights, 1e-8)
    points = np.column_stack([x_idx.astype(np.float64), y_idx.astype(np.float64)])
    centroid = np.average(points, axis=0, weights=weights)
    centered = points - centroid
    cov = (centered * weights[:, None]).T @ centered / float(np.sum(weights))
    vals, vecs = np.linalg.eigh(cov)
    line_dir = vecs[:, int(np.argmax(vals))]
    line_dir = line_dir / max(1e-8, float(np.linalg.norm(line_dir)))
    normal = np.asarray([-line_dir[1], line_dir[0]], dtype=np.float64)

    avg_grad = np.asarray(
        [
            float(np.average(gx[mask], weights=weights)),
            float(np.average(gy[mask], weights=weights)),
        ],
        dtype=np.float64,
    )
    if float(np.dot(normal, avg_grad)) < 0.0:
        normal *= -1.0
    angle = (math.degrees(math.atan2(float(line_dir[1]), float(line_dir[0]))) + 180.0) % 180.0
    return {"centroid": centroid, "normal": normal, "angle": angle}


def _edge_spread_function(
    gray: np.ndarray,
    normal: np.ndarray,
    centroid: np.ndarray,
    *,
    bin_width: float,
) -> tuple[np.ndarray, np.ndarray]:
    h, w = gray.shape[:2]
    ys, xs = np.mgrid[0:h, 0:w].astype(np.float64)
    distances = (xs - float(centroid[0])) * float(normal[0]) + (ys - float(centroid[1])) * float(normal[1])
    values = gray.astype(np.float64).reshape(-1)
    d = distances.reshape(-1)
    low = math.floor(float(np.min(d)) / bin_width) * bin_width
    high = math.ceil(float(np.max(d)) / bin_width) * bin_width
    edges = np.arange(low, high + bin_width, bin_width, dtype=np.float64)
    if len(edges) < 8:
        raise ValueError("La ROI no ofrece rango suficiente alrededor del borde.")
    sums, _ = np.histogram(d, bins=edges, weights=values)
    counts, _ = np.histogram(d, bins=edges)
    valid = counts > 0
    centers = (edges[:-1] + edges[1:]) / 2.0
    if int(np.count_nonzero(valid)) < 12:
        raise ValueError("No hay suficientes bins MTF válidos; aumenta la ROI.")
    return centers[valid], sums[valid] / np.maximum(1, counts[valid])


def _regularize_esf(distances: np.ndarray, esf: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    d = np.asarray(distances, dtype=np.float64)
    y = np.asarray(esf, dtype=np.float64)
    order = np.argsort(d)
    d = d[order]
    y = y[order]
    if len(d) < 12:
        raise ValueError("ESF demasiado corta para calcular MTF.")
    step = float(np.median(np.diff(d)))
    if not np.isfinite(step) or step <= 0:
        raise ValueError("Muestreo ESF inválido.")
    regular = np.arange(float(d[0]), float(d[-1]) + step * 0.5, step, dtype=np.float64)
    values = np.interp(regular, d, y)
    return regular, values


def _smooth_esf(esf: np.ndarray) -> np.ndarray:
    values = np.asarray(esf, dtype=np.float64)
    if len(values) < 7:
        return values
    kernel = np.asarray([1.0, 2.0, 3.0, 2.0, 1.0], dtype=np.float64)
    kernel /= float(np.sum(kernel))
    radius = len(kernel) // 2
    padded = np.pad(values, (radius, radius), mode="edge")
    return np.convolve(padded, kernel, mode="valid")


def _line_spread_function(distances: np.ndarray, esf: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    d = np.asarray(distances, dtype=np.float64)
    y = np.asarray(esf, dtype=np.float64)
    step = float(np.median(np.diff(d)))
    lsf = np.gradient(y, step)
    return d, lsf


def _mtf_from_lsf(lsf: np.ndarray, *, bin_width: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    signal = np.asarray(lsf, dtype=np.float64)
    if signal.size < 8:
        raise ValueError("LSF demasiado corta para calcular MTF.")
    signal = signal - float(np.median(signal[: max(2, signal.size // 20)]))
    window = np.hamming(signal.size)
    spectrum = np.abs(np.fft.rfft(signal * window))
    if spectrum.size == 0 or float(spectrum[0]) <= 1e-10:
        raise ValueError("MTF inválida: la LSF no contiene energía útil.")
    mtf = spectrum / float(spectrum[0])
    freq = np.fft.rfftfreq(signal.size, d=float(bin_width))
    mtf = np.clip(mtf, 0.0, 2.0)
    keep = freq <= 0.5
    return freq[keep], mtf[keep], freq, mtf


def _mtf_crossing(frequency: np.ndarray, mtf: np.ndarray, level: float) -> float | None:
    if len(frequency) < 2 or len(mtf) < 2:
        return None
    y = np.minimum.accumulate(np.asarray(mtf, dtype=np.float64))
    x = np.asarray(frequency, dtype=np.float64)
    if float(np.min(y)) > float(level):
        return None
    for idx in range(1, len(y)):
        if y[idx] <= level <= y[idx - 1]:
            y0, y1 = float(y[idx - 1]), float(y[idx])
            x0, x1 = float(x[idx - 1]), float(x[idx])
            if abs(y1 - y0) <= 1e-12:
                return x1
            t = (float(level) - y0) / (y1 - y0)
            return float(x0 + t * (x1 - x0))
    return None


def _mtf_acutance(frequency: np.ndarray, mtf: np.ndarray) -> float:
    if len(frequency) < 2:
        return 0.0
    x = np.asarray(frequency, dtype=np.float64)
    y = np.clip(np.asarray(mtf, dtype=np.float64), 0.0, 1.5)
    area = float(np.trapezoid(y, x))
    return area / 0.5


def _finite_list(values: np.ndarray) -> list[float]:
    arr = np.asarray(values, dtype=np.float64)
    return [float(v) for v in arr if np.isfinite(v)]
