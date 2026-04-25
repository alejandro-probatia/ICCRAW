from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys


def bundled_tool_dirs() -> list[Path]:
    dirs: list[Path] = []

    env_dir = os.environ.get("ICCRAW_TOOL_DIR", "").strip()
    if env_dir:
        dirs.append(Path(env_dir).expanduser())

    exe_dir = Path(sys.executable).resolve().parent
    dirs.extend(
        [
            exe_dir / "tools" / "bin",
            exe_dir / "tools" / "argyll" / "bin",
            exe_dir / "tools" / "exiftool",
            exe_dir / "tools" / "lcms" / "bin",
        ]
    )

    base_dir = Path(getattr(sys, "_MEIPASS", exe_dir)).resolve()
    dirs.extend(
        [
            base_dir / "tools" / "bin",
            base_dir / "tools" / "argyll" / "bin",
            base_dir / "tools" / "exiftool",
            base_dir / "tools" / "lcms" / "bin",
        ]
    )

    seen: set[Path] = set()
    out: list[Path] = []
    for folder in dirs:
        try:
            resolved = folder.resolve()
        except Exception:
            resolved = folder
        if resolved not in seen:
            seen.add(resolved)
            out.append(resolved)
    return out


def external_tool_path(name: str) -> str | None:
    for folder in bundled_tool_dirs():
        for candidate in _candidate_names(name):
            path = folder / candidate
            if path.exists() and path.is_file():
                return str(path)
    return shutil.which(name)


def external_tool_search_path() -> str:
    parts = [str(folder) for folder in bundled_tool_dirs() if folder.exists()]
    current = os.environ.get("PATH", "")
    return os.pathsep.join([*parts, current]) if parts else current


def _candidate_names(name: str) -> list[str]:
    raw = str(name)
    names = [raw]
    if os.name == "nt" and Path(raw).suffix == "":
        names.append(f"{raw}.exe")
    return names
