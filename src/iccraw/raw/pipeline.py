from __future__ import annotations

from pathlib import Path
import subprocess
import shutil
import tempfile
import numpy as np

from ..core.models import DevelopResult, Recipe
from ..core.recipe import scientific_guard
from ..core.utils import read_image, write_tiff16
from .metadata import raw_info


DCRAW_QUALITY_MAP = {
    # dcraw -q:
    # 0: linear, 1: VNG, 2: PPG, 3: AHD.
    "linear": "0",
    "vng": "1",
    "ppg": "2",
    "ahd": "3",
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
    if developer in {"", "dcraw", "dcraw-cli"}:
        return _develop_with_dcraw(input_path, recipe)
    raise RuntimeError(f"raw_developer no soportado: {recipe.raw_developer}. Usa 'dcraw'.")


def _develop_with_dcraw(input_path: Path, recipe: Recipe) -> np.ndarray:
    if shutil.which("dcraw") is None:
        raise RuntimeError("No se puede revelar RAW: 'dcraw' no esta disponible en PATH.")
    cmd = _build_dcraw_command(input_path, recipe)

    with tempfile.TemporaryDirectory(prefix="iccraw_dcraw_") as tmp:
        out = Path(tmp) / "dcraw_out.tiff"
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            stderr_tail = proc.stderr.decode("utf-8", errors="ignore")[-400:]
            raise RuntimeError(
                "Fallo de decodificacion RAW con dcraw. "
                f"stderr: {stderr_tail}"
            )
        if not proc.stdout:
            raise RuntimeError("dcraw no devolvio datos TIFF en stdout.")
        out.write_bytes(proc.stdout)
        return read_image(out)


def _build_dcraw_command(input_path: Path, recipe: Recipe) -> list[str]:
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
        "0",
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
    return cmd


def dcraw_quality_value(demosaic_algorithm: str) -> str:
    name = str(demosaic_algorithm or "").strip().lower()
    if name not in DCRAW_QUALITY_MAP:
        supported = ", ".join(sorted(DCRAW_QUALITY_MAP))
        raise RuntimeError(
            "demosaic_algorithm no soportado por dcraw: "
            f"{demosaic_algorithm!r}. Valores soportados: {supported}."
        )
    return DCRAW_QUALITY_MAP[name]


def _dcraw_wb(values: list[float] | None) -> list[float] | None:
    if not values:
        return None
    wb = [float(v) for v in values]
    if len(wb) >= 4:
        return [wb[0], wb[1], wb[2], wb[3]]
    if len(wb) == 3:
        # dcraw expects R G B G.
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
