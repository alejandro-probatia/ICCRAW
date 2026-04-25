from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import hashlib
import json
import subprocess
import tempfile
import numpy as np
import colour
from PIL import ImageCms

from ..core.models import BatchManifest, BatchManifestEntry, Recipe
from ..core.external import external_tool_path
from ..core.utils import list_raw_files, sha256_file, write_tiff16
from ..raw.pipeline import develop_scene_linear_array, render_recipe_output_array
from ..version import __version__


D50_XY = np.asarray(colour.CCS_ILLUMINANTS["CIE 1931 2 Degree Standard Observer"]["D50"], dtype=np.float64)


def batch_develop(raws_dir: Path, recipe: Recipe, profile_path: Path, out_dir: Path) -> BatchManifest:
    out_dir.mkdir(parents=True, exist_ok=True)
    linear_audit_dir = out_dir / "_linear_audit"
    linear_audit_dir.mkdir(parents=True, exist_ok=True)
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

    if not profile_path.exists():
        raise FileNotFoundError(f"No existe perfil ICC: {profile_path}")

    color_mode = color_management_mode(recipe)

    recipe_sha = hashlib.sha256(json.dumps(asdict(recipe), sort_keys=True).encode("utf-8")).hexdigest()

    entries: list[BatchManifestEntry] = []

    for raw in files:
        out_linear = linear_audit_dir / f"{raw.stem}.scene_linear.tiff"
        out_final = out_dir / f"{raw.stem}.tiff"

        scene_linear = develop_scene_linear_array(raw, recipe)
        write_tiff16(out_linear, scene_linear)
        # Render final output from the in-memory array to avoid a second TIFF
        # quantization/read cycle. The audit TIFF is still written and hashed in
        # the manifest, preserving the forensic artifact.
        image = render_recipe_output_array(scene_linear, recipe)
        write_profiled_tiff(out_final, image, recipe=recipe, profile_path=profile_path)

        entries.append(
            BatchManifestEntry(
                source_raw=str(raw),
                source_sha256=sha256_file(raw),
                output_tiff=str(out_final),
                output_sha256=sha256_file(out_final),
                profile_path=str(profile_path),
                color_management_mode=color_mode,
                output_color_space=recipe.output_space,
                linear_audit_tiff=str(out_linear),
            )
        )

    return BatchManifest(
        recipe_sha256=recipe_sha,
        profile_path=str(profile_path),
        color_management_mode=color_mode,
        output_color_space=recipe.output_space,
        software_version=__version__,
        entries=entries,
    )


def color_management_mode(recipe: Recipe) -> str:
    space = recipe.output_space.strip().lower()
    if space in {"scene_linear_camera_rgb", "camera_rgb", "camera"}:
        return "camera_rgb_with_input_icc"
    if space in {"srgb", "s_rgb", "s-rgb"}:
        if recipe.output_linear:
            raise RuntimeError(
                "output_space=srgb requiere output_linear=false para conversion ICC "
                "con perfil sRGB estandar. Linear sRGB necesita un perfil de salida "
                "explicito que aun no esta implementado."
            )
        return "converted_srgb"
    raise RuntimeError(
        f"output_space no soportado para export ICC: {recipe.output_space!r}. "
        "Valores soportados: scene_linear_camera_rgb, camera_rgb, camera, srgb."
    )


def write_profiled_tiff(
    out_tiff: Path,
    image_linear_rgb: np.ndarray,
    *,
    recipe: Recipe,
    profile_path: Path | None,
) -> str:
    if profile_path is None:
        write_tiff16(out_tiff, image_linear_rgb)
        return "no_profile"

    if not profile_path.exists():
        raise FileNotFoundError(f"No existe perfil ICC: {profile_path}")

    mode = color_management_mode(recipe)
    if mode == "camera_rgb_with_input_icc":
        write_tiff16(out_tiff, image_linear_rgb, icc_profile=profile_path.read_bytes())
        return mode

    if mode == "converted_srgb":
        _write_converted_srgb_tiff(out_tiff, image_linear_rgb, input_profile=profile_path)
        return mode

    raise RuntimeError(f"Modo de gestion de color no soportado: {mode}")


def _write_converted_srgb_tiff(out_tiff: Path, image_linear_rgb: np.ndarray, *, input_profile: Path) -> None:
    tificc = external_tool_path("tificc")
    if tificc is None:
        raise RuntimeError(
            "No se puede convertir ICC: 'tificc' no esta disponible en PATH. "
            "Instala LittleCMS tools (por ejemplo, paquete liblcms2-utils)."
        )

    out_tiff.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="nexoraw_lcms_") as tmp:
        tmpdir = Path(tmp)
        source_tiff = tmpdir / "camera_rgb_input.tiff"
        srgb_icc = tmpdir / "srgb.icc"

        write_tiff16(source_tiff, image_linear_rgb)
        _write_srgb_profile(srgb_icc)

        cmd = [
            tificc,
            f"-i{input_profile}",
            f"-o{srgb_icc}",
            "-t1",
            "-b",
            "-w16",
            "-e",
            str(source_tiff),
            str(out_tiff),
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"tificc retorno {proc.returncode}: {proc.stdout[-500:]}")


def _write_srgb_profile(path: Path) -> None:
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
    path.write_bytes(profile.tobytes())


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
            illuminant=D50_XY,
            apply_cctf_encoding=(not output_linear),
        )
        out = np.clip(rgb, 0.0, 1.0)
    elif space in {"scene_linear_camera_rgb", "camera_rgb", "camera"}:
        # Keep mapped XYZ projected back to linear sRGB primaries for practical TIFF export.
        rgb_linear = colour.XYZ_to_sRGB(xyz, illuminant=D50_XY, apply_cctf_encoding=False)
        out = np.clip(rgb_linear, 0.0, 1.0)
    else:
        rgb_linear = colour.XYZ_to_sRGB(xyz, illuminant=D50_XY, apply_cctf_encoding=(not output_linear))
        out = np.clip(rgb_linear, 0.0, 1.0)

    return out.reshape(h, w, 3).astype(np.float32)


# Backward-compat alias kept to avoid breaking external scripts that imported
# the previous private name before it was promoted to public API.
_apply_profile_matrix = apply_profile_matrix
