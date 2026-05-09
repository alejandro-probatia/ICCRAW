from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import sys

import numpy as np
import colour
from colour.adaptation import matrix_chromatic_adaptation_VonKries
from PIL import ImageCms

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
    preferred_descriptions: tuple[str, ...] = ()
    compatible_descriptions: tuple[str, ...] = ()
    rejected_descriptions: tuple[str, ...] = ()


GENERIC_RGB_PROFILES: dict[str, GenericRgbProfile] = {
    "srgb": GenericRgbProfile(
        key="srgb",
        label="sRGB",
        colour_space="sRGB",
        gamma=2.2,
        preferred_filenames=("sRGB Color Space Profile.icm", "sRGB.icm", "sRGB.icc", "sRGB Profile.icc"),
        preferred_descriptions=("sRGB", "sRGB IEC61966"),
    ),
    "adobe_rgb": GenericRgbProfile(
        key="adobe_rgb",
        label="Adobe RGB (1998)",
        colour_space="Adobe RGB (1998)",
        gamma=2.19921875,
        preferred_filenames=("AdobeRGB1998.icc", "Adobe RGB (1998).icc", "Adobe RGB 1998.icc"),
        compatible_filenames=("ClayRGB1998.icm",),
        preferred_descriptions=("Adobe RGB (1998)", "Compatible with Adobe RGB (1998)"),
        compatible_descriptions=("ClayRGB1998", "Clay RGB 1998"),
    ),
    "prophoto_rgb": GenericRgbProfile(
        key="prophoto_rgb",
        label="ProPhoto RGB",
        colour_space="ProPhoto RGB",
        gamma=1.8,
        preferred_filenames=("ProPhoto.icm", "ProPhoto RGB.icc", "ProPhotoRGB.icc", "ProPhoto.icc"),
        compatible_filenames=("ProPhoto.icm",),
        preferred_descriptions=("ProPhoto RGB", "ROMM RGB"),
        rejected_descriptions=("Linear",),
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
        candidate = _find_standard_profile_by_filename(folders, filenames)
        if candidate is not None:
            return candidate
    for descriptions in (profile.preferred_descriptions, profile.compatible_descriptions):
        candidate = _find_standard_profile_by_description(
            folders,
            descriptions,
            rejected_descriptions=profile.rejected_descriptions,
        )
        if candidate is not None:
            return candidate
    return None


def available_standard_output_profiles(output_space: str | None) -> list[Path]:
    profile = generic_output_profile(output_space)
    folders = _standard_profile_search_dirs()
    matches: list[Path] = []
    seen: set[Path] = set()
    for filenames in (profile.preferred_filenames, profile.compatible_filenames):
        for candidate in _standard_profiles_by_filename(folders, filenames):
            resolved = candidate.resolve(strict=False)
            if resolved not in seen:
                seen.add(resolved)
                matches.append(candidate)
    for descriptions in (profile.preferred_descriptions, profile.compatible_descriptions):
        for candidate in _standard_profiles_by_description(
            folders,
            descriptions,
            rejected_descriptions=profile.rejected_descriptions,
        ):
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


def standard_profile_search_dirs() -> list[Path]:
    return _standard_profile_search_dirs()


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
        data_home = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share").expanduser()
        data_dirs = [
            Path(item).expanduser()
            for item in os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":")
            if item.strip()
        ]
        dirs.extend(
            [
                data_home / "color" / "icc",
                data_home / "icc",
                *(data_dir / "color" / "icc" for data_dir in data_dirs),
                *(data_dir / "icc" for data_dir in data_dirs),
                Path("/usr/share/color/icc"),
                Path("/usr/share/color/icc/colord"),
                Path("/usr/share/icc"),
                Path("/usr/local/share/color/icc"),
                Path("/usr/local/share/icc"),
                Path("/var/lib/colord/icc"),
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


def _find_standard_profile_by_filename(folders: list[Path], filenames: tuple[str, ...]) -> Path | None:
    return next(iter(_standard_profiles_by_filename(folders, filenames)), None)


def _standard_profiles_by_filename(folders: list[Path], filenames: tuple[str, ...]) -> list[Path]:
    names = {str(filename) for filename in filenames}
    matches: list[Path] = []
    seen: set[Path] = set()
    for folder in folders:
        for filename in filenames:
            candidate = folder / filename
            if _valid_icc_file(candidate):
                resolved = candidate.resolve(strict=False)
                if resolved not in seen:
                    seen.add(resolved)
                    matches.append(candidate)
    for candidate in _iter_system_icc_files(folders):
        if candidate.name not in names:
            continue
        resolved = candidate.resolve(strict=False)
        if resolved not in seen:
            seen.add(resolved)
            matches.append(candidate)
    return matches


def _find_standard_profile_by_description(
    folders: list[Path],
    descriptions: tuple[str, ...],
    *,
    rejected_descriptions: tuple[str, ...] = (),
) -> Path | None:
    return next(
        iter(
            _standard_profiles_by_description(
                folders,
                descriptions,
                rejected_descriptions=rejected_descriptions,
            )
        ),
        None,
    )


def _standard_profiles_by_description(
    folders: list[Path],
    descriptions: tuple[str, ...],
    *,
    rejected_descriptions: tuple[str, ...] = (),
) -> list[Path]:
    if not descriptions:
        return []
    matches: list[Path] = []
    seen: set[Path] = set()
    for candidate in _iter_system_icc_files(folders):
        resolved = candidate.resolve(strict=False)
        if resolved in seen:
            continue
        if _profile_description_matches(candidate, descriptions, rejected_descriptions=rejected_descriptions):
            seen.add(resolved)
            matches.append(candidate)
    return matches


def _iter_system_icc_files(folders: list[Path]) -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    for folder in folders:
        if not folder.exists() or not folder.is_dir():
            continue
        try:
            candidates = sorted(
                (
                    path
                    for path in folder.rglob("*")
                    if path.suffix.lower() in {".icc", ".icm"} and path.is_file()
                ),
                key=lambda path: (len(path.relative_to(folder).parts), path.name.lower(), str(path)),
            )
        except Exception:
            continue
        for candidate in candidates:
            if not _valid_icc_file(candidate):
                continue
            resolved = candidate.resolve(strict=False)
            if resolved in seen:
                continue
            seen.add(resolved)
            files.append(candidate)
    return files


def _valid_icc_file(path: Path) -> bool:
    try:
        return path.exists() and path.is_file() and path.stat().st_size >= 128
    except Exception:
        return False


def _profile_description_matches(
    path: Path,
    descriptions: tuple[str, ...],
    *,
    rejected_descriptions: tuple[str, ...] = (),
) -> bool:
    description = _normalized_profile_text(_profile_description(path))
    if not description:
        return False
    if any(_normalized_profile_text(candidate) in description for candidate in rejected_descriptions):
        return False
    return any(_normalized_profile_text(candidate) in description for candidate in descriptions)


def _profile_description(path: Path) -> str:
    try:
        profile = ImageCms.getOpenProfile(str(path))
        return ImageCms.getProfileDescription(profile).strip()
    except Exception:
        return ""


def _normalized_profile_text(value: str) -> str:
    return "".join(ch for ch in str(value or "").casefold() if ch.isalnum())


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
                root_dir / "share" / "argyllcms" / "ref",
                root_dir / "share" / "color" / "argyll" / "ref",
                bin_dir / "ref",
            ]
        )

    dirs.extend(
        [
            Path("/usr/share/argyllcms/ref"),
            Path("/usr/share/color/argyll/ref"),
            Path("/usr/local/share/argyllcms/ref"),
            Path("/usr/local/share/color/argyll/ref"),
            Path("/opt/homebrew/share/argyllcms/ref"),
            Path("/opt/homebrew/share/color/argyll/ref"),
        ]
    )
    return dirs
