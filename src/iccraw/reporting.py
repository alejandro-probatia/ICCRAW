from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import os
import platform
import shutil
import subprocess
from typing import Any


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


@dataclass
class ExternalToolCheck:
    name: str
    commands: list[str]
    selected_command: str | None
    path: str | None
    available: bool
    required: bool
    version: str
    version_command: list[str] | None
    ok: bool
    message: str


EXTERNAL_TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "dcraw",
        "commands": ["dcraw"],
        "version_args": [],
        "required": True,
    },
    {
        "name": "argyll-colprof",
        "commands": ["colprof"],
        "version_args": ["-?"],
        "required": True,
    },
    {
        "name": "argyll-xicclu",
        "commands": ["xicclu", "icclu"],
        "version_args": [],
        "required": True,
    },
    {
        "name": "littlecms-tificc",
        "commands": ["tificc"],
        "version_args": ["-v"],
        "required": True,
    },
    {
        "name": "exiftool",
        "commands": ["exiftool"],
        "version_args": ["-ver"],
        "required": True,
    },
]


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
            DependencyVersion(name="dcraw", version=_dcraw_version()),
            DependencyVersion(name="rawpy-optional", version=_safe_import_version("rawpy")),
            DependencyVersion(name="opencv", version=_safe_import_version("cv2")),
            DependencyVersion(name="colour-science", version=_safe_import_version("colour")),
            DependencyVersion(name="tifffile", version=_safe_import_version("tifffile")),
        ],
    )
    return asdict(context)


def check_external_tools() -> dict[str, Any]:
    checks = [_check_external_tool(spec) for spec in EXTERNAL_TOOL_SPECS]
    missing_required = [check.name for check in checks if check.required and not check.available]
    failing_required = [check.name for check in checks if check.required and not check.ok]
    return {
        "status": "ok" if not failing_required else "missing_required",
        "missing_required": missing_required,
        "failing_required": failing_required,
        "tools": [asdict(check) for check in checks],
    }


def _check_external_tool(spec: dict[str, Any]) -> ExternalToolCheck:
    commands = [str(c) for c in spec["commands"]]
    selected = next((command for command in commands if shutil.which(command)), None)
    required = bool(spec.get("required", True))

    if selected is None:
        return ExternalToolCheck(
            name=str(spec["name"]),
            commands=commands,
            selected_command=None,
            path=None,
            available=False,
            required=required,
            version="not-available",
            version_command=None,
            ok=not required,
            message="herramienta no encontrada en PATH",
        )

    version_args = [str(arg) for arg in spec.get("version_args", [])]
    version_command = [selected, *version_args]
    version, message = _tool_version(version_command)
    return ExternalToolCheck(
        name=str(spec["name"]),
        commands=commands,
        selected_command=selected,
        path=shutil.which(selected),
        available=True,
        required=required,
        version=version,
        version_command=version_command,
        ok=True,
        message=message,
    )


def _tool_version(command: list[str]) -> tuple[str, str]:
    try:
        proc = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
            timeout=10,
        )
    except Exception as exc:
        return "unknown", f"no se pudo leer version: {exc}"

    lines = [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]
    if not lines:
        return "unknown", "herramienta disponible; version no detectada"
    return lines[0], "ok"


def _safe_import_version(module: str) -> str:
    try:
        mod = __import__(module)
    except Exception:
        return "not-available"
    return getattr(mod, "__version__", "unknown")


def _dcraw_version() -> str:
    try:
        proc = subprocess.run(
            ["dcraw"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        output = (proc.stdout or "").strip().splitlines()
        for line in output:
            txt = line.strip()
            if txt.lower().startswith("dcraw"):
                return txt
        if output:
            return output[0].strip()
        return "unknown"
    except Exception:
        return "not-available"
