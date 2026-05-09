from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
from importlib import metadata as importlib_metadata
import os
from pathlib import Path
import platform
import subprocess
import sys
from typing import Any

from .core.external import check_output_external, external_tool_path, run_external
from .display_color import detect_system_display_profile, display_profile_label
from .profile.generic import GENERIC_RGB_PROFILES, find_standard_output_profile
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
    standard_profiles = _check_standard_profiles()
    missing_required = [check.name for check in checks if check.required and not check.available]
    missing_required.extend(standard_profiles["missing_required"])
    failing_required = [check.name for check in checks if check.required and not check.ok]
    failing_required.extend(standard_profiles["missing_required"])
    return {
        "status": "ok" if not failing_required else "missing_required",
        "missing_required": missing_required,
        "failing_required": failing_required,
        "tools": [asdict(check) for check in checks],
        "standard_profiles": standard_profiles,
        "python_runtime": {
            "rawpy": _safe_import_version("rawpy"),
            "rawpy_distribution": _rawpy_distribution_version(),
            "libraw": _libraw_version(),
            "rawpy_flags": rawpy_feature_flags(),
            "amaze_supported": bool(rawpy_feature_flags().get("DEMOSAIC_PACK_GPL3", False)),
        },
    }


def check_color_environment() -> dict[str, Any]:
    """Return a cross-platform color-management audit for installed builds."""
    display_profile = _display_profile_status()
    standard_profiles = _check_standard_profiles()
    session = _graphics_session_status()
    wayland = _wayland_color_status()
    packages = _system_color_packages()
    policy = _color_management_policy(display_profile=display_profile, session=session)
    warnings = _color_environment_warnings(
        display_profile=display_profile,
        standard_profiles=standard_profiles,
        session=session,
        wayland=wayland,
        packages=packages,
    )
    return {
        "status": "ok" if not warnings else "warning",
        "warnings": warnings,
        "platform": {
            "sys_platform": sys.platform,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "os_release": _os_release(),
        },
        "session": session,
        "toolkit": _toolkit_status(),
        "cmm": _cmm_status(),
        "color_management_policy": policy,
        "display_profile": display_profile,
        "standard_profiles": standard_profiles,
        "wayland": wayland,
        "desktop": _desktop_status(),
        "packages": packages,
        "colord": _colord_status(),
    }


def _check_standard_profiles() -> dict[str, Any]:
    profiles: list[dict[str, Any]] = []
    missing: list[str] = []
    for key, profile in GENERIC_RGB_PROFILES.items():
        path = find_standard_output_profile(key)
        available = path is not None
        check_name = f"standard-profile-{key}"
        if not available:
            missing.append(check_name)
        profiles.append(
            {
                "name": check_name,
                "key": key,
                "label": profile.label,
                "available": available,
                "required": True,
                "path": str(path) if path is not None else None,
                "sha256": _sha256_file_optional(path),
                "ok": available,
                "message": "ok" if available else "perfil ICC estandar no encontrado",
            }
        )
    return {
        "status": "ok" if not missing else "missing_required",
        "missing_required": missing,
        "profiles": profiles,
    }


def _graphics_session_status() -> dict[str, Any]:
    env_keys = [
        "XDG_SESSION_TYPE",
        "XDG_CURRENT_DESKTOP",
        "DESKTOP_SESSION",
        "KDE_FULL_SESSION",
        "KDE_SESSION_VERSION",
        "WAYLAND_DISPLAY",
        "DISPLAY",
        "QT_QPA_PLATFORM",
        "XDG_DATA_HOME",
        "XDG_DATA_DIRS",
        "SESSIONNAME",
        "USERDOMAIN",
    ]
    env = {key: os.environ.get(key) for key in env_keys if os.environ.get(key)}
    session_type = str(env.get("XDG_SESSION_TYPE") or "").strip().lower() or "unknown"
    return {
        "session_type": session_type,
        "is_wayland": session_type == "wayland" or bool(env.get("WAYLAND_DISPLAY")),
        "is_x11": session_type in {"x11", "xorg"} or bool(env.get("DISPLAY")),
        "environment": env,
    }


def _color_management_policy(*, display_profile: dict[str, Any], session: dict[str, Any]) -> dict[str, Any]:
    platform_name = sys.platform
    if platform_name == "win32":
        os_color_system = "Windows WCS/ICM"
        profile_provider = "GetICMProfileW"
        surface_policy = "ProbRAW convierte previews con LittleCMS2; Windows gestiona el perfil de pantalla del dispositivo."
    elif platform_name == "darwin":
        os_color_system = "macOS ColorSync"
        profile_provider = "CoreGraphics/ColorSync"
        surface_policy = "ProbRAW convierte previews con LittleCMS2; ColorSync proporciona el perfil ICC de la pantalla principal."
    elif platform_name.startswith(("linux", "freebsd", "openbsd", "netbsd")):
        os_color_system = "Linux colord/Wayland/X11"
        profile_provider = "colord en Linux, _ICC_PROFILE en X11 como fallback"
        if session.get("is_wayland"):
            surface_policy = (
                "ProbRAW usa LittleCMS2 para la preview gestionada. En Wayland, KWin/compositor "
                "puede gestionar superficies etiquetadas; evitar doble conversion requiere validacion por plataforma."
            )
        else:
            surface_policy = "ProbRAW usa LittleCMS2 para convertir la preview hacia el ICC de monitor detectado."
    else:
        os_color_system = "unknown"
        profile_provider = "manual"
        surface_policy = "ProbRAW usa LittleCMS2 cuando hay perfiles ICC disponibles."

    return {
        "os_color_system": os_color_system,
        "display_profile_provider": profile_provider,
        "display_profile_status": display_profile.get("status"),
        "preview_cmm": "LittleCMS2 via Pillow ImageCms",
        "profile_creation_engine": "ArgyllCMS colprof",
        "profile_validation_engine": "ArgyllCMS xicclu/icclu",
        "derived_export_cmm": "ArgyllCMS cctiff",
        "surface_policy": surface_policy,
        "monitor_profile_is_working_space": False,
    }


def _display_profile_status() -> dict[str, Any]:
    detected = detect_system_display_profile()
    if detected is None:
        return {
            "status": "fallback_srgb",
            "path": None,
            "label": "sRGB",
            "sha256": None,
            "size_bytes": None,
            "message": "no se detecto perfil ICC de monitor; se usara fallback visual sRGB",
        }
    path = Path(detected).expanduser()
    return {
        "status": "ok" if path.exists() else "missing",
        "path": str(path),
        "label": display_profile_label(path),
        "sha256": _sha256_file_optional(path),
        "size_bytes": _file_size_optional(path),
        "message": "ok" if path.exists() else "perfil detectado pero no accesible",
    }


def _toolkit_status() -> dict[str, Any]:
    qt_runtime = "not-available"
    pyside = _safe_distribution_version("PySide6")
    try:
        from PySide6 import QtCore  # type: ignore[import-not-found]

        qt_runtime = QtCore.qVersion()
    except Exception:
        pass
    return {
        "pyside6": pyside,
        "qt_runtime": qt_runtime,
    }


def _cmm_status() -> dict[str, Any]:
    littlecms = "unknown"
    try:
        from PIL import ImageCms

        littlecms = str(getattr(ImageCms.core, "littlecms_version", "unknown"))
    except Exception:
        pass
    return {
        "pillow": _safe_import_version("PIL"),
        "littlecms": littlecms,
        "argyll_cctiff": _external_version_line("cctiff", ["-?"]),
        "argyll_xicclu": _external_version_line("xicclu", []),
    }


def _desktop_status() -> dict[str, Any]:
    return {
        "plasmashell": _external_version_line("plasmashell", ["--version"]),
        "kwin_wayland": _external_version_line("kwin_wayland", ["--version"]),
        "kwin_x11": _external_version_line("kwin_x11", ["--version"]),
        "qmake6": _external_version_line("qmake6", ["--version"]),
    }


def _wayland_color_status() -> dict[str, Any]:
    wayland_info = external_tool_path("wayland-info")
    if wayland_info is None:
        return {
            "available": False,
            "command": None,
            "returncode": None,
            "color_protocol_lines": [],
            "message": "wayland-info no disponible",
        }
    proc = _run_probe_command([wayland_info], timeout=5, max_output_chars=20000)
    lines = [
        line.strip()
        for line in str(proc.get("stdout") or "").splitlines()
        if any(token in line.lower() for token in ("color", "wp_color", "xx_color", "frog", "hdr"))
    ]
    return {
        "available": True,
        "command": [wayland_info],
        "returncode": proc.get("returncode"),
        "color_protocol_lines": lines[:120],
        "message": "ok" if proc.get("returncode") == 0 else proc.get("message", "wayland-info fallo"),
    }


def _colord_status() -> dict[str, Any]:
    colormgr = external_tool_path("colormgr")
    if colormgr is None:
        return {
            "available": False,
            "devices_display": [],
            "profiles": [],
            "message": "colormgr no disponible",
        }
    devices = _run_probe_command([colormgr, "get-devices-by-kind", "display"], timeout=5, max_output_chars=20000)
    profiles = _run_probe_command([colormgr, "get-profiles"], timeout=5, max_output_chars=20000)
    return {
        "available": True,
        "devices_display": _trim_nonempty_lines(devices.get("stdout"), max_lines=180),
        "profiles": _trim_nonempty_lines(profiles.get("stdout"), max_lines=180),
        "devices_returncode": devices.get("returncode"),
        "profiles_returncode": profiles.get("returncode"),
        "message": "ok" if devices.get("returncode") == 0 else devices.get("message", "colormgr fallo"),
    }


def _system_color_packages() -> dict[str, Any]:
    packages = [
        "kwin",
        "plasma-desktop",
        "plasma-workspace",
        "qt6-base",
        "qt6-wayland",
        "wayland-protocols",
        "wayland-utils",
        "colord",
        "colord-kde",
        "lcms2",
        "argyllcms",
        "displaycal",
        "python",
        "python-pyside6",
        "python-pillow",
        "python-numpy",
        "python-rawpy",
    ]
    return {
        "pacman": _query_pacman_packages(packages),
        "dpkg": _query_dpkg_packages(
            [
                "kwin-wayland",
                "plasma-desktop",
                "plasma-workspace",
                "qt6-base-dev",
                "wayland-protocols",
                "wayland-utils",
                "colord",
                "colord-kde",
                "liblcms2-2",
                "argyll",
                "displaycal",
            ]
        ),
        "brew": _query_brew_packages(["argyll-cms", "exiftool", "little-cms2", "python", "pyside"]),
    }


def _query_pacman_packages(packages: list[str]) -> dict[str, Any]:
    pacman = external_tool_path("pacman")
    if pacman is None:
        return {"available": False, "packages": {}}
    result: dict[str, Any] = {}
    for package in packages:
        proc = _run_probe_command([pacman, "-Q", package], timeout=2, max_output_chars=1000)
        line = str(proc.get("stdout") or "").strip().splitlines()
        if proc.get("returncode") == 0 and line:
            parts = line[0].split(maxsplit=1)
            result[package] = {"installed": True, "version": parts[1] if len(parts) > 1 else "unknown"}
        else:
            result[package] = {"installed": False, "version": None}
    return {"available": True, "packages": result}


def _query_dpkg_packages(packages: list[str]) -> dict[str, Any]:
    dpkg = external_tool_path("dpkg-query")
    if dpkg is None:
        return {"available": False, "packages": {}}
    result: dict[str, Any] = {}
    for package in packages:
        proc = _run_probe_command([dpkg, "-W", "-f=${Version}", package], timeout=2, max_output_chars=1000)
        if proc.get("returncode") == 0:
            result[package] = {"installed": True, "version": str(proc.get("stdout") or "").strip() or "unknown"}
        else:
            result[package] = {"installed": False, "version": None}
    return {"available": True, "packages": result}


def _query_brew_packages(packages: list[str]) -> dict[str, Any]:
    brew = external_tool_path("brew")
    if brew is None:
        return {"available": False, "packages": {}}
    result: dict[str, Any] = {}
    for package in packages:
        proc = _run_probe_command([brew, "list", "--versions", package], timeout=3, max_output_chars=1000)
        line = str(proc.get("stdout") or "").strip().splitlines()
        if proc.get("returncode") == 0 and line:
            parts = line[0].split(maxsplit=1)
            result[package] = {"installed": True, "version": parts[1] if len(parts) > 1 else "unknown"}
        else:
            result[package] = {"installed": False, "version": None}
    return {"available": True, "packages": result}


def _color_environment_warnings(
    *,
    display_profile: dict[str, Any],
    standard_profiles: dict[str, Any],
    session: dict[str, Any],
    wayland: dict[str, Any],
    packages: dict[str, Any],
) -> list[str]:
    warnings: list[str] = []
    if display_profile.get("status") != "ok":
        warnings.append("display_profile_not_detected")
    for missing in standard_profiles.get("missing_required", []):
        warnings.append(str(missing))
    if session.get("is_wayland") and wayland.get("available") and not wayland.get("color_protocol_lines"):
        warnings.append("wayland_color_protocols_not_reported")
    pacman = packages.get("pacman") if isinstance(packages.get("pacman"), dict) else {}
    pacman_packages = pacman.get("packages") if isinstance(pacman.get("packages"), dict) else {}
    for required in ("argyllcms", "colord", "lcms2"):
        status = pacman_packages.get(required)
        if isinstance(status, dict) and status.get("installed") is False:
            warnings.append(f"pacman_package_missing:{required}")
    return warnings


def _external_version_line(command: str, args: list[str]) -> str:
    tool = external_tool_path(command)
    if tool is None:
        return "not-available"
    proc = _run_probe_command([tool, *args], timeout=5, max_output_chars=3000)
    text = "\n".join(_trim_nonempty_lines(proc.get("stdout"), max_lines=3))
    if text:
        return text
    return "ok" if proc.get("returncode") == 0 else "unknown"


def _run_probe_command(args: list[str], *, timeout: float, max_output_chars: int) -> dict[str, Any]:
    try:
        proc = run_external(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
            timeout=timeout,
        )
    except Exception as exc:
        return {"returncode": None, "stdout": "", "message": str(exc)}
    output = str(proc.stdout or "")
    if len(output) > max_output_chars:
        output = output[:max_output_chars] + "\n...[truncated]"
    return {"returncode": proc.returncode, "stdout": output, "message": "ok" if proc.returncode == 0 else "command_failed"}


def _trim_nonempty_lines(value: Any, *, max_lines: int) -> list[str]:
    lines = [line.rstrip() for line in str(value or "").splitlines() if line.strip()]
    return lines[:max_lines]


def _os_release() -> dict[str, str]:
    path = Path("/etc/os-release")
    if not path.exists():
        return {}
    result: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line or line.lstrip().startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            result[key] = value.strip().strip('"')
    except OSError:
        return {}
    return result


def _sha256_file_optional(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        h = hashlib.sha256()
        with Path(path).expanduser().open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _file_size_optional(path: Path | None) -> int | None:
    if path is None:
        return None
    try:
        return Path(path).expanduser().stat().st_size
    except OSError:
        return None


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
