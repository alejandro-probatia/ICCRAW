from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import sys

import numpy as np
import colour
from colour.adaptation import matrix_chromatic_adaptation_VonKries

from ..core.external import external_tool_path
from .builder import D50_XYZ, build_matrix_shaper_icc


@dataclass(frozen=True)
class GenericRgbProfile:
    key: str
    label: str
    colour_space: str
    gamma: float
    preferred_filenames: tuple[str, ...]
    compatible_filenames: tuple[str, ...] = ()


GENERIC_RGB_PROFILES: dict[str, GenericRgbProfile] = {
    "srgb": GenericRgbProfile(
        key="srgb",
        label="sRGB",
        colour_space="sRGB",
        gamma=2.2,
        preferred_filenames=("sRGB Color Space Profile.icm", "sRGB.icm", "sRGB.icc", "sRGB Profile.icc"),
    ),
    "adobe_rgb": GenericRgbProfile(
        key="adobe_rgb",
        label="Adobe RGB (1998)",
        colour_space="Adobe RGB (1998)",
        gamma=2.19921875,
        preferred_filenames=("AdobeRGB1998.icc", "Adobe RGB (1998).icc", "Adobe RGB 1998.icc"),
        compatible_filenames=("ClayRGB1998.icm",),
    ),
    "prophoto_rgb": GenericRgbProfile(
        key="prophoto_rgb",
        label="ProPhoto RGB",
        colour_space="ProPhoto RGB",
        gamma=1.8,
        preferred_filenames=("ProPhoto.icm", "ProPhoto RGB.icc", "ProPhoto.icc"),
        compatible_filenames=("ProPhoto.icm",),
    ),
}

GENERIC_OUTPUT_ALIASES = {
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


def canonical_generic_output_space(output_space: str | None) -> str | None:
    key = str(output_space or "").strip().lower()
    return GENERIC_OUTPUT_ALIASES.get(key)


def is_generic_output_space(output_space: str | None) -> bool:
    return canonical_generic_output_space(output_space) is not None


def generic_output_profile(output_space: str | None) -> GenericRgbProfile:
    key = canonical_generic_output_space(output_space)
    if key is None:
        supported = ", ".join(profile.key for profile in GENERIC_RGB_PROFILES.values())
        raise RuntimeError(f"Espacio RGB generico no soportado: {output_space!r}. Valores: {supported}.")
    return GENERIC_RGB_PROFILES[key]


def generic_output_profile_path(output_space: str | None, *, directory: Path | None = None) -> Path:
    profile = generic_output_profile(output_space)
    base = directory or (Path.home() / ".cache" / "probraw" / "generic-profiles")
    source = find_standard_output_profile(profile.key)
    filename = source.name if source is not None else profile.preferred_filenames[0]
    return Path(base).expanduser() / filename


def ensure_generic_output_profile(output_space: str | None, *, directory: Path | None = None) -> Path:
    profile = generic_output_profile(output_space)
    source = find_standard_output_profile(profile.key)
    if source is None:
        raise RuntimeError(
            f"No se encontro un perfil ICC estandar para {profile.label}. "
            "Instala ArgyllCMS con su directorio ref, configura PROBRAW_STANDARD_ICC_DIR "
            "o selecciona un perfil ICC estandar del sistema."
        )

    base = directory or (Path.home() / ".cache" / "probraw" / "standard-profiles")
    target = Path(base).expanduser() / source.name
    if target.exists() and target.stat().st_size == source.stat().st_size:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return target


def find_standard_output_profile(output_space: str | None) -> Path | None:
    profile = generic_output_profile(output_space)
    folders = _standard_profile_search_dirs()
    for filenames in (profile.preferred_filenames, profile.compatible_filenames):
        for folder in folders:
            for filename in filenames:
                candidate = folder / filename
                if candidate.exists() and candidate.is_file() and candidate.stat().st_size >= 128:
                    return candidate
    return None


def available_standard_output_profiles(output_space: str | None) -> list[Path]:
    profile = generic_output_profile(output_space)
    folders = _standard_profile_search_dirs()
    matches: list[Path] = []
    seen: set[Path] = set()
    for filenames in (profile.preferred_filenames, profile.compatible_filenames):
        for folder in folders:
            for filename in filenames:
                candidate = folder / filename
                if candidate.exists() and candidate.is_file() and candidate.stat().st_size >= 128:
                    resolved = candidate.resolve(strict=False)
                    if resolved not in seen:
                        seen.add(resolved)
                        matches.append(candidate)
    return matches


def build_generic_output_icc(output_space: str | None) -> bytes:
    """Build a matrix-shaper fallback profile.

    Kept for backward-compatible imports and tests. Runtime export paths use
    real standard ICC profiles from the OS or ArgyllCMS instead of this helper.
    """
    profile = generic_output_profile(output_space)
    rgb_space = colour.RGB_COLOURSPACES[profile.colour_space]
    matrix = _rgb_to_xyz_d50_matrix(rgb_space)
    return build_matrix_shaper_icc(
        description=f"{profile.label} fallback matrix-shaper",
        matrix_camera_to_xyz=matrix,
        gamma=profile.gamma,
    )


def _rgb_to_xyz_d50_matrix(rgb_space: colour.RGB_Colourspace) -> np.ndarray:
    matrix = np.asarray(rgb_space.matrix_RGB_to_XYZ, dtype=np.float64)
    source_white = np.asarray(colour.xy_to_XYZ(rgb_space.whitepoint), dtype=np.float64)
    if np.allclose(source_white, D50_XYZ, atol=1e-6):
        return matrix
    adaptation = matrix_chromatic_adaptation_VonKries(source_white, D50_XYZ, transform="Bradford")
    return np.asarray(adaptation @ matrix, dtype=np.float64)


def _standard_profile_search_dirs() -> list[Path]:
    dirs: list[Path] = []
    configured = os.environ.get("PROBRAW_STANDARD_ICC_DIR", "").strip()
    if configured:
        dirs.append(Path(configured).expanduser())

    dirs.extend(_argyll_reference_dirs())

    if sys.platform == "win32":
        windir = os.environ.get("WINDIR", r"C:\Windows")
        dirs.append(Path(windir) / "System32" / "spool" / "drivers" / "color")
    elif sys.platform == "darwin":
        dirs.extend(
            [
                Path("/System/Library/ColorSync/Profiles"),
                Path("/Library/ColorSync/Profiles"),
                Path.home() / "Library" / "ColorSync" / "Profiles",
            ]
        )
    else:
        dirs.extend(
            [
                Path("/usr/share/color/icc"),
                Path("/usr/share/color/icc/colord"),
                Path("/usr/local/share/color/icc"),
                Path.home() / ".local" / "share" / "color" / "icc",
            ]
        )

    seen: set[Path] = set()
    out: list[Path] = []
    for folder in dirs:
        try:
            resolved = folder.expanduser().resolve(strict=False)
        except Exception:
            resolved = folder
        if resolved not in seen:
            seen.add(resolved)
            out.append(resolved)
    return out


def _argyll_reference_dirs() -> list[Path]:
    dirs: list[Path] = []
    configured = os.environ.get("PROBRAW_ARGYLL_REF_DIR", "").strip()
    if configured:
        dirs.append(Path(configured).expanduser())

    for command in ("cctiff", "xicclu", "colprof"):
        tool = external_tool_path(command)
        if not tool:
            continue
        bin_dir = Path(tool).resolve().parent
        root_dir = bin_dir.parent
        dirs.extend(
            [
                root_dir / "ref",
                root_dir / "share" / "color" / "argyll" / "ref",
                bin_dir / "ref",
            ]
        )

    dirs.extend(
        [
            Path("/usr/share/color/argyll/ref"),
            Path("/usr/local/share/color/argyll/ref"),
            Path("/opt/homebrew/share/color/argyll/ref"),
        ]
    )
    return dirs
