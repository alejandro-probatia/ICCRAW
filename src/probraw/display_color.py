from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
import ctypes
from ctypes import wintypes
import hashlib
import os
import re
import shutil
import subprocess
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
    if sys.platform == "win32":
        return _detect_windows_display_profile()
    if sys.platform == "darwin":
        return _detect_macos_display_profile()
    if sys.platform.startswith(("linux", "freebsd", "openbsd", "netbsd")):
        return _detect_linux_display_profile()
    return None


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


def _detect_linux_display_profile() -> Path | None:
    detected = _detect_colord_display_profile()
    if detected is not None:
        return detected
    return _detect_x11_root_icc_profile()


def _detect_colord_display_profile() -> Path | None:
    if shutil.which("colormgr") is None:
        return None
    output = _run_text_command(["colormgr", "get-devices-by-kind", "display"])
    if not output:
        return None

    for _score, device_path, block in _colord_display_device_candidates(output):
        profile_output = _run_text_command(["colormgr", "device-get-default-profile", device_path])
        profile_path = _parse_colord_profile_filename(profile_output or "")
        if profile_path is not None:
            return profile_path

        for fallback in _parse_colord_device_profile_paths(block):
            if fallback.exists():
                return fallback
    return None


def _colord_display_device_candidates(output: str) -> list[tuple[int, str, str]]:
    blocks: list[str] = []
    current: list[str] = []
    for line in output.splitlines():
        if line.startswith("Object Path:"):
            if current:
                blocks.append("\n".join(current))
            current = [line]
        elif current:
            current.append(line)
    if current:
        blocks.append("\n".join(current))

    candidates: list[tuple[int, str, str]] = []
    for index, block in enumerate(blocks):
        match = re.search(r"^Object Path:\s+(.+)$", block, re.MULTILINE)
        if match is None:
            continue
        score = 1000 - index
        if re.search(r"^Enabled:\s+Yes\s*$", block, re.MULTILINE):
            score += 100
        if re.search(r"^Metadata:\s+OutputPriority=primary\s*$", block, re.MULTILINE):
            score += 1000
        if re.search(r"^Embedded:\s+Yes\s*$", block, re.MULTILINE):
            score += 10
        candidates.append((score, match.group(1).strip(), block))
    return sorted(candidates, key=lambda item: item[0], reverse=True)


def _parse_colord_profile_filename(output: str) -> Path | None:
    for line in output.splitlines():
        match = re.match(r"^Filename:\s+(.+)$", line.strip())
        if match is None:
            continue
        path = Path(match.group(1).strip()).expanduser()
        if path.exists():
            return path
    return None


def _parse_colord_device_profile_paths(block: str) -> list[Path]:
    paths: list[Path] = []
    lines = block.splitlines()
    for index, line in enumerate(lines):
        if not re.match(r"^\s*Profile\s+\d+:", line):
            continue
        rest = line.split(":", 1)[1].strip()
        if _looks_like_icc_path(rest):
            paths.append(Path(rest).expanduser())
            continue
        for next_line in lines[index + 1 : index + 4]:
            candidate = next_line.strip()
            if _looks_like_icc_path(candidate):
                paths.append(Path(candidate).expanduser())
                break
            if re.match(r"^[A-Za-z ]+:", candidate):
                break
    return paths


def _detect_x11_root_icc_profile() -> Path | None:
    if shutil.which("xprop") is None:
        return None
    if not os.environ.get("DISPLAY"):
        return None
    output = _run_text_command(["xprop", "-root", "_ICC_PROFILE"], timeout=2.0)
    data = _parse_xprop_icc_profile_bytes(output or "")
    if data is None:
        return None
    return _write_cached_display_profile(data, prefix="x11-root")


def _parse_xprop_icc_profile_bytes(output: str) -> bytes | None:
    if "=" not in output:
        return None
    raw_values = re.findall(r"-?\d+", output.split("=", 1)[1])
    if len(raw_values) < 128:
        return None
    values: list[int] = []
    for item in raw_values:
        try:
            value = int(item)
        except ValueError:
            return None
        if value < 0 or value > 255:
            return None
        values.append(value)
    data = bytes(values)
    profile_size = int.from_bytes(data[:4], "big")
    if 128 <= profile_size <= len(data):
        data = data[:profile_size]
    if len(data) < 128:
        return None
    return data


def _detect_macos_display_profile() -> Path | None:
    data = _macos_main_display_icc_data()
    if data is None:
        return None
    return _write_cached_display_profile(data, prefix="macos-main-display")


def _macos_main_display_icc_data() -> bytes | None:
    try:
        core_graphics = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
        )
        core_foundation = ctypes.cdll.LoadLibrary(
            "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
        )

        core_graphics.CGMainDisplayID.argtypes = []
        core_graphics.CGMainDisplayID.restype = ctypes.c_uint32
        core_graphics.CGDisplayCopyColorSpace.argtypes = [ctypes.c_uint32]
        core_graphics.CGDisplayCopyColorSpace.restype = ctypes.c_void_p
        core_graphics.CGColorSpaceCopyICCData.argtypes = [ctypes.c_void_p]
        core_graphics.CGColorSpaceCopyICCData.restype = ctypes.c_void_p

        core_foundation.CFDataGetLength.argtypes = [ctypes.c_void_p]
        core_foundation.CFDataGetLength.restype = ctypes.c_long
        core_foundation.CFDataGetBytePtr.argtypes = [ctypes.c_void_p]
        core_foundation.CFDataGetBytePtr.restype = ctypes.POINTER(ctypes.c_ubyte)
        core_foundation.CFRelease.argtypes = [ctypes.c_void_p]
        core_foundation.CFRelease.restype = None
    except Exception:
        return None

    color_space = None
    icc_data = None
    try:
        display_id = core_graphics.CGMainDisplayID()
        color_space = core_graphics.CGDisplayCopyColorSpace(display_id)
        if not color_space:
            return None
        icc_data = core_graphics.CGColorSpaceCopyICCData(color_space)
        if not icc_data:
            return None
        length = int(core_foundation.CFDataGetLength(icc_data))
        if length < 128:
            return None
        pointer = core_foundation.CFDataGetBytePtr(icc_data)
        if not pointer:
            return None
        return ctypes.string_at(pointer, length)
    except Exception:
        return None
    finally:
        try:
            if icc_data:
                core_foundation.CFRelease(icc_data)
            if color_space:
                core_foundation.CFRelease(color_space)
        except Exception:
            pass


def _write_cached_display_profile(data: bytes, *, prefix: str) -> Path | None:
    if len(data) < 128:
        return None
    profile_size = int.from_bytes(data[:4], "big")
    if 128 <= profile_size <= len(data):
        data = data[:profile_size]
    digest = hashlib.sha256(data).hexdigest()[:16]
    cache_root = _display_profile_cache_dir()
    try:
        cache_root.mkdir(parents=True, exist_ok=True)
        path = cache_root / f"{prefix}-{digest}.icc"
        if not path.exists() or path.read_bytes() != data:
            path.write_bytes(data)
        return path
    except OSError:
        return None


def _display_profile_cache_dir() -> Path:
    xdg_cache = os.environ.get("XDG_CACHE_HOME", "").strip()
    if xdg_cache:
        return Path(xdg_cache).expanduser() / "probraw" / "display-profiles"
    return Path.home().expanduser() / ".cache" / "probraw" / "display-profiles"


def _looks_like_icc_path(value: str) -> bool:
    if not value:
        return False
    suffix = Path(value).suffix.lower()
    return (value.startswith("/") or value.startswith("~")) and suffix in {".icc", ".icm"}


def _run_text_command(args: list[str], *, timeout: float = 3.0) -> str | None:
    try:
        result = subprocess.run(
            args,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=timeout,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return result.stdout
