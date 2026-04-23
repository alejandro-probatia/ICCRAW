from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import os
import platform
import subprocess


@dataclass
class DependencyVersion:
    name: str
    version: str


@dataclass
class RunContext:
    software_version: str
    git_commit: str
    timestamp_utc: str
    deterministic_mode: bool
    dependencies: list[DependencyVersion]


def _git_commit() -> str:
    try:
        output = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return output.strip()
    except Exception:
        return "unknown"


def gather_run_context(version: str) -> dict:
    deterministic_mode = os.environ.get("ICC_DETERMINISTIC", "0") == "1"
    timestamp = "1970-01-01T00:00:00Z" if deterministic_mode else datetime.now(timezone.utc).isoformat()

    context = RunContext(
        software_version=version,
        git_commit=_git_commit(),
        timestamp_utc=timestamp,
        deterministic_mode=deterministic_mode,
        dependencies=[
            DependencyVersion(name="python", version=platform.python_version()),
            DependencyVersion(name="rawpy", version=_safe_import_version("rawpy")),
            DependencyVersion(name="opencv", version=_safe_import_version("cv2")),
            DependencyVersion(name="colour-science", version=_safe_import_version("colour")),
            DependencyVersion(name="tifffile", version=_safe_import_version("tifffile")),
        ],
    )
    return asdict(context)


def _safe_import_version(module: str) -> str:
    try:
        mod = __import__(module)
    except Exception:
        return "not-available"
    return getattr(mod, "__version__", "unknown")
