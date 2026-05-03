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
    mtf50p: float | None
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
            "mtf50p": self.mtf50p,
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
    crop_rgb, normalized_roi = _crop_image_roi(image_rgb, roi)
    crop = _luminance_image(crop_rgb)
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
    mtf50p = _mtf_peak_crossing(frequency, mtf, 0.50)
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
        mtf50p=mtf50p,
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


def _crop_image_roi(image: np.ndarray, roi: tuple[int, int, int, int] | None) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    array = np.asarray(image)
    if array.ndim < 2:
        raise ValueError(f"Imagen inesperada para MTF: shape={array.shape}")
    h, w = array.shape[:2]
    if roi is None:
        return array, (0, 0, int(w), int(h))
    x, y, rw, rh = [int(round(v)) for v in roi]
    x0 = int(np.clip(x, 0, max(0, w - 1)))
    y0 = int(np.clip(y, 0, max(0, h - 1)))
    x1 = int(np.clip(x + max(1, rw), x0 + 1, w))
    y1 = int(np.clip(y + max(1, rh), y0 + 1, h))
    return array[y0:y1, x0:x1], (x0, y0, x1 - x0, y1 - y0)


def _fit_edge(gray: np.ndarray) -> dict[str, np.ndarray | float]:
    blurred = cv2.GaussianBlur(gray.astype(np.float32), (0, 0), sigmaX=0.6, sigmaY=0.6)
    gx = cv2.Sobel(blurred, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(blurred, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = np.hypot(gx, gy)
    positive = magnitude[magnitude > 1e-6]
    if positive.size == 0:
        raise ValueError("No se detecta un borde con gradiente suficiente en la ROI.")

    # Use the ridge of the edge gradient. Lower percentiles include texture,
    # uneven illumination and chart surface grain, which biases the fitted edge
    # and artificially widens the ESF.
    for percentile in (98.0, 97.0, 95.0, 92.0, 90.0, 85.0, 80.0, 70.0):
        threshold = float(np.percentile(positive, percentile))
        if threshold <= 1e-6:
            continue
        mask = magnitude >= threshold
        y_idx, x_idx = np.nonzero(mask)
        if len(x_idx) < 16:
            continue
        weights = np.maximum(magnitude[mask].astype(np.float64), 1e-8)
        points = np.column_stack([x_idx.astype(np.float64), y_idx.astype(np.float64)])
        try:
            initial = _fit_edge_from_points(points, weights, gx[mask], gy[mask])
            return _refine_edge_from_line_centroids(gx, gy, initial) or initial
        except ValueError:
            continue
    raise ValueError("No hay suficientes muestras de borde en la ROI seleccionada.")


def _fit_edge_from_points(
    points: np.ndarray,
    weights: np.ndarray,
    gradient_x: np.ndarray,
    gradient_y: np.ndarray,
) -> dict[str, np.ndarray | float]:
    if points.shape[0] < 16:
        raise ValueError("No hay suficientes muestras de borde en la ROI seleccionada.")
    centroid = np.average(points, axis=0, weights=weights)
    centered = points - centroid
    cov = (centered * weights[:, None]).T @ centered / float(np.sum(weights))
    vals, vecs = np.linalg.eigh(cov)
    if not np.isfinite(vals).all() or float(np.max(vals)) <= 1e-8:
        raise ValueError("No se pudo ajustar una línea de borde estable en la ROI.")
    line_dir = vecs[:, int(np.argmax(vals))]
    line_dir = line_dir / max(1e-8, float(np.linalg.norm(line_dir)))
    normal = np.asarray([-line_dir[1], line_dir[0]], dtype=np.float64)

    avg_grad = np.asarray(
        [
            float(np.average(gradient_x, weights=weights)),
            float(np.average(gradient_y, weights=weights)),
        ],
        dtype=np.float64,
    )
    if float(np.dot(normal, avg_grad)) < 0.0:
        normal *= -1.0
    angle = (math.degrees(math.atan2(float(line_dir[1]), float(line_dir[0]))) + 180.0) % 180.0
    return {"centroid": centroid, "normal": normal, "angle": angle}


def _refine_edge_from_line_centroids(
    gx: np.ndarray,
    gy: np.ndarray,
    initial: dict[str, np.ndarray | float],
) -> dict[str, np.ndarray | float] | None:
    normal = np.asarray(initial.get("normal"), dtype=np.float64)
    if normal.shape != (2,) or not np.isfinite(normal).all():
        return None
    if abs(float(normal[0])) >= abs(float(normal[1])):
        return _fit_vertical_edge_from_rows(gx, normal)
    return _fit_horizontal_edge_from_columns(gy, normal)


def _fit_vertical_edge_from_rows(gx: np.ndarray, normal: np.ndarray) -> dict[str, np.ndarray | float] | None:
    h, w = gx.shape[:2]
    if h < 8 or w < 8:
        return None
    oriented = gx.astype(np.float64, copy=False) * (1.0 if float(normal[0]) >= 0.0 else -1.0)
    peaks = np.max(np.maximum(oriented, 0.0), axis=1)
    strong = peaks[peaks > 1e-8]
    if strong.size < 8:
        return None
    min_peak = max(1e-8, float(np.percentile(strong, 65)) * 0.35)
    radius = int(np.clip(round(float(w) * 0.08), 6, 24))
    rows: list[float] = []
    cols: list[float] = []
    weights: list[float] = []
    x_axis = np.arange(w, dtype=np.float64)
    for y, peak in enumerate(peaks):
        if float(peak) < min_peak:
            continue
        profile = np.maximum(oriented[y], 0.0)
        center = int(np.argmax(profile))
        x0 = max(0, center - radius)
        x1 = min(w, center + radius + 1)
        local = profile[x0:x1]
        floor = float(np.percentile(local, 20)) if local.size else 0.0
        local = np.maximum(local - floor, 0.0)
        total = float(np.sum(local))
        if total <= 1e-8:
            continue
        xs = x_axis[x0:x1]
        rows.append(float(y))
        cols.append(float(np.sum(xs * local) / total))
        weights.append(total)
    if len(rows) < max(8, min(24, h // 5)):
        return None
    y_values = np.asarray(rows, dtype=np.float64)
    x_values = np.asarray(cols, dtype=np.float64)
    fit_weights = np.sqrt(np.asarray(weights, dtype=np.float64))
    if float(np.ptp(y_values)) < max(6.0, float(h) * 0.35):
        return None
    coeff = _robust_polyfit(y_values, x_values, fit_weights)
    if coeff is None:
        return None
    slope, intercept = coeff
    fitted_x = slope * y_values + intercept
    centroid = np.asarray(
        [
            float(np.average(fitted_x, weights=fit_weights)),
            float(np.average(y_values, weights=fit_weights)),
        ],
        dtype=np.float64,
    )
    return _edge_from_line(np.asarray([slope, 1.0], dtype=np.float64), centroid, np.asarray([normal[0], -slope], dtype=np.float64))


def _fit_horizontal_edge_from_columns(gy: np.ndarray, normal: np.ndarray) -> dict[str, np.ndarray | float] | None:
    h, w = gy.shape[:2]
    if h < 8 or w < 8:
        return None
    oriented = gy.astype(np.float64, copy=False) * (1.0 if float(normal[1]) >= 0.0 else -1.0)
    peaks = np.max(np.maximum(oriented, 0.0), axis=0)
    strong = peaks[peaks > 1e-8]
    if strong.size < 8:
        return None
    min_peak = max(1e-8, float(np.percentile(strong, 65)) * 0.35)
    radius = int(np.clip(round(float(h) * 0.08), 6, 24))
    cols: list[float] = []
    rows: list[float] = []
    weights: list[float] = []
    y_axis = np.arange(h, dtype=np.float64)
    for x, peak in enumerate(peaks):
        if float(peak) < min_peak:
            continue
        profile = np.maximum(oriented[:, x], 0.0)
        center = int(np.argmax(profile))
        y0 = max(0, center - radius)
        y1 = min(h, center + radius + 1)
        local = profile[y0:y1]
        floor = float(np.percentile(local, 20)) if local.size else 0.0
        local = np.maximum(local - floor, 0.0)
        total = float(np.sum(local))
        if total <= 1e-8:
            continue
        ys = y_axis[y0:y1]
        cols.append(float(x))
        rows.append(float(np.sum(ys * local) / total))
        weights.append(total)
    if len(cols) < max(8, min(24, w // 5)):
        return None
    x_values = np.asarray(cols, dtype=np.float64)
    y_values = np.asarray(rows, dtype=np.float64)
    fit_weights = np.sqrt(np.asarray(weights, dtype=np.float64))
    if float(np.ptp(x_values)) < max(6.0, float(w) * 0.35):
        return None
    coeff = _robust_polyfit(x_values, y_values, fit_weights)
    if coeff is None:
        return None
    slope, intercept = coeff
    fitted_y = slope * x_values + intercept
    centroid = np.asarray(
        [
            float(np.average(x_values, weights=fit_weights)),
            float(np.average(fitted_y, weights=fit_weights)),
        ],
        dtype=np.float64,
    )
    return _edge_from_line(np.asarray([1.0, slope], dtype=np.float64), centroid, np.asarray([-slope, normal[1]], dtype=np.float64))


def _robust_polyfit(x: np.ndarray, y: np.ndarray, weights: np.ndarray) -> tuple[float, float] | None:
    try:
        coeff = np.polyfit(x, y, 1, w=weights)
    except Exception:
        return None
    residual = y - (float(coeff[0]) * x + float(coeff[1]))
    median = float(np.median(residual))
    mad = float(np.median(np.abs(residual - median)))
    limit = max(1.5, 4.0 * 1.4826 * mad)
    keep = np.abs(residual - median) <= limit
    if int(np.count_nonzero(keep)) >= max(8, int(y.size * 0.55)):
        try:
            coeff = np.polyfit(x[keep], y[keep], 1, w=weights[keep])
        except Exception:
            return None
    return float(coeff[0]), float(coeff[1])


def _edge_from_line(line_dir: np.ndarray, centroid: np.ndarray, preferred_normal: np.ndarray) -> dict[str, np.ndarray | float] | None:
    line = np.asarray(line_dir, dtype=np.float64)
    norm = float(np.linalg.norm(line))
    if not np.isfinite(norm) or norm <= 1e-8:
        return None
    line = line / norm
    normal = np.asarray([-line[1], line[0]], dtype=np.float64)
    preferred = np.asarray(preferred_normal, dtype=np.float64)
    if preferred.shape == (2,) and np.isfinite(preferred).all() and float(np.dot(normal, preferred)) < 0.0:
        normal *= -1.0
    angle = (math.degrees(math.atan2(float(line[1]), float(line[0]))) + 180.0) % 180.0
    return {"centroid": np.asarray(centroid, dtype=np.float64), "normal": normal, "angle": angle}


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
    n_bins = max(0, int(math.ceil((high - low) / bin_width)))
    if n_bins < 7:
        raise ValueError("La ROI no ofrece rango suficiente alrededor del borde.")
    bin_indices = np.floor((d - low) / bin_width).astype(np.int64, copy=False)
    bin_indices = np.clip(bin_indices, 0, n_bins - 1)
    sums = np.bincount(bin_indices, weights=values, minlength=n_bins)
    counts = np.bincount(bin_indices, minlength=n_bins)
    valid = counts > 0
    centers = low + (np.arange(n_bins, dtype=np.float64) + 0.5) * bin_width
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


def _mtf_peak_crossing(frequency: np.ndarray, mtf: np.ndarray, fraction: float) -> float | None:
    if len(frequency) < 2 or len(mtf) < 2:
        return None
    x = np.asarray(frequency, dtype=np.float64)
    y = np.asarray(mtf, dtype=np.float64)
    valid = np.isfinite(x) & np.isfinite(y) & (x >= 0.0)
    x = x[valid]
    y = y[valid]
    if x.size < 2:
        return None
    peak = float(np.max(y))
    if peak <= 0.0:
        return None
    return _mtf_crossing(x, y, peak * float(fraction))


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
