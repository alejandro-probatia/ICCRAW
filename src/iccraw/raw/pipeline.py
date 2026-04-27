from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile

import numpy as np

from ..core.models import DevelopResult, Recipe
from ..core.recipe import scientific_guard
from ..core.utils import read_image, write_tiff16
from .compat import open_rawpy, rawpy
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

GPL2_DEMOSAIC_ALGORITHMS = {"afd", "lmmse", "modified_ahd", "vcd", "vcd_modified_ahd"}
GPL3_DEMOSAIC_ALGORITHMS = {"amaze"}


RAW_SUFFIXES = {".raw", ".cr2", ".cr3", ".nef", ".arw", ".dng", ".raf", ".rw2", ".orf", ".pef"}
DEMOSAIC_CACHE_SCHEMA = "nexoraw-demosaic-cache-v2"
DEMOSAIC_CACHE_MAX_GB_ENV = "NEXORAW_DEMOSAIC_CACHE_MAX_GB"
LEGACY_DEMOSAIC_CACHE_MAX_GB_ENV = "ICCRAW_DEMOSAIC_CACHE_MAX_GB"
DEFAULT_DEMOSAIC_CACHE_MAX_GB = 5.0

STANDARD_OUTPUT_ALIASES = {
    "srgb": "srgb",
    "s_rgb": "srgb",
    "s-rgb": "srgb",
    "adobe_rgb": "adobe_rgb",
    "adobergb": "adobe_rgb",
    "adobe-rgb": "adobe_rgb",
    "adobe_rgb_1998": "adobe_rgb",
    "adobe-rgb-1998": "adobe_rgb",
    "adobe rgb (1998)": "adobe_rgb",
    "prophoto": "prophoto_rgb",
    "prophoto_rgb": "prophoto_rgb",
    "prophoto-rgb": "prophoto_rgb",
    "romm_rgb": "prophoto_rgb",
    "romm-rgb": "prophoto_rgb",
}


def develop_controlled(
    input_path: Path,
    recipe: Recipe,
    out_tiff: Path,
    audit_linear_tiff: Path | None = None,
    *,
    cache_dir: Path | None = None,
) -> DevelopResult:
    metadata = raw_info(input_path) if input_path.suffix.lower() in RAW_SUFFIXES else _fake_metadata(input_path)
    guard = scientific_guard(recipe)

    image = (
        develop_standard_linear_array(input_path, recipe, cache_dir=cache_dir)
        if is_standard_output_space(recipe.output_space)
        else develop_scene_linear_array(input_path, recipe, cache_dir=cache_dir)
    )

    audit_path_str: str | None = None
    if audit_linear_tiff is not None:
        write_tiff16(audit_linear_tiff, image)
        audit_path_str = str(audit_linear_tiff)

    image = render_recipe_output_array(image, recipe)

    write_tiff16(out_tiff, image)

    return DevelopResult(
        raw_metadata=metadata,
        recipe=recipe,
        scientific_guard=guard,
        output_tiff=str(out_tiff),
        audit_tiff=audit_path_str,
    )


def _develop_image(input_path: Path, recipe: Recipe) -> np.ndarray:
    return develop_scene_linear_array(input_path, recipe)


def develop_scene_linear_array(
    input_path: Path,
    recipe: Recipe,
    *,
    half_size: bool = False,
    cache_dir: Path | None = None,
) -> np.ndarray:
    if input_path.suffix.lower() not in RAW_SUFFIXES:
        return read_image(input_path)

    developer = recipe.raw_developer.strip().lower()
    if developer not in {"", "libraw", "rawpy"}:
        raise RuntimeError(f"raw_developer no soportado: {recipe.raw_developer}. Usa 'libraw'.")
    if bool(getattr(recipe, "use_cache", False)) and not half_size and cache_dir is not None:
        cached = _read_demosaic_cache(input_path, recipe, cache_dir, output_color_space="camera_raw")
        if cached is not None:
            return cached
        image = develop_with_libraw(input_path, recipe, half_size=half_size, output_color_space="camera_raw")
        _write_demosaic_cache(input_path, recipe, cache_dir, image, output_color_space="camera_raw")
        _prune_demosaic_cache(cache_dir)
        return image
    return develop_with_libraw(input_path, recipe, half_size=half_size, output_color_space="camera_raw")


def develop_standard_linear_array(
    input_path: Path,
    recipe: Recipe,
    *,
    half_size: bool = False,
    cache_dir: Path | None = None,
) -> np.ndarray:
    output_space = canonical_standard_output_space(recipe.output_space)
    if output_space is None:
        raise RuntimeError(
            f"output_space no es un espacio RGB estandar soportado: {recipe.output_space!r}"
        )
    if input_path.suffix.lower() not in RAW_SUFFIXES:
        return read_image(input_path)

    developer = recipe.raw_developer.strip().lower()
    if developer not in {"", "libraw", "rawpy"}:
        raise RuntimeError(f"raw_developer no soportado: {recipe.raw_developer}. Usa 'libraw'.")
    if bool(getattr(recipe, "use_cache", False)) and not half_size and cache_dir is not None:
        cached = _read_demosaic_cache(input_path, recipe, cache_dir, output_color_space=output_space)
        if cached is not None:
            return cached
        image = develop_with_libraw(input_path, recipe, half_size=half_size, output_color_space=output_space)
        _write_demosaic_cache(input_path, recipe, cache_dir, image, output_color_space=output_space)
        _prune_demosaic_cache(cache_dir)
        return image
    return develop_with_libraw(input_path, recipe, half_size=half_size, output_color_space=output_space)


def render_recipe_output_array(image_linear_rgb: np.ndarray, recipe: Recipe) -> np.ndarray:
    image = np.clip(image_linear_rgb.astype(np.float32), 0.0, 1.0)

    if recipe.exposure_compensation != 0.0:
        image = np.clip(image * (2.0 ** float(recipe.exposure_compensation)), 0.0, 1.0)

    tone_curve = recipe.tone_curve.lower()
    if tone_curve == "srgb":
        image = _apply_srgb_oetf(image)
    elif tone_curve.startswith("gamma:"):
        gamma = float(tone_curve.split(":", 1)[1])
        image = np.clip(np.power(np.clip(image, 0.0, 1.0), 1.0 / gamma), 0.0, 1.0)

    return np.clip(image, 0.0, 1.0).astype(np.float32)


def develop_image_array(
    input_path: Path,
    recipe: Recipe,
    *,
    half_size: bool = False,
    cache_dir: Path | None = None,
) -> np.ndarray:
    image = develop_scene_linear_array(input_path, recipe, half_size=half_size, cache_dir=cache_dir)
    return render_recipe_output_array(image, recipe)


def develop_standard_output_array(
    input_path: Path,
    recipe: Recipe,
    *,
    half_size: bool = False,
    cache_dir: Path | None = None,
) -> np.ndarray:
    image = develop_standard_linear_array(input_path, recipe, half_size=half_size, cache_dir=cache_dir)
    return render_recipe_output_array(image, recipe)


def develop_with_libraw(
    input_path: Path,
    recipe: Recipe,
    *,
    half_size: bool = False,
    output_color_space: str = "camera_raw",
) -> np.ndarray:
    if rawpy is None:
        raise RuntimeError("No se puede revelar RAW: dependencia 'rawpy'/'LibRaw' no disponible.")

    kwargs = _build_libraw_postprocess_kwargs(recipe, half_size=half_size, output_color_space=output_color_space)
    try:
        with open_rawpy(input_path, unpack=True) as raw:
            image = raw.postprocess(**kwargs)
    except Exception as exc:
        raise RuntimeError(f"Fallo de decodificacion RAW con LibRaw/rawpy: {exc}") from exc
    return _postprocess_output_to_float(image)


def _build_libraw_postprocess_kwargs(
    recipe: Recipe,
    *,
    half_size: bool = False,
    output_color_space: str = "camera_raw",
) -> dict:
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
        "output_color": _libraw_output_color_value(output_color_space),
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


def canonical_standard_output_space(output_space: str | None) -> str | None:
    key = str(output_space or "").strip().lower()
    return STANDARD_OUTPUT_ALIASES.get(key)


def is_standard_output_space(output_space: str | None) -> bool:
    return canonical_standard_output_space(output_space) is not None


def _libraw_output_color_value(output_color_space: str):
    if rawpy is None:
        raise RuntimeError("No se puede configurar LibRaw: dependencia 'rawpy' no disponible.")
    key = str(output_color_space or "camera_raw").strip().lower()
    if key in {"camera_raw", "raw", "camera", "camera_rgb", "scene_linear_camera_rgb"}:
        return rawpy.ColorSpace.raw
    key = canonical_standard_output_space(key)
    if key == "srgb":
        return rawpy.ColorSpace.sRGB
    if key == "adobe_rgb":
        return rawpy.ColorSpace.Adobe
    if key == "prophoto_rgb":
        return rawpy.ColorSpace.ProPhoto
    raise RuntimeError(f"output_color_space no soportado por LibRaw/rawpy: {output_color_space!r}")


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
    reason = unavailable_demosaic_reason(name)
    if reason is not None:
        raise RuntimeError(reason)
    enum_name = LIBRAW_DEMOSAIC_MAP[name]
    return getattr(rawpy.DemosaicAlgorithm, enum_name)


def rawpy_feature_flags() -> dict[str, bool]:
    if rawpy is None:
        return {}
    flags = getattr(rawpy, "flags", None)
    if not isinstance(flags, dict):
        return {}
    return {str(key): bool(value) for key, value in flags.items()}


def is_libraw_demosaic_supported(demosaic_algorithm: str) -> bool:
    return unavailable_demosaic_reason(demosaic_algorithm) is None


def unavailable_demosaic_reason(demosaic_algorithm: str) -> str | None:
    if rawpy is None:
        return "No se puede configurar demosaicing: dependencia 'rawpy' no disponible."

    name = str(demosaic_algorithm or "").strip().lower()
    if name not in LIBRAW_DEMOSAIC_MAP:
        supported = ", ".join(sorted(LIBRAW_DEMOSAIC_MAP))
        return (
            "demosaic_algorithm no soportado por LibRaw/rawpy: "
            f"{demosaic_algorithm!r}. Valores soportados: {supported}."
        )

    flags = rawpy_feature_flags()
    if not flags:
        return None
    if name in GPL3_DEMOSAIC_ALGORITHMS and not flags.get("DEMOSAIC_PACK_GPL3", False):
        return (
            "El algoritmo AMaZE requiere el demosaic pack GPL3 de LibRaw. "
            "Instala rawpy-demosaic o compila rawpy/LibRaw con "
            "LIBRAW_DEMOSAIC_PACK_GPL3; la build actual informa "
            "DEMOSAIC_PACK_GPL3=False."
        )
    if name in GPL2_DEMOSAIC_ALGORITHMS and not flags.get("DEMOSAIC_PACK_GPL2", False):
        return (
            f"El algoritmo {demosaic_algorithm} requiere el demosaic pack GPL2 de LibRaw. "
            "Instala rawpy-demosaic o compila rawpy/LibRaw con "
            "LIBRAW_DEMOSAIC_PACK_GPL2; la build actual informa "
            "DEMOSAIC_PACK_GPL2=False."
        )
    return None


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


def _demosaic_cache_key(raw_path: Path, recipe: Recipe, *, output_color_space: str = "camera_raw") -> str:
    path = Path(raw_path)
    st = path.stat()
    h = hashlib.sha256()
    raw_sha = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            raw_sha.update(chunk)
    payload = {
        "schema": DEMOSAIC_CACHE_SCHEMA,
        "name": path.name,
        "size": int(st.st_size),
        "sha256": raw_sha.hexdigest(),
        "raw_developer": str(recipe.raw_developer),
        "demosaic_algorithm": str(recipe.demosaic_algorithm),
        "white_balance_mode": str(recipe.white_balance_mode),
        "wb_multipliers": [float(v) for v in (recipe.wb_multipliers or [])],
        "black_level_mode": str(recipe.black_level_mode),
        "output_color_space": str(output_color_space),
        "rawpy": str(getattr(rawpy, "__version__", "")) if rawpy is not None else "missing",
        "libraw": str(getattr(rawpy, "libraw_version", "")) if rawpy is not None else "missing",
        "flags": rawpy_feature_flags(),
    }
    h.update(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return h.hexdigest()


def _demosaic_cache_path(
    raw_path: Path,
    recipe: Recipe,
    cache_root: Path,
    *,
    output_color_space: str = "camera_raw",
) -> Path:
    key = _demosaic_cache_key(raw_path, recipe, output_color_space=output_color_space)
    return Path(cache_root) / "demosaic" / key[:2] / f"{key}.npy"


def _read_demosaic_cache(
    raw_path: Path,
    recipe: Recipe,
    cache_root: Path,
    *,
    output_color_space: str = "camera_raw",
) -> np.ndarray | None:
    path = _demosaic_cache_path(raw_path, recipe, cache_root, output_color_space=output_color_space)
    try:
        if not path.is_file():
            return None
        with path.open("rb") as handle:
            image = np.load(handle, allow_pickle=False)
        image = np.asarray(image, dtype=np.float32)
        if image.ndim != 3 or image.shape[-1] < 3:
            return None
        try:
            os.utime(path, None)
        except OSError:
            pass
        return np.ascontiguousarray(image[..., :3])
    except Exception:
        return None


def _write_demosaic_cache(
    raw_path: Path,
    recipe: Recipe,
    cache_root: Path,
    image: np.ndarray,
    *,
    output_color_space: str = "camera_raw",
) -> None:
    path = _demosaic_cache_path(raw_path, recipe, cache_root, output_color_space=output_color_space)
    temp_path: Path | None = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        array = np.ascontiguousarray(np.asarray(image, dtype=np.float32)[..., :3])
        with tempfile.NamedTemporaryFile(prefix=path.name, suffix=".tmp", dir=path.parent, delete=False) as handle:
            temp_path = Path(handle.name)
            np.save(handle, array, allow_pickle=False)
        os.replace(temp_path, path)
    except Exception:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass


def _demosaic_cache_max_bytes() -> int:
    raw = os.environ.get(DEMOSAIC_CACHE_MAX_GB_ENV, "").strip() or os.environ.get(
        LEGACY_DEMOSAIC_CACHE_MAX_GB_ENV, ""
    ).strip()
    try:
        gb = float(raw) if raw else DEFAULT_DEMOSAIC_CACHE_MAX_GB
    except ValueError:
        gb = DEFAULT_DEMOSAIC_CACHE_MAX_GB
    return max(0, int(gb * 1024 * 1024 * 1024))


def _prune_demosaic_cache(cache_root: Path) -> None:
    max_bytes = _demosaic_cache_max_bytes()
    if max_bytes <= 0:
        return
    root = Path(cache_root) / "demosaic"
    try:
        files = [p for p in root.glob("*/*.npy") if p.is_file()]
    except Exception:
        return
    entries: list[tuple[float, int, Path]] = []
    total = 0
    for path in files:
        try:
            st = path.stat()
        except OSError:
            continue
        size = int(st.st_size)
        total += size
        entries.append((float(st.st_atime), size, path))
    if total <= max_bytes:
        return
    for _atime, size, path in sorted(entries, key=lambda item: item[0]):
        try:
            path.unlink()
            total -= size
        except OSError:
            pass
        if total <= max_bytes:
            break


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
        embedded_profile_description=None,
        embedded_profile_source=None,
    )
