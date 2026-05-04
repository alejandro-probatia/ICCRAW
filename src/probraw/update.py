from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
import platform
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from typing import Any
from urllib import request

from .version import __version__

DEFAULT_RELEASE_REPOSITORY = os.environ.get(
    "PROBRAW_RELEASE_REPOSITORY",
    "alejandro-probatia/ProbRAW",
).strip()
DEFAULT_RELEASE_API_URL = os.environ.get(
    "PROBRAW_RELEASE_API_URL",
    f"https://api.github.com/repos/{DEFAULT_RELEASE_REPOSITORY}/releases/latest",
).strip()


@dataclass(slots=True)
class UpdateCheckResult:
    current_version: str
    latest_version: str | None
    update_available: bool
    is_latest: bool | None
    repository: str
    release_url: str | None
    api_url: str
    asset_url: str | None
    asset_name: str | None
    published_at: str | None
    checksum_url: str | None = None
    checksum_name: str | None = None
    checksum_sha256: str | None = None
    error: str | None = None
    raw_payload: dict[str, Any] | None = None


def _normalize_version_text(value: str | None) -> str:
    text = str(value or "").strip()
    if text.lower().startswith("v"):
        text = text[1:]
    return text


def _version_key(value: str | None) -> tuple[int, ...]:
    text = _normalize_version_text(value)
    parts = [int(p) for p in re.findall(r"\d+", text)]
    return tuple(parts)


def compare_versions(left: str | None, right: str | None) -> int:
    a = _version_key(left)
    b = _version_key(right)
    n = max(len(a), len(b))
    a_full = list(a) + [0] * (n - len(a))
    b_full = list(b) + [0] * (n - len(b))
    for av, bv in zip(a_full, b_full):
        if av < bv:
            return -1
        if av > bv:
            return 1
    return 0


def _linux_distribution_ids() -> set[str]:
    candidates: list[Path] = []
    override = os.environ.get("PROBRAW_OS_RELEASE", "").strip()
    if override:
        candidates.append(Path(override))
    candidates.extend([Path("/etc/os-release"), Path("/usr/lib/os-release")])

    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue

        ids: set[str] = set()
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key not in {"ID", "ID_LIKE"}:
                continue
            try:
                values = shlex.split(value)
            except ValueError:
                values = [value.strip().strip("\"'")]
            for parsed in values:
                ids.update(part.strip().lower() for part in parsed.split() if part.strip())
        if ids:
            return ids
    return set()


def _wanted_asset_extensions() -> list[str]:
    if sys.platform == "win32":
        return [".exe", ".msi"]
    if sys.platform == "darwin":
        return [".pkg", ".dmg"]
    if sys.platform.startswith("linux"):
        ids = _linux_distribution_ids()
        if ids & {"debian", "ubuntu", "linuxmint", "pop", "raspbian"}:
            return [".deb", ".appimage"]
        if ids & {"fedora", "rhel", "centos", "rocky", "almalinux", "suse", "opensuse"}:
            return [".rpm", ".appimage"]
        return [".appimage"]
    return []


_ARCH_ALIASES: dict[str, set[str]] = {
    "amd64": {"amd64", "x86_64", "x64"},
    "arm64": {"arm64", "aarch64"},
    "armhf": {"armhf", "armv7", "armv7l"},
    "i386": {"i386", "i686", "x86"},
}
_KNOWN_ARCH_TOKENS = {token for aliases in _ARCH_ALIASES.values() for token in aliases}


def _current_architecture_tokens() -> set[str]:
    tokens: set[str] = set()
    machine = platform.machine().strip().lower()
    if machine:
        tokens.add(machine)

    if sys.platform.startswith("linux"):
        dpkg = shutil.which("dpkg")
        if dpkg:
            try:
                arch = subprocess.check_output(
                    [dpkg, "--print-architecture"],
                    stderr=subprocess.DEVNULL,
                    text=True,
                    timeout=2,
                ).strip().lower()
            except Exception:
                arch = ""
            if arch:
                tokens.add(arch)

    expanded = set(tokens)
    for aliases in _ARCH_ALIASES.values():
        if tokens & aliases:
            expanded.update(aliases)
    return expanded


def _asset_name_has_token(name: str, token: str) -> bool:
    return re.search(rf"(^|[^a-z0-9]){re.escape(token.lower())}($|[^a-z0-9])", name.lower()) is not None


def _asset_arch_score(name: str, native_tokens: set[str]) -> int:
    if any(_asset_name_has_token(name, token) for token in native_tokens):
        return 2
    if any(_asset_name_has_token(name, token) for token in _KNOWN_ARCH_TOKENS):
        return -1
    return 1


def _pick_asset(assets: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    if not assets:
        return None, None

    wanted_ext = _wanted_asset_extensions()
    normalized = [
        (
            str(a.get("name") or ""),
            str(a.get("browser_download_url") or ""),
        )
        for a in assets
    ]
    native_arch_tokens = _current_architecture_tokens()

    for ext in wanted_ext:
        candidates = [
            (name, url, _asset_arch_score(name, native_arch_tokens))
            for name, url in normalized
            if url and name.lower().endswith(ext)
        ]
        for score in (2, 1):
            for name, url, candidate_score in candidates:
                if candidate_score == score:
                    return name, url

    return None, None


def _pick_checksum_asset(assets: list[dict[str, Any]], installer_name: str | None) -> tuple[str | None, str | None]:
    if not installer_name:
        return None, None
    expected = installer_name.lower()
    suffixes = (".sha256", ".sha256sum", ".sha256.txt")
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "")
        url = str(asset.get("browser_download_url") or "")
        lower = name.lower()
        if not url:
            continue
        if any(lower == expected + suffix for suffix in suffixes):
            return name, url
        if lower.endswith(suffixes) and expected in lower:
            return name, url
    return None, None


def _extract_sha256(text: str) -> str | None:
    match = re.search(r"\b[a-fA-F0-9]{64}\b", text)
    return match.group(0).lower() if match else None


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_url(url: str, out_path: Path, *, user_agent: str, timeout: float) -> None:
    req = request.Request(url, headers={"User-Agent": user_agent})
    with request.urlopen(req, timeout=float(timeout)) as response, out_path.open("wb") as handle:
        shutil.copyfileobj(response, handle)


def _terminal_prefix() -> list[str] | None:
    for command, args in (
        ("x-terminal-emulator", ["-e"]),
        ("gnome-terminal", ["--"]),
        ("konsole", ["-e"]),
        ("xfce4-terminal", ["-e"]),
        ("xterm", ["-e"]),
    ):
        path = shutil.which(command)
        if path:
            return [path, *args]
    return None


def _launch_privileged(command: list[str], *, manual_hint: str) -> None:
    pkexec = shutil.which("pkexec")
    if pkexec:
        subprocess.Popen([pkexec, *command])
        return

    sudo = shutil.which("sudo")
    terminal = _terminal_prefix()
    if sudo and terminal:
        subprocess.Popen([*terminal, sudo, *command])
        return

    raise RuntimeError(
        "No se encontro pkexec ni una terminal con sudo para instalar automaticamente. "
        f"Instala el paquete manualmente con: {manual_hint}"
    )


def _launch_deb_installer(installer: Path, *, silent: bool) -> None:
    yes_args = ["-y"] if silent else []
    for manager, args in (
        ("apt-get", ["install", *yes_args, str(installer)]),
        ("apt", ["install", *yes_args, str(installer)]),
        ("dpkg", ["-i", str(installer)]),
    ):
        manager_path = shutil.which(manager)
        if manager_path:
            _launch_privileged(
                [manager_path, *args],
                manual_hint=f"sudo {manager} {' '.join(shlex.quote(arg) for arg in args)}",
            )
            return

    raise RuntimeError(
        "No se encontro apt-get, apt ni dpkg para instalar el paquete Debian local. "
        f"Instala el paquete manualmente con: sudo apt install {shlex.quote(str(installer))}"
    )


def _launch_rpm_installer(installer: Path, *, silent: bool) -> None:
    yes_args = ["-y"] if silent else []
    for manager, args in (
        ("dnf", ["install", *yes_args, str(installer)]),
        ("yum", ["install", *yes_args, str(installer)]),
        ("zypper", ["install", *yes_args, str(installer)]),
        ("rpm", ["-U", str(installer)]),
    ):
        manager_path = shutil.which(manager)
        if manager_path:
            _launch_privileged(
                [manager_path, *args],
                manual_hint=f"sudo {manager} {' '.join(shlex.quote(arg) for arg in args)}",
            )
            return

    raise RuntimeError(
        "No se encontro dnf, yum, zypper ni rpm para instalar el paquete RPM local. "
        f"Instala el paquete manualmente con tu gestor de paquetes: {installer}"
    )


def check_latest_release(*, api_url: str | None = None, repository: str | None = None, timeout: float = 8.0) -> UpdateCheckResult:
    api = str(api_url or DEFAULT_RELEASE_API_URL).strip()
    repo = str(repository or DEFAULT_RELEASE_REPOSITORY).strip()
    current = _normalize_version_text(__version__)
    req = request.Request(
        api,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"ProbRAW/{current}",
        },
    )
    try:
        with request.urlopen(req, timeout=float(timeout)) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return UpdateCheckResult(
            current_version=current,
            latest_version=None,
            update_available=False,
            is_latest=None,
            repository=repo,
            release_url=f"https://github.com/{repo}/releases",
            api_url=api,
            asset_url=None,
            asset_name=None,
            published_at=None,
            error=str(exc),
        )

    tag = _normalize_version_text(str(payload.get("tag_name") or ""))
    release_url = str(payload.get("html_url") or f"https://github.com/{repo}/releases")
    assets = payload.get("assets") if isinstance(payload.get("assets"), list) else []
    release_assets = [a for a in assets if isinstance(a, dict)]
    asset_name, asset_url = _pick_asset(release_assets)
    checksum_name, checksum_url = _pick_checksum_asset(release_assets, asset_name)
    cmp = compare_versions(current, tag)
    update_available = bool(cmp < 0)
    is_latest = bool(cmp >= 0)
    return UpdateCheckResult(
        current_version=current,
        latest_version=tag or None,
        update_available=update_available,
        is_latest=is_latest,
        repository=repo,
        release_url=release_url,
        api_url=api,
        asset_url=asset_url,
        asset_name=asset_name,
        checksum_url=checksum_url,
        checksum_name=checksum_name,
        published_at=str(payload.get("published_at") or "") or None,
        error=None,
        raw_payload=payload,
    )


def download_update_asset(result: UpdateCheckResult, *, target_dir: Path | None = None, timeout: float = 60.0) -> Path:
    if not result.asset_url:
        raise RuntimeError("La release no expone un asset descargable para esta plataforma.")
    dest_dir = Path(target_dir) if target_dir is not None else Path(tempfile.mkdtemp(prefix="probraw-update-"))
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = result.asset_name or Path(result.asset_url).name or "probraw-update.bin"
    out_path = dest_dir / name
    user_agent = f"ProbRAW/{result.current_version}"
    _download_url(result.asset_url, out_path, user_agent=user_agent, timeout=timeout)

    expected_sha256 = result.checksum_sha256
    if result.checksum_url:
        checksum_name = result.checksum_name or Path(result.checksum_url).name or f"{name}.sha256"
        checksum_path = dest_dir / checksum_name
        _download_url(result.checksum_url, checksum_path, user_agent=user_agent, timeout=timeout)
        expected_sha256 = _extract_sha256(checksum_path.read_text(encoding="utf-8", errors="replace"))
        if not expected_sha256:
            raise RuntimeError(f"No se pudo leer SHA-256 valido desde {checksum_path.name}.")

    if expected_sha256:
        actual_sha256 = _file_sha256(out_path)
        if actual_sha256.lower() != expected_sha256.lower():
            raise RuntimeError(
                "La descarga del instalador no coincide con el SHA-256 publicado "
                f"(esperado {expected_sha256.lower()}, obtenido {actual_sha256.lower()})."
            )
    return out_path


def launch_installer(path: Path, *, silent: bool = True) -> None:
    installer = Path(path).expanduser().resolve()
    suffix = installer.suffix.lower()
    if sys.platform == "win32":
        if suffix == ".msi":
            args = ["msiexec", "/i", str(installer)]
            if silent:
                args.extend(["/qn", "/norestart"])
            subprocess.Popen(args)
            return
        if suffix == ".exe":
            args = [str(installer)]
            if silent:
                args.extend(["/SP-", "/VERYSILENT", "/NORESTART"])
            subprocess.Popen(args)
            return
        os.startfile(str(installer))  # type: ignore[attr-defined]
        return
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(installer)])
        return
    if suffix == ".deb":
        _launch_deb_installer(installer, silent=silent)
        return
    if suffix == ".rpm":
        _launch_rpm_installer(installer, silent=silent)
        return
    if suffix == ".appimage":
        installer.chmod(installer.stat().st_mode | 0o100)
        subprocess.Popen([str(installer)])
        return
    subprocess.Popen(["xdg-open", str(installer)])


def auto_update(*, check: UpdateCheckResult, silent: bool = True, target_dir: Path | None = None) -> Path:
    installer = download_update_asset(check, target_dir=target_dir)
    launch_installer(installer, silent=silent)
    return installer
