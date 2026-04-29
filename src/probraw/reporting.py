from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from importlib import metadata as importlib_metadata
import os
from pathlib import Path
import platform
import subprocess
from typing import Any

from .core.external import check_output_external, external_tool_path, run_external
from .raw.pipeline import rawpy_feature_flags


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
        "name": "argyll-cctiff",
        "commands": ["cctiff"],
        "version_args": ["-?"],
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
        output = check_output_external(
            ["git", "rev-parse", "--short", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
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
            DependencyVersion(name="rawpy-distribution", version=_rawpy_distribution_version()),
            DependencyVersion(name="libraw", version=_libraw_version()),
            DependencyVersion(name="rawpy-flags", version=_rawpy_flags_summary()),
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
        "python_runtime": {
            "rawpy": _safe_import_version("rawpy"),
            "rawpy_distribution": _rawpy_distribution_version(),
            "libraw": _libraw_version(),
            "rawpy_flags": rawpy_feature_flags(),
            "amaze_supported": bool(rawpy_feature_flags().get("DEMOSAIC_PACK_GPL3", False)),
        },
    }


def check_amaze_backend() -> dict[str, Any]:
    flags = rawpy_feature_flags()
    supported = bool(flags.get("DEMOSAIC_PACK_GPL3", False))
    return {
        "status": "ok" if supported else "missing_gpl3",
        "rawpy": _safe_import_version("rawpy"),
        "rawpy_distribution": _rawpy_distribution_version(),
        "libraw": _libraw_version(),
        "rawpy_flags": flags,
        "amaze_supported": supported,
    }


def check_c2pa_support() -> dict[str, Any]:
    try:
        import c2pa  # type: ignore[import-not-found]
    except Exception as exc:
        return {
            "status": "not_available",
            "available": False,
            "c2pa_python_distribution": _safe_distribution_version("c2pa-python"),
            "module_path": None,
            "native_libraries": [],
            "missing_api": [],
            "message": f"c2pa-python no disponible: {exc}",
        }

    required_api = ["Builder", "C2paSignerInfo", "C2paSigningAlg", "Reader", "Signer"]
    missing_api = [name for name in required_api if not hasattr(c2pa, name)]
    module_path = Path(getattr(c2pa, "__file__", "") or "")
    package_dir = module_path.parent if module_path else Path()
    native_libraries = sorted(
        str(path)
        for pattern in ("c2pa_c.*", "libc2pa_c.*")
        for path in (package_dir / "libs").glob(pattern)
    )
    ok = not missing_api and any(path.lower().endswith((".dll", ".so", ".dylib")) for path in native_libraries)
    return {
        "status": "ok" if ok else "incomplete",
        "available": True,
        "c2pa_python_distribution": _safe_distribution_version("c2pa-python"),
        "module_path": str(module_path) if module_path else None,
        "native_libraries": native_libraries,
        "missing_api": missing_api,
        "message": "ok" if ok else "c2pa-python instalado, pero faltan API o libreria nativa",
    }


def _check_external_tool(spec: dict[str, Any]) -> ExternalToolCheck:
    commands = [str(c) for c in spec["commands"]]
    selected = next((command for command in commands if external_tool_path(command)), None)
    selected_path = external_tool_path(selected) if selected is not None else None
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
    version_command = [selected_path or selected, *version_args]
    version, message = _tool_version(version_command)
    return ExternalToolCheck(
        name=str(spec["name"]),
        commands=commands,
        selected_command=selected,
        path=selected_path,
        available=True,
        required=required,
        version=version,
        version_command=version_command,
        ok=True,
        message=message,
    )


def _tool_version(command: list[str]) -> tuple[str, str]:
    try:
        proc = run_external(
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


def _rawpy_distribution_version() -> str:
    found: list[str] = []
    for dist_name in ("rawpy-demosaic", "rawpy"):
        try:
            found.append(f"{dist_name}=={importlib_metadata.version(dist_name)}")
        except importlib_metadata.PackageNotFoundError:
            continue
    return ", ".join(found) if found else "not-available"


def _safe_distribution_version(dist_name: str) -> str:
    try:
        return importlib_metadata.version(dist_name)
    except importlib_metadata.PackageNotFoundError:
        return "not-available"


def _rawpy_flags_summary() -> str:
    flags = rawpy_feature_flags()
    if not flags:
        return "not-available"
    return ", ".join(f"{key}={value}" for key, value in sorted(flags.items()))


def _libraw_version() -> str:
    try:
        import rawpy

        version = getattr(rawpy, "libraw_version", None)
        if isinstance(version, tuple):
            return ".".join(str(part) for part in version)
        return str(version or "unknown")
    except Exception:
        return "not-available"
