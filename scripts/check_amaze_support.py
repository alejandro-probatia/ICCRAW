from __future__ import annotations

import json
from importlib import metadata as importlib_metadata


def _dist_version(name: str) -> str | None:
    try:
        return importlib_metadata.version(name)
    except importlib_metadata.PackageNotFoundError:
        return None


def main() -> int:
    try:
        import rawpy
    except Exception as exc:
        payload = {
            "rawpy_module_version": "not-available",
            "rawpy_distribution": _dist_version("rawpy"),
            "rawpy_demosaic_distribution": _dist_version("rawpy-demosaic"),
            "libraw_version": "not-available",
            "flags": {},
            "amaze_supported": False,
            "error": str(exc),
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return 2

    flags = getattr(rawpy, "flags", {}) or {}
    payload = {
        "rawpy_module_version": getattr(rawpy, "__version__", "unknown"),
        "rawpy_distribution": _dist_version("rawpy"),
        "rawpy_demosaic_distribution": _dist_version("rawpy-demosaic"),
        "libraw_version": getattr(rawpy, "libraw_version", "unknown"),
        "flags": {str(key): bool(value) for key, value in flags.items()},
        "amaze_supported": bool(flags.get("DEMOSAIC_PACK_GPL3", False)),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
    return 0 if payload["amaze_supported"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
