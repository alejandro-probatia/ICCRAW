from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import colour
from colour.adaptation import matrix_chromatic_adaptation_VonKries

from .builder import D50_XYZ, build_matrix_shaper_icc


@dataclass(frozen=True)
class GenericRgbProfile:
    key: str
    label: str
    colour_space: str
    gamma: float
    filename: str


GENERIC_RGB_PROFILES: dict[str, GenericRgbProfile] = {
    "srgb": GenericRgbProfile(
        key="srgb",
        label="sRGB",
        colour_space="sRGB",
        gamma=2.2,
        filename="nexoraw-generic-srgb.icc",
    ),
    "adobe_rgb": GenericRgbProfile(
        key="adobe_rgb",
        label="Adobe RGB (1998)",
        colour_space="Adobe RGB (1998)",
        gamma=2.19921875,
        filename="nexoraw-generic-adobe-rgb-1998.icc",
    ),
    "prophoto_rgb": GenericRgbProfile(
        key="prophoto_rgb",
        label="ProPhoto RGB",
        colour_space="ProPhoto RGB",
        gamma=1.8,
        filename="nexoraw-generic-prophoto-rgb.icc",
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
    base = directory or (Path.home() / ".cache" / "nexoraw" / "generic-profiles")
    return Path(base).expanduser() / profile.filename


def ensure_generic_output_profile(output_space: str | None, *, directory: Path | None = None) -> Path:
    profile = generic_output_profile(output_space)
    path = generic_output_profile_path(profile.key, directory=directory)
    if path.exists() and path.stat().st_size > 0:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(build_generic_output_icc(profile.key))
    return path


def build_generic_output_icc(output_space: str | None) -> bytes:
    profile = generic_output_profile(output_space)
    rgb_space = colour.RGB_COLOURSPACES[profile.colour_space]
    matrix = _rgb_to_xyz_d50_matrix(rgb_space)
    return build_matrix_shaper_icc(
        description=f"NexoRAW generic {profile.label}",
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
