from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile

import cv2
import numpy as np

from ..core.models import Recipe
from ..core.recipe import load_recipe
from ..core.utils import RAW_EXTENSIONS, read_image
from ..profile.builder import load_profile_model
from ..profile.export import apply_profile_matrix
from .pipeline import dcraw_quality_value, develop_controlled


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
        return image, f"RAW previsualizado en modo rapido: {input_path.name}"

    # Fallback preciso: mismo pipeline de revelado controlado.
    with tempfile.TemporaryDirectory(prefix="iccraw_qt_preview_") as tmp:
        out_tiff = Path(tmp) / "preview_raw.tiff"
        develop_controlled(input_path, recipe, out_tiff, None)
        image = read_image(out_tiff)
    image = _downscale_for_preview(image, max_preview_side=max_preview_side)
    return image, f"RAW revelado completo para preview: {input_path.name}"


def _develop_raw_fast_preview(input_path: Path, recipe: Recipe) -> np.ndarray:
    if shutil.which("dcraw") is None:
        raise RuntimeError("No se puede previsualizar RAW: 'dcraw' no esta disponible en PATH.")

    embedded = extract_embedded_preview(input_path)
    if embedded is not None:
        return embedded

    q = dcraw_quality_value(recipe.demosaic_algorithm)
    cmd = [
        "dcraw",
        "-T",
        "-4",
        "-W",
        "-H",
        "0",
        "-t",
        "0",
        "-o",
        "1",
        "-h",  # Half-size decode; much faster for interactive preview.
        "-q",
        q,
    ]

    wb_mode = recipe.white_balance_mode.strip().lower()
    if wb_mode == "camera_metadata":
        cmd.append("-w")
    elif wb_mode == "fixed":
        wb = _dcraw_wb(recipe.wb_multipliers)
        if wb is not None:
            cmd.extend(["-r", *(f"{v:.10g}" for v in wb)])

    black_mode = recipe.black_level_mode.strip().lower()
    if black_mode.startswith("fixed:"):
        cmd.extend(["-k", str(_parse_int_mode_value(black_mode, "fixed"))])
    elif black_mode.startswith("white:"):
        cmd.extend(["-S", str(_parse_int_mode_value(black_mode, "white"))])

    cmd.extend(["-c", str(input_path)])

    with tempfile.TemporaryDirectory(prefix="iccraw_fast_preview_") as tmp:
        out = Path(tmp) / "dcraw_fast_preview.tiff"
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            stderr_tail = proc.stderr.decode("utf-8", errors="ignore")[-400:]
            raise RuntimeError(f"Fallo de previsualizacion RAW con dcraw: {stderr_tail}")
        if not proc.stdout:
            raise RuntimeError("dcraw no devolvio datos para la previsualizacion RAW.")
        out.write_bytes(proc.stdout)
        return read_image(out)


def extract_embedded_preview(input_path: Path) -> np.ndarray | None:
    cmd = ["dcraw", "-e", "-c", str(input_path)]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0 or not proc.stdout:
        return None

    buf = np.frombuffer(proc.stdout, dtype=np.uint8)
    decoded = cv2.imdecode(buf, cv2.IMREAD_UNCHANGED)
    if decoded is None:
        return None

    if decoded.ndim == 2:
        decoded = cv2.cvtColor(decoded, cv2.COLOR_GRAY2RGB)
    elif decoded.ndim == 3:
        decoded = cv2.cvtColor(decoded, cv2.COLOR_BGR2RGB)
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


def _dcraw_wb(values: list[float] | None) -> list[float] | None:
    if not values:
        return None
    wb = [float(v) for v in values]
    if len(wb) >= 4:
        return [wb[0], wb[1], wb[2], wb[3]]
    if len(wb) == 3:
        return [wb[0], wb[1], wb[2], wb[1]]
    return None


def _parse_int_mode_value(mode: str, prefix: str) -> int:
    raw = mode.split(":", 1)[1]
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"Valor invalido para {prefix} level: {raw}") from exc
    if value < 0:
        raise RuntimeError(f"Valor invalido para {prefix} level: {raw}")
    return value


def apply_adjustments(
    image_linear_rgb: np.ndarray,
    *,
    denoise_luminance: float = 0.0,
    denoise_color: float = 0.0,
    denoise_strength: float | None = None,
    sharpen_amount: float = 0.0,
    sharpen_radius: float = 1.0,
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

    s = float(max(0.0, sharpen_amount))
    if s > 0.0:
        radius = max(0.1, float(sharpen_radius))
        smooth = cv2.GaussianBlur(out, (0, 0), sigmaX=radius, sigmaY=radius, borderType=cv2.BORDER_REFLECT)
        detail = out - smooth
        out = out + s * detail

    return np.clip(out, 0.0, 1.0).astype(np.float32)


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
