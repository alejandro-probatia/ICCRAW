from __future__ import annotations

from pathlib import Path
import hashlib
import itertools
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


def versioned_output_path(path: Path, *, separator: str = "_v", width: int = 3) -> Path:
    """Return a non-existing sibling path by appending a version suffix.

    The first render keeps the requested name. If it already exists, subsequent
    renders use ``stem_v002.ext``, ``stem_v003.ext`` and so on, preserving
    previous TIFFs and their audit value.
    """
    candidate = Path(path)
    if not candidate.exists():
        return candidate

    parent = candidate.parent
    stem = candidate.stem
    suffix = candidate.suffix
    for index in itertools.count(2):
        versioned = parent / f"{stem}{separator}{index:0{int(width)}d}{suffix}"
        if not versioned.exists():
            return versioned
    raise RuntimeError("No se pudo generar una ruta versionada de salida")


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
    source = np.asarray(image_linear_rgb, dtype=np.float32)
    work = np.empty(source.shape, dtype=np.float32)
    np.clip(source, 0.0, 1.0, out=work)
    np.multiply(work, 65535.0, out=work)
    np.rint(work, out=work)
    data = work.astype(np.uint16, copy=False)

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
