from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
import ctypes
from ctypes import wintypes
import sys

import numpy as np
from PIL import Image, ImageCms


_TRANSFORM_CACHE: OrderedDict[str, ImageCms.ImageCmsTransform] = OrderedDict()
_SRGB_PROFILE = ImageCms.createProfile("sRGB")


def srgb_float_to_u8(image_srgb: np.ndarray) -> np.ndarray:
    image = np.asarray(image_srgb)
    if image.ndim == 2:
        image = np.repeat(image[..., None], 3, axis=2)
    if image.ndim != 3 or image.shape[2] < 3:
        raise RuntimeError(f"Imagen sRGB inesperada para display: shape={image.shape}")
    image = image[..., :3]
    if np.issubdtype(image.dtype, np.integer):
        maxv = float(np.iinfo(image.dtype).max)
        image_f = np.clip(image.astype(np.float32) / maxv, 0.0, 1.0)
    else:
        image_f = np.clip(image.astype(np.float32), 0.0, 1.0)
    return np.ascontiguousarray(np.round(image_f * 255.0).astype(np.uint8))


def srgb_to_display_u8(image_srgb: np.ndarray, monitor_profile: Path | None) -> np.ndarray:
    rgb_u8 = srgb_float_to_u8(image_srgb)
    if monitor_profile is None:
        return rgb_u8
    return srgb_u8_to_display_u8(rgb_u8, monitor_profile)


def srgb_u8_to_display_u8(rgb_u8: np.ndarray, monitor_profile: Path | None) -> np.ndarray:
    rgb = np.asarray(rgb_u8)
    if rgb.ndim == 2:
        rgb = np.repeat(rgb[..., None], 3, axis=2)
    if rgb.ndim != 3 or rgb.shape[2] < 3:
        raise RuntimeError(f"Imagen sRGB inesperada para display: shape={rgb.shape}")
    rgb = np.ascontiguousarray(rgb[..., :3].astype(np.uint8))
    if monitor_profile is None:
        return rgb

    transform = _display_transform(monitor_profile)
    image = Image.fromarray(rgb, "RGB")
    converted = ImageCms.applyTransform(image, transform)
    if converted is None:
        raise RuntimeError("La conversion ICC de monitor no devolvio imagen.")
    return np.asarray(converted, dtype=np.uint8).copy()


def display_profile_cache_key(profile_path: Path) -> str:
    path = Path(profile_path).expanduser()
    try:
        resolved = path.resolve()
        st = resolved.stat()
        return f"{resolved}|{st.st_mtime_ns}|{st.st_size}"
    except OSError:
        return str(path)


def display_profile_label(profile_path: Path | None) -> str:
    if profile_path is None:
        return "sRGB"
    path = Path(profile_path).expanduser()
    if not path.exists():
        return f"No encontrado: {path}"
    try:
        profile = ImageCms.getOpenProfile(str(path))
        description = ImageCms.getProfileDescription(profile).strip()
    except Exception:
        description = ""
    return description or path.name


def detect_system_display_profile() -> Path | None:
    if sys.platform != "win32":
        return None
    return _detect_windows_display_profile()


def _display_transform(monitor_profile: Path) -> ImageCms.ImageCmsTransform:
    key = display_profile_cache_key(monitor_profile)
    cached = _TRANSFORM_CACHE.get(key)
    if cached is not None:
        _TRANSFORM_CACHE.move_to_end(key)
        return cached

    path = Path(monitor_profile).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"No existe el perfil ICC de monitor: {path}")

    try:
        destination = ImageCms.getOpenProfile(str(path))
        transform = ImageCms.buildTransformFromOpenProfiles(
            _SRGB_PROFILE,
            destination,
            "RGB",
            "RGB",
            renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC,
        )
    except Exception as exc:
        raise RuntimeError(f"No se pudo construir transformacion ICC de monitor: {path}") from exc

    _TRANSFORM_CACHE[key] = transform
    while len(_TRANSFORM_CACHE) > 4:
        _TRANSFORM_CACHE.popitem(last=False)
    return transform


def _detect_windows_display_profile() -> Path | None:
    try:
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        user32.GetDC.argtypes = [wintypes.HWND]
        user32.GetDC.restype = wintypes.HDC
        user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
        user32.ReleaseDC.restype = wintypes.INT
        gdi32.GetICMProfileW.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR]
        gdi32.GetICMProfileW.restype = wintypes.BOOL
    except Exception:
        return None

    hdc = user32.GetDC(None)
    if not hdc:
        return None
    try:
        size = wintypes.DWORD(0)
        gdi32.GetICMProfileW(hdc, ctypes.byref(size), None)
        if size.value <= 0:
            return None
        buffer = ctypes.create_unicode_buffer(size.value)
        if not gdi32.GetICMProfileW(hdc, ctypes.byref(size), buffer):
            return None
        path = Path(buffer.value).expanduser()
        if path.exists():
            return path
    except Exception:
        return None
    finally:
        user32.ReleaseDC(None, hdc)
    return None
