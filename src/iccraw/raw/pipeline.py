from __future__ import annotations

from pathlib import Path

import numpy as np

try:
    import rawpy
except Exception:  # pragma: no cover - dependency check emits a clearer runtime error.
    rawpy = None

from ..core.models import DevelopResult, Recipe
from ..core.recipe import scientific_guard
from ..core.utils import read_image, write_tiff16
from .metadata import raw_info


LIBRAW_DEMOSAIC_MAP = {
    "linear": "LINEAR",
    "vng": "VNG",
    "ppg": "PPG",
    "ahd": "AHD",
    "modified_ahd": "MODIFIED_AHD",
    "aahd": "AAHD",
    "afd": "AFD",
    "vcd": "VCD",
    "vcd_modified_ahd": "VCD_MODIFIED_AHD",
    "dcb": "DCB",
    "dht": "DHT",
    "lmmse": "LMMSE",
    "amaze": "AMAZE",
}


RAW_SUFFIXES = {".raw", ".cr2", ".cr3", ".nef", ".arw", ".dng", ".raf", ".rw2", ".orf", ".pef"}


def develop_controlled(input_path: Path, recipe: Recipe, out_tiff: Path, audit_linear_tiff: Path | None = None) -> DevelopResult:
    metadata = raw_info(input_path) if input_path.suffix.lower() in RAW_SUFFIXES else _fake_metadata(input_path)
    guard = scientific_guard(recipe)

    image = _develop_image(input_path, recipe)

    audit_path_str: str | None = None
    if audit_linear_tiff is not None:
        write_tiff16(audit_linear_tiff, image)
        audit_path_str = str(audit_linear_tiff)

    if recipe.exposure_compensation != 0.0:
        image = np.clip(image * (2.0 ** float(recipe.exposure_compensation)), 0.0, 1.0)

    if recipe.tone_curve.lower() == "srgb":
        image = _apply_srgb_oetf(image)
    elif recipe.tone_curve.lower().startswith("gamma:"):
        gamma = float(recipe.tone_curve.split(":", 1)[1])
        image = np.clip(np.power(np.clip(image, 0.0, 1.0), 1.0 / gamma), 0.0, 1.0)

    write_tiff16(out_tiff, image)

    return DevelopResult(
        raw_metadata=metadata,
        recipe=recipe,
        scientific_guard=guard,
        output_tiff=str(out_tiff),
        audit_tiff=audit_path_str,
    )


def _develop_image(input_path: Path, recipe: Recipe) -> np.ndarray:
    if input_path.suffix.lower() not in RAW_SUFFIXES:
        return read_image(input_path)

    developer = recipe.raw_developer.strip().lower()
    if developer not in {"", "libraw", "rawpy"}:
        raise RuntimeError(f"raw_developer no soportado: {recipe.raw_developer}. Usa 'libraw'.")
    return develop_with_libraw(input_path, recipe, half_size=False)


def develop_with_libraw(input_path: Path, recipe: Recipe, *, half_size: bool = False) -> np.ndarray:
    if rawpy is None:
        raise RuntimeError("No se puede revelar RAW: dependencia 'rawpy'/'LibRaw' no disponible.")

    kwargs = _build_libraw_postprocess_kwargs(recipe, half_size=half_size)
    try:
        with rawpy.imread(str(input_path)) as raw:
            image = raw.postprocess(**kwargs)
    except Exception as exc:
        raise RuntimeError(f"Fallo de decodificacion RAW con LibRaw/rawpy: {exc}") from exc
    return _postprocess_output_to_float(image)


def _build_libraw_postprocess_kwargs(recipe: Recipe, *, half_size: bool = False) -> dict:
    if rawpy is None:
        raise RuntimeError("No se puede configurar LibRaw: dependencia 'rawpy' no disponible.")

    wb_mode = recipe.white_balance_mode.strip().lower()
    use_camera_wb = wb_mode == "camera_metadata"
    user_wb = _libraw_wb(recipe.wb_multipliers) if wb_mode == "fixed" else None

    kwargs = {
        "demosaic_algorithm": libraw_demosaic_value(recipe.demosaic_algorithm),
        "half_size": bool(half_size),
        "use_camera_wb": use_camera_wb,
        "use_auto_wb": False,
        "user_wb": user_wb,
        "output_color": rawpy.ColorSpace.raw,
        "output_bps": 16,
        "user_flip": 0,
        "no_auto_bright": True,
        "bright": 1.0,
        "highlight_mode": rawpy.HighlightMode.Clip,
        "gamma": (1.0, 1.0),
    }

    black_mode = recipe.black_level_mode.strip().lower()
    if black_mode.startswith("fixed:"):
        kwargs["user_black"] = _parse_int_mode_value(black_mode, "fixed")
    elif black_mode.startswith("white:"):
        kwargs["user_sat"] = _parse_int_mode_value(black_mode, "white")

    return kwargs


def libraw_demosaic_value(demosaic_algorithm: str):
    if rawpy is None:
        raise RuntimeError("No se puede configurar demosaicing: dependencia 'rawpy' no disponible.")

    name = str(demosaic_algorithm or "").strip().lower()
    if name not in LIBRAW_DEMOSAIC_MAP:
        supported = ", ".join(sorted(LIBRAW_DEMOSAIC_MAP))
        raise RuntimeError(
            "demosaic_algorithm no soportado por LibRaw/rawpy: "
            f"{demosaic_algorithm!r}. Valores soportados: {supported}."
        )
    enum_name = LIBRAW_DEMOSAIC_MAP[name]
    return getattr(rawpy.DemosaicAlgorithm, enum_name)


def _libraw_wb(values: list[float] | None) -> list[float] | None:
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


def _postprocess_output_to_float(image: np.ndarray) -> np.ndarray:
    out = np.asarray(image)
    if out.ndim == 2:
        out = np.repeat(out[..., None], 3, axis=2)
    if out.ndim != 3 or out.shape[2] < 3:
        raise RuntimeError(f"Salida LibRaw inesperada: shape={out.shape}")
    out = out[..., :3]

    if np.issubdtype(out.dtype, np.integer):
        maxv = float(np.iinfo(out.dtype).max)
        return np.clip(out.astype(np.float32) / maxv, 0.0, 1.0)
    return np.clip(out.astype(np.float32), 0.0, 1.0)


def _apply_srgb_oetf(x: np.ndarray) -> np.ndarray:
    a = 0.055
    out = np.where(x <= 0.0031308, 12.92 * x, (1 + a) * np.power(np.clip(x, 0.0, 1.0), 1 / 2.4) - a)
    return np.clip(out, 0.0, 1.0)


def _fake_metadata(path: Path):
    from ..core.models import RawMetadata
    from ..core.utils import sha256_file

    return RawMetadata(
        source_file=str(path),
        input_sha256=sha256_file(path),
        camera_model="non-raw-input",
        cfa_pattern="none",
        available_white_balance="unknown",
        wb_multipliers=None,
        black_level=None,
        white_level=None,
        color_matrix_hint=None,
        iso=None,
        exposure_time_seconds=None,
        lens_model=None,
        capture_datetime=None,
        dimensions=None,
        intermediate_working_space="scene_linear_camera_rgb",
    )
