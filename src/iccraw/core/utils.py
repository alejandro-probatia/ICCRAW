from __future__ import annotations

from pathlib import Path
import hashlib
from typing import Iterable

import numpy as np
import tifffile
from PIL import Image


RAW_EXTENSIONS = {".raw", ".cr2", ".cr3", ".nef", ".arw", ".dng", ".raf", ".rw2", ".orf", ".pef"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def list_raw_files(folder: Path) -> list[Path]:
    files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in RAW_EXTENSIONS]
    files.sort()
    return files


def read_image(path: Path) -> np.ndarray:
    suffix = path.suffix.lower()
    if suffix in {".tif", ".tiff"}:
        arr = tifffile.imread(str(path))
        return _to_float_rgb(arr)
    img = Image.open(path).convert("RGB")
    arr = np.asarray(img)
    return _to_float_rgb(arr)


def _to_float_rgb(arr: np.ndarray) -> np.ndarray:
    arr = np.asarray(arr)
    if arr.ndim == 2:
        arr = np.repeat(arr[..., None], 3, axis=2)
    if arr.shape[-1] > 3:
        arr = arr[..., :3]

    if np.issubdtype(arr.dtype, np.integer):
        maxv = np.iinfo(arr.dtype).max
        return arr.astype(np.float32) / float(maxv)
    return np.clip(arr.astype(np.float32), 0.0, 1.0)


def write_tiff16(path: Path, image_linear_rgb: np.ndarray, icc_profile: bytes | None = None) -> None:
    ensure_parent(path)
    clipped = np.clip(image_linear_rgb, 0.0, 1.0)
    data = np.round(clipped * 65535.0).astype(np.uint16)

    extratags = None
    if icc_profile:
        extratags = [(34675, "B", len(icc_profile), icc_profile, False)]

    tifffile.imwrite(
        str(path),
        data,
        photometric="rgb",
        metadata=None,
        extratags=extratags,
    )


def robust_trimmed_mean(values: np.ndarray, trim_percent: float) -> float:
    if values.size == 0:
        return float("nan")
    values = np.sort(values)
    n = values.size
    k = int(n * trim_percent)
    if 2 * k >= n:
        return float(np.mean(values))
    return float(np.mean(values[k : n - k]))


def as_float_list(values: Iterable[float]) -> list[float]:
    return [float(v) for v in values]
