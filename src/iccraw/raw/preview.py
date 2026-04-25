from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from ..core.models import Recipe
from ..core.recipe import load_recipe
from ..core.utils import RAW_EXTENSIONS, read_image
from ..profile.builder import load_profile_model
from ..profile.export import apply_profile_matrix
from .compat import open_rawpy, rawpy
from .pipeline import develop_image_array


def load_image_for_preview(
    input_path: Path,
    recipe_path: Path | None = None,
    *,
    recipe: Recipe | None = None,
    fast_raw: bool = True,
    max_preview_side: int = 2600,
) -> tuple[np.ndarray, str]:
    if not input_path.exists():
        raise FileNotFoundError(f"No existe el archivo de entrada: {input_path}")

    if input_path.suffix.lower() not in RAW_EXTENSIONS:
        image = read_image(input_path)
        image = _downscale_for_preview(image, max_preview_side=max_preview_side)
        return image, f"Imagen cargada: {input_path.name}"

    if recipe is None:
        if recipe_path is None:
            raise RuntimeError("Para previsualizar RAW debes indicar una receta YAML/JSON.")
        if not recipe_path.exists():
            raise FileNotFoundError(f"No existe la receta: {recipe_path}")
        recipe = load_recipe(recipe_path)

    if fast_raw:
        image = _develop_raw_fast_preview(input_path, recipe)
        image = _downscale_for_preview(image, max_preview_side=max_preview_side)
        image = _camera_rgb_display_balance_if_needed(image, recipe)
        return image, f"RAW previsualizado en modo rapido: {input_path.name}"

    # Preview de alta calidad: mismo render que develop_controlled, sin TIFF temporal.
    image = develop_image_array(input_path, recipe)
    image = _downscale_for_preview(image, max_preview_side=max_preview_side)
    image = _camera_rgb_display_balance_if_needed(image, recipe)
    return image, f"RAW revelado completo para preview de alta calidad: {input_path.name}"


def _develop_raw_fast_preview(input_path: Path, recipe: Recipe) -> np.ndarray:
    embedded = extract_embedded_preview(input_path)
    if embedded is not None:
        return embedded

    return develop_image_array(input_path, recipe, half_size=True)


def extract_embedded_preview(input_path: Path) -> np.ndarray | None:
    try:
        with open_rawpy(input_path) as raw:
            thumb = raw.extract_thumb()
    except Exception:
        return None

    if thumb.format == rawpy.ThumbFormat.JPEG:
        buf = np.frombuffer(thumb.data, dtype=np.uint8)
        decoded = cv2.imdecode(buf, cv2.IMREAD_UNCHANGED)
        if decoded is None:
            return None
        if decoded.ndim == 2:
            decoded = cv2.cvtColor(decoded, cv2.COLOR_GRAY2RGB)
        elif decoded.ndim == 3:
            decoded = cv2.cvtColor(decoded, cv2.COLOR_BGR2RGB)
        else:
            return None
    elif thumb.format == rawpy.ThumbFormat.BITMAP:
        decoded = np.asarray(thumb.data)
        if decoded.ndim == 2:
            decoded = np.repeat(decoded[..., None], 3, axis=2)
        elif decoded.ndim == 3 and decoded.shape[2] >= 3:
            decoded = decoded[..., :3]
        else:
            return None
    else:
        return None


    if np.issubdtype(decoded.dtype, np.integer):
        maxv = float(np.iinfo(decoded.dtype).max)
        srgb = np.clip(decoded.astype(np.float32) / maxv, 0.0, 1.0)
    else:
        srgb = np.clip(decoded.astype(np.float32), 0.0, 1.0)

    # Embedded previews are generally display-referred (sRGB-encoded).
    # Convert to linear so the rest of the preview pipeline remains consistent.
    return srgb_to_linear_display(srgb)


def _downscale_for_preview(image: np.ndarray, *, max_preview_side: int) -> np.ndarray:
    if max_preview_side <= 0:
        return image.astype(np.float32)

    h, w = int(image.shape[0]), int(image.shape[1])
    max_side = max(h, w)
    if max_side <= max_preview_side:
        return image.astype(np.float32)

    scale = float(max_preview_side) / float(max_side)
    nw = max(1, int(round(w * scale)))
    nh = max(1, int(round(h * scale)))
    resized = cv2.resize(image.astype(np.float32), (nw, nh), interpolation=cv2.INTER_AREA)
    return np.clip(resized, 0.0, 1.0).astype(np.float32)


def _camera_rgb_display_balance_if_needed(image: np.ndarray, recipe: Recipe) -> np.ndarray:
    output_space = str(recipe.output_space or "").strip().lower()
    if not recipe.profiling_mode and "camera_rgb" not in output_space:
        return image.astype(np.float32)

    rgb = np.clip(image.astype(np.float32), 0.0, 1.0)
    if rgb.ndim != 3 or rgb.shape[2] < 3:
        return rgb

    means = np.mean(rgb[..., :3], axis=(0, 1), dtype=np.float64)
    if not np.all(np.isfinite(means)) or float(np.min(means)) <= 1e-6:
        return rgb

    if float(np.max(means) / np.min(means)) < 1.35:
        return rgb

    # Display-only neutralisation for camera-native profiling previews. The
    # scientific render, manual detection geometry, sampling and exported TIFFs
    # continue to use the unmodified recipe data.
    target = float(np.median(means))
    gains = np.clip(target / means, 0.35, 2.8).astype(np.float32)
    balanced = rgb.copy()
    balanced[..., :3] *= gains.reshape((1, 1, 3))
    return np.clip(balanced, 0.0, 1.0).astype(np.float32)


def apply_adjustments(
    image_linear_rgb: np.ndarray,
    *,
    denoise_luminance: float = 0.0,
    denoise_color: float = 0.0,
    denoise_strength: float | None = None,
    sharpen_amount: float = 0.0,
    sharpen_radius: float = 1.0,
    lateral_ca_red_scale: float = 1.0,
    lateral_ca_blue_scale: float = 1.0,
) -> np.ndarray:
    out = np.clip(image_linear_rgb.astype(np.float32), 0.0, 1.0)

    # Backward compatibility: old API used a single denoise value.
    if denoise_strength is not None and denoise_luminance == 0.0 and denoise_color == 0.0:
        denoise_luminance = float(denoise_strength)
        denoise_color = float(denoise_strength)

    dl = float(np.clip(denoise_luminance, 0.0, 1.0))
    dc = float(np.clip(denoise_color, 0.0, 1.0))
    if dl > 0.0 or dc > 0.0:
        ycc = cv2.cvtColor(out, cv2.COLOR_RGB2YCrCb)

        if dl > 0.0:
            sigma_l = 0.2 + dl * 3.2
            y = ycc[..., 0]
            y_blur = cv2.GaussianBlur(y, (0, 0), sigmaX=sigma_l, sigmaY=sigma_l, borderType=cv2.BORDER_REFLECT)
            ycc[..., 0] = (1.0 - dl) * y + dl * y_blur

        if dc > 0.0:
            sigma_c = 0.2 + dc * 3.8
            cc = ycc[..., 1:3]
            cc_blur = cv2.GaussianBlur(cc, (0, 0), sigmaX=sigma_c, sigmaY=sigma_c, borderType=cv2.BORDER_REFLECT)
            ycc[..., 1:3] = (1.0 - dc) * cc + dc * cc_blur

        out = cv2.cvtColor(ycc, cv2.COLOR_YCrCb2RGB)

    if abs(float(lateral_ca_red_scale) - 1.0) > 1e-5 or abs(float(lateral_ca_blue_scale) - 1.0) > 1e-5:
        out = apply_lateral_chromatic_aberration(
            out,
            red_scale=float(lateral_ca_red_scale),
            blue_scale=float(lateral_ca_blue_scale),
        )

    s = float(max(0.0, sharpen_amount))
    if s > 0.0:
        radius = max(0.1, float(sharpen_radius))
        smooth = cv2.GaussianBlur(out, (0, 0), sigmaX=radius, sigmaY=radius, borderType=cv2.BORDER_REFLECT)
        detail = out - smooth
        out = out + s * detail

    return np.clip(out, 0.0, 1.0).astype(np.float32)


def apply_lateral_chromatic_aberration(
    image_linear_rgb: np.ndarray,
    *,
    red_scale: float = 1.0,
    blue_scale: float = 1.0,
) -> np.ndarray:
    """Apply a simple radial red/blue scale correction around the image centre."""
    out = np.clip(image_linear_rgb.astype(np.float32), 0.0, 1.0).copy()
    if out.ndim != 3 or out.shape[2] < 3:
        return out

    if abs(float(red_scale) - 1.0) > 1e-5:
        out[..., 0] = _scale_channel_radially(out[..., 0], float(red_scale))
    if abs(float(blue_scale) - 1.0) > 1e-5:
        out[..., 2] = _scale_channel_radially(out[..., 2], float(blue_scale))
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def apply_render_adjustments(
    image_linear_rgb: np.ndarray,
    *,
    temperature_kelvin: float = 5003.0,
    neutral_kelvin: float = 5003.0,
    tint: float = 0.0,
    brightness_ev: float = 0.0,
    black_point: float = 0.0,
    white_point: float = 1.0,
    contrast: float = 0.0,
    midtone: float = 1.0,
    tone_curve_points: list[tuple[float, float]] | None = None,
    tone_curve_black_point: float = 0.0,
    tone_curve_white_point: float = 1.0,
) -> np.ndarray:
    out = np.clip(image_linear_rgb.astype(np.float32), 0.0, 1.0)

    out = _apply_temperature_tint(
        out,
        temperature_kelvin=float(temperature_kelvin),
        neutral_kelvin=float(neutral_kelvin),
        tint=float(tint),
    )

    if abs(float(brightness_ev)) > 1e-6:
        out = out * (2.0 ** float(brightness_ev))

    bp = float(np.clip(black_point, 0.0, 0.95))
    wp = float(np.clip(white_point, bp + 1e-4, 1.0))
    if bp > 0.0 or wp < 1.0:
        out = (out - bp) / max(1e-4, wp - bp)

    c = float(np.clip(contrast, -0.95, 2.0))
    if abs(c) > 1e-6:
        factor = 1.0 + c
        out = (out - 0.5) * factor + 0.5

    m = float(np.clip(midtone, 0.25, 4.0))
    if abs(m - 1.0) > 1e-6:
        gamma = 1.0 / m
        out = np.power(np.clip(out, 0.0, 1.0), gamma)

    if tone_curve_points:
        out = apply_tone_curve(
            out,
            tone_curve_points,
            black_point=tone_curve_black_point,
            white_point=tone_curve_white_point,
        )

    return np.clip(out, 0.0, 1.0).astype(np.float32)


def normalize_tone_curve_points(points: list[tuple[float, float]] | tuple[tuple[float, float], ...]) -> list[tuple[float, float]]:
    normalized: list[tuple[float, float]] = []
    for point in points:
        try:
            x = float(point[0])
            y = float(point[1])
        except (TypeError, ValueError, IndexError):
            continue
        if not np.isfinite(x) or not np.isfinite(y):
            continue
        normalized.append((float(np.clip(x, 0.0, 1.0)), float(np.clip(y, 0.0, 1.0))))

    normalized.extend([(0.0, 0.0), (1.0, 1.0)])
    normalized.sort(key=lambda p: (p[0], p[1]))

    deduped: list[tuple[float, float]] = []
    for x, y in normalized:
        if deduped and abs(x - deduped[-1][0]) < 1e-4:
            deduped[-1] = (x, y)
        else:
            deduped.append((x, y))
    deduped[0] = (0.0, 0.0)
    deduped[-1] = (1.0, 1.0)

    monotonic: list[tuple[float, float]] = []
    previous_y = 0.0
    for idx, (x, y) in enumerate(deduped):
        if idx == 0:
            y = 0.0
        elif idx == len(deduped) - 1:
            y = 1.0
        else:
            y = float(np.clip(max(y, previous_y), 0.0, 1.0))
        monotonic.append((x, y))
        previous_y = y
    return monotonic


def tone_curve_lut(
    points: list[tuple[float, float]] | tuple[tuple[float, float], ...],
    *,
    lut_size: int = 4096,
    black_point: float = 0.0,
    white_point: float = 1.0,
) -> tuple[np.ndarray, np.ndarray]:
    curve = normalize_tone_curve_points(points)
    xs = np.asarray([p[0] for p in curve], dtype=np.float32)
    ys = np.asarray([p[1] for p in curve], dtype=np.float32)
    lut_size = int(np.clip(lut_size, 256, 65536))

    bp = float(np.clip(black_point, 0.0, 0.95))
    wp = float(np.clip(white_point, bp + 1e-4, 1.0))
    lut_x = np.linspace(0.0, 1.0, lut_size, dtype=np.float32)
    curve_x = np.clip((lut_x - bp) / max(1e-4, wp - bp), 0.0, 1.0).astype(np.float32)
    lut_y = _monotone_cubic_interpolate(xs, ys, curve_x)
    lut_y = np.maximum.accumulate(np.clip(lut_y, 0.0, 1.0)).astype(np.float32)
    lut_y[-1] = 1.0
    return lut_x, lut_y


def apply_tone_curve(
    image_linear_rgb: np.ndarray,
    points: list[tuple[float, float]] | tuple[tuple[float, float], ...],
    *,
    lut_size: int = 4096,
    black_point: float = 0.0,
    white_point: float = 1.0,
) -> np.ndarray:
    curve = normalize_tone_curve_points(points)
    xs = np.asarray([p[0] for p in curve], dtype=np.float32)
    ys = np.asarray([p[1] for p in curve], dtype=np.float32)
    bp = float(np.clip(black_point, 0.0, 0.95))
    wp = float(np.clip(white_point, bp + 1e-4, 1.0))

    out = np.clip(image_linear_rgb.astype(np.float32), 0.0, 1.0)
    if (
        len(curve) <= 2
        and np.allclose(xs, [0.0, 1.0], atol=1e-6)
        and np.allclose(ys, [0.0, 1.0], atol=1e-6)
        and abs(bp) <= 1e-6
        and abs(wp - 1.0) <= 1e-6
    ):
        return out.astype(np.float32)

    # Apply the curve to scene luminance and scale RGB by the luminance ratio.
    # This keeps the operation deterministic while reducing hue shifts versus
    # applying an arbitrary display curve independently to each channel.
    weights = np.asarray([0.2126, 0.7152, 0.0722], dtype=np.float32)
    luminance = np.clip(np.sum(out[..., :3] * weights.reshape((1, 1, 3)), axis=2), 0.0, 1.0)
    _lut_x, lut_y = tone_curve_lut(
        curve,
        lut_size=lut_size,
        black_point=bp,
        white_point=wp,
    )
    lut_size = int(lut_y.size)
    indices = np.clip(np.rint(luminance * (lut_size - 1)), 0, lut_size - 1).astype(np.int32)
    curved_luminance = lut_y[indices]

    scale = np.ones_like(luminance, dtype=np.float32)
    mask = luminance > 1e-6
    scale[mask] = curved_luminance[mask] / luminance[mask]
    adjusted = out.copy()
    adjusted[..., :3] *= scale[..., None]
    return np.clip(adjusted, 0.0, 1.0).astype(np.float32)


def _monotone_cubic_interpolate(x: np.ndarray, y: np.ndarray, x_new: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32)
    y = np.asarray(y, dtype=np.float32)
    x_new = np.asarray(x_new, dtype=np.float32)
    if x.size < 3:
        return np.interp(x_new, x, y).astype(np.float32)

    h = np.diff(x)
    if np.any(h <= 0.0):
        return np.interp(x_new, x, y).astype(np.float32)
    delta = np.diff(y) / h

    slopes = np.zeros_like(y, dtype=np.float32)
    slopes[0] = _pchip_endpoint_slope(h[0], h[1], delta[0], delta[1])
    slopes[-1] = _pchip_endpoint_slope(h[-1], h[-2], delta[-1], delta[-2])
    for idx in range(1, x.size - 1):
        left = float(delta[idx - 1])
        right = float(delta[idx])
        if left <= 0.0 or right <= 0.0:
            slopes[idx] = 0.0
        else:
            w1 = 2.0 * float(h[idx]) + float(h[idx - 1])
            w2 = float(h[idx]) + 2.0 * float(h[idx - 1])
            slopes[idx] = (w1 + w2) / ((w1 / left) + (w2 / right))

    interval = np.searchsorted(x, x_new, side="right") - 1
    interval = np.clip(interval, 0, x.size - 2)
    x0 = x[interval]
    x1 = x[interval + 1]
    y0 = y[interval]
    y1 = y[interval + 1]
    m0 = slopes[interval]
    m1 = slopes[interval + 1]
    width = np.maximum(x1 - x0, 1e-6)
    t = (x_new - x0) / width
    t2 = t * t
    t3 = t2 * t

    h00 = 2.0 * t3 - 3.0 * t2 + 1.0
    h10 = t3 - 2.0 * t2 + t
    h01 = -2.0 * t3 + 3.0 * t2
    h11 = t3 - t2
    return (h00 * y0 + h10 * width * m0 + h01 * y1 + h11 * width * m1).astype(np.float32)


def _pchip_endpoint_slope(h0: float, h1: float, delta0: float, delta1: float) -> np.float32:
    d = ((2.0 * h0 + h1) * delta0 - h0 * delta1) / max(1e-6, h0 + h1)
    if d <= 0.0:
        return np.float32(0.0)
    if delta0 <= 0.0:
        return np.float32(0.0)
    if delta1 <= 0.0 and d > 3.0 * delta0:
        return np.float32(3.0 * delta0)
    return np.float32(d)


def _scale_channel_radially(channel: np.ndarray, scale: float) -> np.ndarray:
    if scale <= 0.0 or abs(scale - 1.0) <= 1e-5:
        return channel.astype(np.float32)

    h, w = channel.shape[:2]
    y, x = np.indices((h, w), dtype=np.float32)
    cx = (w - 1) / 2.0
    cy = (h - 1) / 2.0
    map_x = ((x - cx) / scale + cx).astype(np.float32)
    map_y = ((y - cy) / scale + cy).astype(np.float32)
    return cv2.remap(
        channel.astype(np.float32),
        map_x,
        map_y,
        interpolation=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT,
    )


def _apply_temperature_tint(
    image_linear_rgb: np.ndarray,
    *,
    temperature_kelvin: float,
    neutral_kelvin: float,
    tint: float,
) -> np.ndarray:
    multipliers = temperature_tint_multipliers(
        temperature_kelvin=temperature_kelvin,
        neutral_kelvin=neutral_kelvin,
        tint=tint,
    )
    return image_linear_rgb * multipliers.reshape((1, 1, 3))


def temperature_tint_multipliers(
    *,
    temperature_kelvin: float,
    neutral_kelvin: float = 5003.0,
    tint: float = 0.0,
) -> np.ndarray:
    temp = float(np.clip(temperature_kelvin, 2000.0, 12000.0))
    neutral = float(np.clip(neutral_kelvin, 2000.0, 12000.0))
    warm = float(np.clip(np.log(temp / neutral), -1.2, 1.2))
    tint_n = float(np.clip(tint / 100.0, -1.0, 1.0))

    multipliers = np.array(
        [
            1.0 + 0.22 * warm + 0.08 * tint_n,
            1.0 - 0.16 * tint_n,
            1.0 - 0.22 * warm + 0.08 * tint_n,
        ],
        dtype=np.float32,
    )
    return np.clip(multipliers, 0.55, 1.65)


def estimate_temperature_tint_from_neutral_sample(
    sample_rgb: np.ndarray,
    *,
    neutral_kelvin: float = 5003.0,
) -> tuple[int, float]:
    """Estimate preview temperature/tint controls from a sampled neutral patch."""
    sample = np.asarray(sample_rgb, dtype=np.float64).reshape(-1)
    if sample.size < 3:
        raise ValueError("La muestra neutra no contiene canales RGB suficientes.")
    sample = sample[:3]
    if not np.all(np.isfinite(sample)) or float(np.max(sample)) <= 1e-6:
        raise ValueError("La muestra neutra no es valida.")

    sample = np.clip(sample, 1e-6, 1.0)
    if float(np.max(sample)) < 0.01:
        raise ValueError("La muestra neutra es demasiado oscura.")

    temp, tint = _best_temperature_tint_for_sample(
        sample,
        neutral_kelvin=neutral_kelvin,
        temp_values=np.arange(2000.0, 12000.1, 100.0),
        tint_values=np.arange(-100.0, 100.1, 2.0),
    )
    temp, tint = _best_temperature_tint_for_sample(
        sample,
        neutral_kelvin=neutral_kelvin,
        temp_values=np.arange(max(2000.0, temp - 160.0), min(12000.0, temp + 160.0) + 0.1, 10.0),
        tint_values=np.arange(max(-100.0, tint - 5.0), min(100.0, tint + 5.0) + 0.001, 0.2),
    )
    return int(round(temp)), float(round(tint, 1))


def _best_temperature_tint_for_sample(
    sample_rgb: np.ndarray,
    *,
    neutral_kelvin: float,
    temp_values: np.ndarray,
    tint_values: np.ndarray,
) -> tuple[float, float]:
    temps = np.asarray(temp_values, dtype=np.float64)
    tints = np.asarray(tint_values, dtype=np.float64)
    neutral = float(np.clip(neutral_kelvin, 2000.0, 12000.0))
    warm = np.clip(np.log(temps[:, None] / neutral), -1.2, 1.2)
    tint_n = np.clip(tints[None, :] / 100.0, -1.0, 1.0)

    multipliers = np.stack(
        [
            1.0 + 0.22 * warm + 0.08 * tint_n,
            np.broadcast_to(1.0 - 0.16 * tint_n, (temps.size, tints.size)),
            1.0 - 0.22 * warm + 0.08 * tint_n,
        ],
        axis=-1,
    )
    multipliers = np.clip(multipliers, 0.55, 1.65)
    corrected = multipliers * sample_rgb.reshape((1, 1, 3))
    mean = np.mean(corrected, axis=-1, keepdims=True)
    log_chroma = np.log(np.clip(corrected / np.clip(mean, 1e-6, None), 1e-6, None))
    cost = np.mean(log_chroma * log_chroma, axis=-1)
    idx = np.unravel_index(int(np.argmin(cost)), cost.shape)
    return float(temps[idx[0]]), float(tints[idx[1]])


def apply_profile_preview(image_linear_rgb: np.ndarray, profile_path: Path) -> np.ndarray:
    if not profile_path.exists():
        raise FileNotFoundError(f"No existe el perfil ICC: {profile_path}")

    model = load_profile_model(profile_path)
    matrix = np.asarray(model["matrix_camera_to_xyz"], dtype=np.float64)
    mapped = apply_profile_matrix(
        image_linear_rgb=image_linear_rgb,
        matrix_camera_to_xyz=matrix,
        output_space="srgb",
        output_linear=False,
    )
    return np.clip(mapped.astype(np.float32), 0.0, 1.0)


def linear_to_srgb_display(image_linear_rgb: np.ndarray) -> np.ndarray:
    x = np.clip(image_linear_rgb.astype(np.float32), 0.0, 1.0)
    a = 0.055
    srgb = np.where(x <= 0.0031308, 12.92 * x, (1.0 + a) * np.power(x, 1.0 / 2.4) - a)
    return np.clip(srgb, 0.0, 1.0)


def srgb_to_linear_display(image_srgb: np.ndarray) -> np.ndarray:
    x = np.clip(image_srgb.astype(np.float32), 0.0, 1.0)
    linear = np.where(x <= 0.04045, x / 12.92, np.power((x + 0.055) / 1.055, 2.4))
    return np.clip(linear, 0.0, 1.0)


def preview_analysis_text(original_linear: np.ndarray, adjusted_linear: np.ndarray) -> str:
    o = np.clip(original_linear.astype(np.float32), 0.0, 1.0)
    a = np.clip(adjusted_linear.astype(np.float32), 0.0, 1.0)

    lines: list[str] = []
    lines.append("Resumen de análisis (lineal 0..1)")
    lines.append("")
    lines.extend(_channel_stats("Original", o))
    lines.append("")
    lines.extend(_channel_stats("Ajustada", a))
    lines.append("")
    diff = np.abs(a - o)
    lines.append(f"Diferencia media absoluta global: {float(np.mean(diff)):.6f}")
    lines.append(f"Diferencia máxima absoluta global: {float(np.max(diff)):.6f}")
    return "\n".join(lines)


def _channel_stats(label: str, image: np.ndarray) -> list[str]:
    ch_names = ("R", "G", "B")
    lines = [f"{label}:"]
    for idx, ch_name in enumerate(ch_names):
        ch = image[..., idx]
        lines.append(
            (
                f"  {ch_name}: media={float(np.mean(ch)):.6f} "
                f"std={float(np.std(ch)):.6f} "
                f"min={float(np.min(ch)):.6f} "
                f"max={float(np.max(ch)):.6f} "
                f"clip_hi={float(np.mean(ch >= 0.999)) * 100.0:.3f}%"
            )
        )
    return lines
