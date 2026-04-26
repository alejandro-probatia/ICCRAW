from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import hashlib
import json
import subprocess
import shutil
import tempfile
from typing import Any
import numpy as np
import colour

from ..core.models import BatchManifest, BatchManifestEntry, Recipe
from ..core.external import external_tool_path, run_external
from ..core.utils import list_raw_files, sha256_file, write_tiff16
from ..provenance.c2pa import (
    C2PASignConfig,
    C2PASigningError,
    build_render_settings,
    sign_tiff_with_c2pa,
)
from ..provenance.nexoraw_proof import (
    NexoRawProofConfig,
    NexoRawProofResult,
    proof_config_from_environment,
    sign_nexoraw_proof,
)
from ..raw.pipeline import develop_scene_linear_array, render_recipe_output_array
from ..version import __version__


D50_XY = np.asarray(colour.CCS_ILLUMINANTS["CIE 1931 2 Degree Standard Observer"]["D50"], dtype=np.float64)


def batch_develop(
    raws_dir: Path,
    recipe: Recipe,
    profile_path: Path,
    out_dir: Path,
    *,
    c2pa_config: C2PASignConfig | None = None,
    proof_config: NexoRawProofConfig | None = None,
) -> BatchManifest:
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
    proof_sign_config = proof_config or proof_config_from_environment()

    recipe_sha = hashlib.sha256(json.dumps(asdict(recipe), sort_keys=True).encode("utf-8")).hexdigest()

    entries: list[BatchManifestEntry] = []

    for raw in files:
        out_final, out_linear = _versioned_batch_paths(out_dir, linear_audit_dir, raw.stem)

        scene_linear = develop_scene_linear_array(raw, recipe)
        write_tiff16(out_linear, scene_linear)
        # Render final output from the in-memory array to avoid a second TIFF
        # quantization/read cycle. The audit TIFF is still written and hashed in
        # the manifest, preserving the forensic artifact.
        image = render_recipe_output_array(scene_linear, recipe)
        write_mode, proof_result = write_signed_profiled_tiff(
            out_final,
            image,
            source_raw=raw,
            recipe=recipe,
            profile_path=profile_path,
            c2pa_config=c2pa_config,
            proof_config=proof_sign_config,
            render_context={"entrypoint": "batch_develop", "linear_audit_tiff": str(out_linear)},
        )

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
                proof_path=proof_result.proof_path,
                proof_sha256=proof_result.proof_sha256,
                c2pa_embedded=bool(c2pa_config),
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


def _versioned_batch_paths(out_dir: Path, linear_audit_dir: Path, stem: str) -> tuple[Path, Path]:
    for index in range(1, 10000):
        version = "" if index == 1 else f"_v{index:03d}"
        out_final = out_dir / f"{stem}{version}.tiff"
        out_linear = linear_audit_dir / f"{stem}{version}.scene_linear.tiff"
        if not out_final.exists() and not out_linear.exists():
            return out_final, out_linear
    raise RuntimeError(f"No se pudo generar una version de salida libre para: {stem}")


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
        _write_converted_srgb_tiff_with_argyll(out_tiff, image_linear_rgb, input_profile=profile_path)
        return mode

    raise RuntimeError(f"Modo de gestion de color no soportado: {mode}")


def write_signed_profiled_tiff(
    out_tiff: Path,
    image_linear_rgb: np.ndarray,
    *,
    source_raw: Path,
    recipe: Recipe,
    profile_path: Path | None,
    c2pa_config: C2PASignConfig | None = None,
    proof_config: NexoRawProofConfig | None = None,
    detail_adjustments: dict[str, Any] | None = None,
    render_adjustments: dict[str, Any] | None = None,
    render_context: dict[str, Any] | None = None,
) -> tuple[str, NexoRawProofResult]:
    proof_sign_config = proof_config or proof_config_from_environment()
    out_tiff = Path(out_tiff)
    out_tiff.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{out_tiff.stem}.nexoraw_", dir=out_tiff.parent) as tmp:
        staged_tiff = Path(tmp) / out_tiff.name
        mode = write_profiled_tiff(staged_tiff, image_linear_rgb, recipe=recipe, profile_path=profile_path)
        settings = build_render_settings(
            recipe=recipe,
            profile_path=profile_path,
            color_management_mode=mode,
            detail_adjustments=detail_adjustments,
            render_adjustments=render_adjustments,
            context=render_context,
        )
        c2pa_status: dict[str, Any] = {"embedded": False, "status": "not_configured"}
        if c2pa_config is not None:
            try:
                c2pa_result = sign_tiff_with_c2pa(
                    staged_tiff,
                    source_raw=source_raw,
                    recipe=recipe,
                    profile_path=profile_path,
                    color_management_mode=mode,
                    config=c2pa_config,
                    render_settings=settings,
                )
                c2pa_status = {
                    "embedded": True,
                    "status": "signed",
                    "output_sha256_after_signing": c2pa_result.output_sha256_after_signing,
                }
            except C2PASigningError:
                raise
        shutil.move(str(staged_tiff), str(out_tiff))
        try:
            proof_result = sign_nexoraw_proof(
                output_tiff=out_tiff,
                source_raw=source_raw,
                recipe=recipe,
                profile_path=profile_path,
                color_management_mode=mode,
                render_settings=settings,
                config=proof_sign_config,
                c2pa_embedded=bool(c2pa_config),
                c2pa_status=c2pa_status,
            )
        except Exception:
            out_tiff.unlink(missing_ok=True)
            default_proof = out_tiff.with_suffix(out_tiff.suffix + ".nexoraw.proof.json")
            default_proof.unlink(missing_ok=True)
            raise
        return mode, proof_result


def _write_converted_srgb_tiff_with_argyll(out_tiff: Path, image_linear_rgb: np.ndarray, *, input_profile: Path) -> None:
    cctiff = external_tool_path("cctiff")
    if cctiff is None:
        raise RuntimeError(
            "No se puede convertir ICC: 'cctiff' de ArgyllCMS no esta disponible en PATH. "
            "Instala ArgyllCMS completo o configura su directorio bin."
        )
    srgb_icc = _argyll_reference_profile("sRGB.icm")

    out_tiff.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="nexoraw_argyll_cctiff_") as tmp:
        tmpdir = Path(tmp)
        source_tiff = tmpdir / "camera_rgb_input.tiff"

        write_tiff16(source_tiff, image_linear_rgb)

        cmd = [
            cctiff,
            "-N",  # uncompressed TIFF, reproducible and readable without optional codecs
            "-p",  # precise correction path
            "-ir",
            str(input_profile),
            str(srgb_icc),
            "-e",
            str(srgb_icc),
            str(source_tiff),
            str(out_tiff),
        ]
        proc = run_external(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"cctiff retorno {proc.returncode}: {proc.stdout[-800:]}")


def _argyll_reference_profile(name: str) -> Path:
    for command in ("cctiff", "xicclu", "colprof"):
        tool = external_tool_path(command)
        if not tool:
            continue
        candidate = Path(tool).resolve().parent.parent / "ref" / name
        if candidate.exists():
            return candidate
    raise RuntimeError(f"No se encontro el perfil de referencia de ArgyllCMS: {name}")


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
