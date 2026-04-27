from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any
from urllib import request

from .version import __version__

DEFAULT_RELEASE_REPOSITORY = os.environ.get(
    "NEXORAW_RELEASE_REPOSITORY",
    "alejandro-probatia/NexoRAW",
).strip()
DEFAULT_RELEASE_API_URL = os.environ.get(
    "NEXORAW_RELEASE_API_URL",
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


def _pick_asset(assets: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    if not assets:
        return None, None

    wanted_ext = [".exe", ".msi"] if sys.platform == "win32" else [".pkg", ".dmg", ".deb", ".rpm", ".appimage", ".tar.gz"]
    normalized = [
        (
            str(a.get("name") or ""),
            str(a.get("browser_download_url") or ""),
        )
        for a in assets
    ]

    for ext in wanted_ext:
        for name, url in normalized:
            if name.lower().endswith(ext):
                return name, url

    for name, url in normalized:
        if url:
            return name, url
    return None, None


def check_latest_release(*, api_url: str | None = None, repository: str | None = None, timeout: float = 8.0) -> UpdateCheckResult:
    api = str(api_url or DEFAULT_RELEASE_API_URL).strip()
    repo = str(repository or DEFAULT_RELEASE_REPOSITORY).strip()
    current = _normalize_version_text(__version__)
    req = request.Request(
        api,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"NexoRAW/{current}",
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
    asset_name, asset_url = _pick_asset([a for a in assets if isinstance(a, dict)])
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
        published_at=str(payload.get("published_at") or "") or None,
        error=None,
        raw_payload=payload,
    )


def download_update_asset(result: UpdateCheckResult, *, target_dir: Path | None = None, timeout: float = 60.0) -> Path:
    if not result.asset_url:
        raise RuntimeError("La release no expone un asset descargable para esta plataforma.")
    dest_dir = Path(target_dir) if target_dir is not None else Path(tempfile.mkdtemp(prefix="nexoraw-update-"))
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = result.asset_name or Path(result.asset_url).name or "nexoraw-update.bin"
    out_path = dest_dir / name
    req = request.Request(
        result.asset_url,
        headers={"User-Agent": f"NexoRAW/{result.current_version}"},
    )
    with request.urlopen(req, timeout=float(timeout)) as response, out_path.open("wb") as handle:
        shutil.copyfileobj(response, handle)
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
    subprocess.Popen(["xdg-open", str(installer)])


def auto_update(*, check: UpdateCheckResult, silent: bool = True, target_dir: Path | None = None) -> Path:
    installer = download_update_asset(check, target_dir=target_dir)
    launch_installer(installer, silent=silent)
    return installer

