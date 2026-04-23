from __future__ import annotations

from pathlib import Path
import subprocess
import shutil
import tempfile
import numpy as np
import rawpy

from .models import DevelopResult, Recipe
from .raw import raw_info
from .recipe import scientific_guard
from .utils import read_image, write_tiff16


DEMOSAIC_MAP = {
    "linear": rawpy.DemosaicAlgorithm.LINEAR,
    "vng": rawpy.DemosaicAlgorithm.VNG,
    "ppg": rawpy.DemosaicAlgorithm.PPG,
    "ahd": rawpy.DemosaicAlgorithm.AHD,
    "dcb": rawpy.DemosaicAlgorithm.DCB,
    "dht": rawpy.DemosaicAlgorithm.DHT,
    "aa_hd": rawpy.DemosaicAlgorithm.AAHD,
}


RAW_SUFFIXES = {".raw", ".cr2", ".cr3", ".nef", ".arw", ".dng", ".raf", ".rw2", ".orf", ".pef"}


def develop_controlled(input_path: Path, recipe: Recipe, out_tiff: Path, audit_linear_tiff: Path | None = None) -> DevelopResult:
    metadata = raw_info(input_path) if input_path.suffix.lower() in RAW_SUFFIXES else _fake_metadata(input_path)
    guard = scientific_guard(recipe)

    image = _develop_image(input_path, recipe)

    if recipe.exposure_compensation != 0.0:
        image = np.clip(image * (2.0 ** float(recipe.exposure_compensation)), 0.0, 1.0)

    if recipe.tone_curve.lower() == "srgb":
        image = _apply_srgb_oetf(image)
    elif recipe.tone_curve.lower().startswith("gamma:"):
        gamma = float(recipe.tone_curve.split(":", 1)[1])
        image = np.clip(np.power(np.clip(image, 0.0, 1.0), 1.0 / gamma), 0.0, 1.0)

    write_tiff16(out_tiff, image)

    audit_path_str: str | None = None
    if audit_linear_tiff is not None:
        write_tiff16(audit_linear_tiff, image)
        audit_path_str = str(audit_linear_tiff)

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

    demosaic = DEMOSAIC_MAP.get(recipe.demosaic_algorithm.lower(), rawpy.DemosaicAlgorithm.AHD)
    use_camera_wb = recipe.white_balance_mode.lower() == "camera_metadata"
    no_auto_bright = True

    user_wb = None
    if recipe.white_balance_mode.lower() == "fixed" and recipe.wb_multipliers:
        vals = recipe.wb_multipliers
        if len(vals) == 4:
            user_wb = [float(vals[0]), float(vals[1]), float(vals[3])]
        elif len(vals) == 3:
            user_wb = [float(vals[0]), float(vals[1]), float(vals[2])]

    gamma = (1.0, 1.0) if recipe.output_linear else (2.222, 4.5)

    try:
        with rawpy.imread(str(input_path)) as raw:
            user_black = None
            user_sat = None
            mode = recipe.black_level_mode.lower()
            if mode.startswith("fixed:"):
                user_black = int(mode.split(":", 1)[1])
            if mode.startswith("white:"):
                user_sat = int(mode.split(":", 1)[1])

            rgb = raw.postprocess(
                output_bps=16,
                gamma=gamma,
                no_auto_bright=no_auto_bright,
                use_auto_wb=False,
                use_camera_wb=use_camera_wb,
                user_wb=user_wb,
                demosaic_algorithm=demosaic,
                user_black=user_black,
                user_sat=user_sat,
                highlight_mode=rawpy.HighlightMode.Clip,
                fbdd_noise_reduction=rawpy.FBDDNoiseReductionMode.Off,
            )
        return rgb.astype(np.float32) / 65535.0
    except Exception:
        return _develop_with_dcraw(input_path, recipe)


def _develop_with_dcraw(input_path: Path, recipe: Recipe) -> np.ndarray:
    if shutil.which("dcraw") is None:
        raise RuntimeError("No se pudo decodificar RAW: rawpy fallo y dcraw no esta disponible")

    q_map = {"linear": "0", "vng": "1", "ppg": "2", "ahd": "3"}
    q = q_map.get(recipe.demosaic_algorithm.lower(), "3")

    with tempfile.TemporaryDirectory(prefix="icc_entrada_dcraw_") as tmp:
        out = Path(tmp) / "dcraw_out.tiff"
        cmd = ["dcraw", "-T", "-4", "-o", "0", "-q", q]
        if recipe.white_balance_mode.lower() == "camera_metadata":
            cmd.append("-w")
        if recipe.white_balance_mode.lower() == "fixed" and recipe.wb_multipliers:
            wb = recipe.wb_multipliers
            if len(wb) >= 3:
                cmd.extend(["-r", str(wb[0]), str(wb[1]), str(wb[2]), str(wb[1])])
        cmd.extend(["-c", str(input_path)])

        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            raise RuntimeError(
                "No se pudo decodificar RAW con rawpy ni dcraw. "
                f"dcraw stderr: {proc.stderr.decode('utf-8', errors='ignore')[-200:]}"
            )
        out.write_bytes(proc.stdout)
        return read_image(out)


def _apply_srgb_oetf(x: np.ndarray) -> np.ndarray:
    a = 0.055
    out = np.where(x <= 0.0031308, 12.92 * x, (1 + a) * np.power(np.clip(x, 0.0, 1.0), 1 / 2.4) - a)
    return np.clip(out, 0.0, 1.0)


def _fake_metadata(path: Path):
    from .models import RawMetadata
    from .utils import sha256_file

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
