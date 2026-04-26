from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
from collections.abc import Sequence
from typing import Any


def bundled_tool_dirs() -> list[Path]:
    dirs: list[Path] = []

    env_dir = os.environ.get("NEXORAW_TOOL_DIR", "").strip() or os.environ.get("ICCRAW_TOOL_DIR", "").strip()
    if env_dir:
        dirs.append(Path(env_dir).expanduser())

    exe_dir = Path(sys.executable).resolve().parent
    dirs.extend(
        [
            exe_dir / "tools" / "bin",
            exe_dir / "tools" / "argyll" / "bin",
            exe_dir / "tools" / "exiftool",
        ]
    )

    base_dir = Path(getattr(sys, "_MEIPASS", exe_dir)).resolve()
    dirs.extend(
        [
            base_dir / "tools" / "bin",
            base_dir / "tools" / "argyll" / "bin",
            base_dir / "tools" / "exiftool",
        ]
    )

    if sys.platform == "darwin":
        dirs.extend(
            [
                Path("/opt/homebrew/bin"),
                Path("/opt/homebrew/opt/argyll-cms/bin"),
                Path("/usr/local/bin"),
                Path("/usr/local/opt/argyll-cms/bin"),
                Path("/opt/local/bin"),
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


def hidden_subprocess_kwargs() -> dict[str, Any]:
    """Return kwargs that keep external tools from flashing a console on Windows."""
    if os.name != "nt":
        return {}

    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = getattr(subprocess, "SW_HIDE", 0)
    return {
        "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0),
        "startupinfo": startupinfo,
    }


def run_external(command: Sequence[str] | str, **kwargs: Any) -> subprocess.CompletedProcess:
    return subprocess.run(command, **_merge_hidden_subprocess_kwargs(kwargs))


def check_output_external(command: Sequence[str] | str, **kwargs: Any) -> str | bytes:
    return subprocess.check_output(command, **_merge_hidden_subprocess_kwargs(kwargs))


def _merge_hidden_subprocess_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    merged = dict(kwargs)
    if os.name != "nt":
        return merged

    hidden = hidden_subprocess_kwargs()
    hidden_flags = int(hidden.get("creationflags", 0) or 0)
    current_flags = int(merged.get("creationflags", 0) or 0)
    merged["creationflags"] = current_flags | hidden_flags
    merged.setdefault("startupinfo", hidden.get("startupinfo"))
    return merged


def _candidate_names(name: str) -> list[str]:
    raw = str(name)
    names = [raw]
    if os.name == "nt" and Path(raw).suffix == "":
        names.append(f"{raw}.exe")
    return names
