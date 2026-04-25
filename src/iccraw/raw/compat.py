from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

try:
    import rawpy
except Exception:  # pragma: no cover - optional dependency at runtime.
    rawpy = None


@contextmanager
def open_rawpy(path_or_file, *, shot_select: int = 0, unpack: bool = False) -> Iterator:
    if rawpy is None:
        raise RuntimeError("No se puede abrir RAW: dependencia 'rawpy'/'LibRaw' no disponible.")

    raw = rawpy.RawPy()
    try:
        if hasattr(path_or_file, "read"):
            raw.open_buffer(path_or_file)
        else:
            raw.open_file(str(Path(path_or_file)))

        # rawpy-demosaic 0.10.1 on Windows exposes a helper imread() that calls
        # set_unpack_params(), while its RawPy object does not provide that
        # method. Use it only when present; the default shot is still loaded.
        set_unpack_params = getattr(raw, "set_unpack_params", None)
        if callable(set_unpack_params):
            set_unpack_params(shot_select=int(shot_select))
        if unpack:
            raw.unpack()
        yield raw
    finally:
        try:
            raw.close()
        except Exception:
            pass
