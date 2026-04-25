from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import rawpy

from ..core.models import Recipe
from ..core.recipe import load_recipe
from ..core.utils import RAW_EXTENSIONS, read_image
from ..profile.builder import load_profile_model
from ..profile.export import apply_profile_matrix
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
        with rawpy.imread(str(input_path)) as raw:
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

    return np.clip(out, 0.0, 1.0).astype(np.float32)


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
    multipliers = np.clip(multipliers, 0.55, 1.65)
    return image_linear_rgb * multipliers.reshape((1, 1, 3))


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
