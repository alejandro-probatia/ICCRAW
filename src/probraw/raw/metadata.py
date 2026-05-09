from __future__ import annotations

from pathlib import Path
import json
from typing import Any

from ..core.external import check_output_external, external_tool_path
from .compat import open_rawpy, rawpy

from ..core.models import RawMetadata
from ..core.utils import sha256_file


def raw_info(path: Path, *, input_sha256: str | None = None) -> RawMetadata:
    if not path.exists():
        raise FileNotFoundError(f"RAW no encontrado: {path}")

    exif = _read_exif(path)
    if rawpy is None:
        return _fallback_metadata(path, exif, input_sha256=input_sha256)

    try:
        with open_rawpy(path) as raw:
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
                input_sha256=input_sha256 or sha256_file(path),
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
                black_level_per_channel=[int(v) for v in black_levels] if black_levels else None,
                embedded_profile_description=_embedded_profile_description(exif),
                embedded_profile_source=_embedded_profile_source(exif),
            )
    except Exception:
        return _fallback_metadata(path, exif, input_sha256=input_sha256)


def estimate_pixel_pitch_um(
    path: Path,
    *,
    image_dimensions: tuple[int, int] | list[int] | None = None,
) -> tuple[float, str] | None:
    exif = _read_exif(path)
    return estimate_pixel_pitch_um_from_exif(exif, image_dimensions=image_dimensions)


def estimate_pixel_pitch_um_from_exif(
    exif: dict[str, Any],
    *,
    image_dimensions: tuple[int, int] | list[int] | None = None,
) -> tuple[float, str] | None:
    dimensions = _extract_dimensions(exif) or _normalize_dimensions(image_dimensions)
    pitch_from_sensor = _pixel_pitch_from_sensor_size(exif, dimensions)
    if pitch_from_sensor is not None:
        return pitch_from_sensor
    pitch_from_focal_plane = _pixel_pitch_from_focal_plane_resolution(exif)
    if pitch_from_focal_plane is not None:
        return pitch_from_focal_plane
    return _pixel_pitch_from_35mm_equivalent(exif, dimensions)


def _read_exif(path: Path) -> dict:
    exiftool = external_tool_path("exiftool")
    if exiftool is None:
        return {}
    try:
        output = check_output_external([exiftool, "-json", str(path)], text=True, timeout=10)
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


def _fallback_metadata(path: Path, exif: dict[str, Any], *, input_sha256: str | None = None) -> RawMetadata:
    return RawMetadata(
        source_file=str(path),
        input_sha256=input_sha256 or sha256_file(path),
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
        embedded_profile_description=_embedded_profile_description(exif),
        embedded_profile_source=_embedded_profile_source(exif),
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


def _normalize_dimensions(value: tuple[int, int] | list[int] | None) -> list[int] | None:
    if not value or len(value) < 2:
        return None
    try:
        width = int(value[0])
        height = int(value[1])
    except Exception:
        return None
    if width > 0 and height > 0:
        return [width, height]
    return None


def _pixel_pitch_from_sensor_size(
    exif: dict[str, Any],
    dimensions: list[int] | None,
) -> tuple[float, str] | None:
    if not dimensions:
        return None
    width_px, height_px = int(dimensions[0]), int(dimensions[1])
    sensor_width = _metadata_length_mm(
        exif,
        (
            "SensorWidth",
            "Sensor Width",
            "SensorSizeWidth",
            "SensorPhysicalWidth",
            "FocalPlaneXSize",
        ),
    )
    sensor_height = _metadata_length_mm(
        exif,
        (
            "SensorHeight",
            "Sensor Height",
            "SensorSizeHeight",
            "SensorPhysicalHeight",
            "FocalPlaneYSize",
        ),
    )
    candidates: list[float] = []
    if sensor_width is not None and width_px > 0:
        candidates.append(sensor_width * 1000.0 / float(width_px))
    if sensor_height is not None and height_px > 0:
        candidates.append(sensor_height * 1000.0 / float(height_px))
    candidates = [v for v in candidates if 0.1 <= v <= 30.0]
    if not candidates:
        return None
    pitch = float(sum(candidates) / len(candidates))
    source = "sensor_size"
    if sensor_width is not None and sensor_height is not None:
        source = "sensor_width_height"
    elif sensor_width is not None:
        source = "sensor_width"
    elif sensor_height is not None:
        source = "sensor_height"
    return pitch, source


def _pixel_pitch_from_focal_plane_resolution(exif: dict[str, Any]) -> tuple[float, str] | None:
    x_res = _metadata_number(
        exif,
        (
            "FocalPlaneXResolution",
            "Focal Plane X Resolution",
            "FocalPlaneResolutionX",
        ),
    )
    y_res = _metadata_number(
        exif,
        (
            "FocalPlaneYResolution",
            "Focal Plane Y Resolution",
            "FocalPlaneResolutionY",
        ),
    )
    unit_um = _focal_plane_resolution_unit_um(exif.get("FocalPlaneResolutionUnit") or exif.get("Focal Plane Resolution Unit"))
    if unit_um is None:
        return None
    candidates = []
    for value in (x_res, y_res):
        if value is not None and value > 0:
            candidates.append(unit_um / float(value))
    candidates = [v for v in candidates if 0.1 <= v <= 30.0]
    if not candidates:
        return None
    return float(sum(candidates) / len(candidates)), "focal_plane_resolution"


def _pixel_pitch_from_35mm_equivalent(
    exif: dict[str, Any],
    dimensions: list[int] | None,
) -> tuple[float, str] | None:
    if not dimensions:
        return None
    width_px, height_px = int(dimensions[0]), int(dimensions[1])
    if width_px <= 0 or height_px <= 0:
        return None
    scale = _metadata_number(
        exif,
        (
            "ScaleFactor35efl",
            "ScaleFactor35EFL",
            "Scale Factor To 35 mm Equivalent",
        ),
    )
    if scale is None or scale <= 0:
        focal = _metadata_length_mm(exif, ("FocalLength", "Focal Length"))
        focal_35 = _metadata_length_mm(
            exif,
            (
                "FocalLengthIn35mmFormat",
                "FocalLength35efl",
                "FocalLength35EFL",
                "Focal Length In 35mm Format",
            ),
        )
        if focal is not None and focal_35 is not None and focal > 0 and focal_35 > 0:
            scale = focal_35 / focal
    if scale is None or scale <= 0:
        return None

    full_frame_diagonal_mm = 43.266615305567875
    sensor_diagonal_mm = full_frame_diagonal_mm / float(scale)
    aspect = float(width_px) / float(height_px)
    sensor_height_mm = sensor_diagonal_mm / (aspect * aspect + 1.0) ** 0.5
    sensor_width_mm = sensor_height_mm * aspect
    pitch_w = sensor_width_mm * 1000.0 / float(width_px)
    pitch_h = sensor_height_mm * 1000.0 / float(height_px)
    candidates = [v for v in (pitch_w, pitch_h) if 0.1 <= v <= 30.0]
    if not candidates:
        return None
    return float(sum(candidates) / len(candidates)), "35mm_equivalent"


def _metadata_length_mm(exif: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = exif.get(key)
        parsed = _parse_length_mm(value)
        if parsed is not None:
            return parsed
    return None


def _metadata_number(exif: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        parsed = _parse_number(exif.get(key))
        if parsed is not None:
            return parsed
    return None


def _parse_length_mm(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().lower()
    if not text:
        return None
    number = _parse_number(text.split()[0])
    if number is None:
        return None
    if "um" in text or "µm" in text:
        return number / 1000.0
    if "cm" in text:
        return number * 10.0
    if "in" in text or "inch" in text:
        return number * 25.4
    return number


def _parse_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", ".")
    if not text:
        return None
    if "/" in text:
        first = text.split()[0]
        a, b = first.split("/", 1)
        try:
            return float(a) / float(b)
        except Exception:
            return None
    try:
        return float(text.split()[0])
    except Exception:
        return None


def _focal_plane_resolution_unit_um(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        code = int(value)
        if code == 2:
            return 25400.0
        if code == 3:
            return 10000.0
        if code == 4:
            return 1000.0
        if code == 5:
            return 1.0
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    if "inch" in text or "inches" in text:
        return 25400.0
    if text in {"2"}:
        return 25400.0
    if "cm" in text or "centimeter" in text:
        return 10000.0
    if text in {"3"}:
        return 10000.0
    if text == "mm" or "millimeter" in text:
        return 1000.0
    if text in {"4"}:
        return 1000.0
    if text in {"um", "µm", "micrometer", "micrometre", "microns", "5"}:
        return 1.0
    return None


def _embedded_profile_description(exif: dict[str, Any]) -> str | None:
    for key in (
        "ProfileDescription",
        "ICCProfileName",
        "ColorProfile",
        "CurrentICCProfile",
        "EmbeddedProfileName",
    ):
        value = exif.get(key)
        if value:
            return str(value)
    return None


def _embedded_profile_source(exif: dict[str, Any]) -> str | None:
    if _embedded_profile_description(exif):
        return "embedded_or_metadata_profile"
    color_space = str(exif.get("ColorSpace") or "").strip()
    if color_space:
        return f"metadata_color_space:{color_space}"
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
