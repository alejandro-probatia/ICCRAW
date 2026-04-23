from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import hashlib
import json
import numpy as np
import colour

from .models import BatchManifest, BatchManifestEntry, Recipe
from .pipeline import develop_controlled
from .profiling import load_profile_model
from .utils import list_raw_files, read_image, sha256_file, write_tiff16


def batch_develop(raws_dir: Path, recipe: Recipe, profile_path: Path, out_dir: Path) -> BatchManifest:
    out_dir.mkdir(parents=True, exist_ok=True)
    files = list_raw_files(raws_dir)
    if not files:
        files = sorted(
            [
                p
                for p in raws_dir.iterdir()
                if p.is_file() and p.suffix.lower() in {".tif", ".tiff", ".png", ".jpg", ".jpeg"}
            ]
        )
    if not files:
        raise RuntimeError(f"No se encontraron RAWs ni imagenes compatibles en: {raws_dir}")

    profile_model = load_profile_model(profile_path)
    matrix = np.asarray(profile_model["matrix_camera_to_xyz"], dtype=np.float64)
    icc_bytes = profile_path.read_bytes() if profile_path.exists() else None

    recipe_sha = hashlib.sha256(json.dumps(asdict(recipe), sort_keys=True).encode("utf-8")).hexdigest()

    entries: list[BatchManifestEntry] = []

    for raw in files:
        out_linear = out_dir / f"{raw.stem}.linear.tiff"
        out_final = out_dir / f"{raw.stem}.tiff"

        develop_controlled(raw, recipe, out_linear, None)
        image = read_image(out_linear)
        corrected = apply_profile_matrix(image, matrix, recipe.output_space, recipe.output_linear)
        write_tiff16(out_final, corrected, icc_profile=icc_bytes)

        entries.append(
            BatchManifestEntry(
                source_raw=str(raw),
                source_sha256=sha256_file(raw),
                output_tiff=str(out_final),
                output_sha256=sha256_file(out_final),
                profile_path=str(profile_path),
            )
        )

    return BatchManifest(
        recipe_sha256=recipe_sha,
        profile_path=str(profile_path),
        software_version="0.1.0-python",
        entries=entries,
    )


def apply_profile_matrix(
    image_linear_rgb: np.ndarray,
    matrix_camera_to_xyz: np.ndarray,
    output_space: str,
    output_linear: bool,
) -> np.ndarray:
    h, w, _ = image_linear_rgb.shape
    flat = image_linear_rgb.reshape(-1, 3).astype(np.float64)

    xyz = flat @ matrix_camera_to_xyz

    space = output_space.lower()
    if space in {"srgb", "s_rgb", "s-rgb"}:
        rgb = colour.XYZ_to_sRGB(
            xyz,
            illuminant=colour.CCS_ILLUMINANTS["CIE 1931 2 Degree Standard Observer"]["D65"],
            apply_cctf_encoding=(not output_linear),
        )
        out = np.clip(rgb, 0.0, 1.0)
    elif space in {"scene_linear_camera_rgb", "camera_rgb", "camera"}:
        # Keep mapped XYZ projected back to linear sRGB primaries for practical TIFF export.
        rgb_linear = colour.XYZ_to_sRGB(xyz, apply_cctf_encoding=False)
        out = np.clip(rgb_linear, 0.0, 1.0)
    else:
        rgb_linear = colour.XYZ_to_sRGB(xyz, apply_cctf_encoding=(not output_linear))
        out = np.clip(rgb_linear, 0.0, 1.0)

    return out.reshape(h, w, 3).astype(np.float32)


# Backward-compat alias kept to avoid breaking external scripts that imported
# the previous private name before it was promoted to public API.
_apply_profile_matrix = apply_profile_matrix
