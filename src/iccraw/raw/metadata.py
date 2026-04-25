from __future__ import annotations

from pathlib import Path
import json
import subprocess
from typing import Any

from ..core.external import external_tool_path

try:
    import rawpy
except Exception:  # pragma: no cover - optional dependency at runtime.
    rawpy = None

from ..core.models import RawMetadata
from ..core.utils import sha256_file


def raw_info(path: Path) -> RawMetadata:
    if not path.exists():
        raise FileNotFoundError(f"RAW no encontrado: {path}")

    exif = _read_exif(path)
    if rawpy is None:
        return _fallback_metadata(path, exif)

    try:
        with rawpy.imread(str(path)) as raw:
            cfa_pattern = _cfa_name(raw)
            wb = raw.camera_whitebalance.tolist() if raw.camera_whitebalance is not None else None
            black_levels = raw.black_level_per_channel.tolist() if raw.black_level_per_channel is not None else None
            black_level = int(round(sum(black_levels) / len(black_levels))) if black_levels else None

            color_matrix_hint = None
            if raw.color_matrix is not None:
                cm = raw.color_matrix
                if cm.ndim == 2:
                    color_matrix_hint = [[float(v) for v in row[:3]] for row in cm[:3]]

            return RawMetadata(
                source_file=str(path),
                input_sha256=sha256_file(path),
                camera_model=exif.get("Model") or exif.get("CameraModelName"),
                cfa_pattern=cfa_pattern,
                available_white_balance="camera_metadata" if wb else "unknown",
                wb_multipliers=[float(v) for v in wb] if wb else None,
                black_level=black_level,
                white_level=int(raw.white_level) if raw.white_level is not None else None,
                color_matrix_hint=color_matrix_hint,
                iso=_to_int(exif.get("ISO")),
                exposure_time_seconds=_to_float(exif.get("ExposureTime")),
                lens_model=exif.get("LensModel") or exif.get("LensID") or exif.get("LensType"),
                capture_datetime=exif.get("DateTimeOriginal") or exif.get("CreateDate"),
                dimensions=[int(raw.sizes.raw_width), int(raw.sizes.raw_height)],
                intermediate_working_space="scene_linear_camera_rgb",
            )
    except Exception:
        return _fallback_metadata(path, exif)


def _read_exif(path: Path) -> dict:
    exiftool = external_tool_path("exiftool")
    if exiftool is None:
        return {}
    try:
        output = subprocess.check_output([exiftool, "-json", str(path)], text=True)
        data = json.loads(output)
        if data and isinstance(data, list):
            return data[0]
    except Exception:
        pass
    return {}


def _to_int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _to_float(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and "/" in value:
        a, b = value.split("/", 1)
        try:
            return float(a) / float(b)
        except Exception:
            return None
    try:
        return float(value)
    except Exception:
        return None


def _fallback_metadata(path: Path, exif: dict[str, Any]) -> RawMetadata:
    return RawMetadata(
        source_file=str(path),
        input_sha256=sha256_file(path),
        camera_model=exif.get("Model") or exif.get("CameraModelName"),
        cfa_pattern="unknown",
        available_white_balance="unknown",
        wb_multipliers=None,
        black_level=None,
        white_level=None,
        color_matrix_hint=None,
        iso=_to_int(exif.get("ISO")),
        exposure_time_seconds=_to_float(exif.get("ExposureTime")),
        lens_model=exif.get("LensModel") or exif.get("LensID") or exif.get("LensType"),
        capture_datetime=exif.get("DateTimeOriginal") or exif.get("CreateDate"),
        dimensions=_extract_dimensions(exif),
        intermediate_working_space="scene_linear_camera_rgb",
    )


def _extract_dimensions(exif: dict[str, Any]) -> list[int] | None:
    width = (
        _to_int(exif.get("RawImageFullWidth"))
        or _to_int(exif.get("ImageWidth"))
        or _to_int(exif.get("ExifImageWidth"))
    )
    height = (
        _to_int(exif.get("RawImageFullHeight"))
        or _to_int(exif.get("ImageHeight"))
        or _to_int(exif.get("ExifImageHeight"))
    )
    if width and height:
        return [int(width), int(height)]
    return None


def _cfa_name(raw) -> str:
    try:
        pattern = raw.raw_pattern
        if pattern is None:
            return "unknown"
        # Common Bayer patterns encoded as matrix indexes 0..3.
        text = "".join(str(int(v)) for v in pattern.flatten().tolist())
        mapping = {
            "0121": "bayer_rggb",
            "1021": "bayer_grbg",
            "1201": "bayer_gbrg",
            "1210": "bayer_bggr",
        }
        return mapping.get(text, "bayer_other")
    except Exception:
        return "unknown"
