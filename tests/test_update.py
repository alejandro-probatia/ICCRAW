from __future__ import annotations

from dataclasses import asdict
import hashlib
import io
import json
from pathlib import Path

import pytest
import probraw.update as update_mod


def test_compare_versions_with_revision_suffix() -> None:
    assert update_mod.compare_versions("0.2.0-r1", "0.2.0") > 0
    assert update_mod.compare_versions("v0.2.1", "0.2.0-r9") > 0
    assert update_mod.compare_versions("0.2.0", "0.2.0") == 0


def test_check_latest_release_network_error(monkeypatch) -> None:
    def raise_error(*_args, **_kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(update_mod.request, "urlopen", raise_error)
    result = update_mod.check_latest_release()
    assert result.error is not None
    assert result.update_available is False
    assert result.is_latest is None


def test_check_latest_release_payload(monkeypatch) -> None:
    monkeypatch.setattr(update_mod.sys, "platform", "win32")
    payload = {
        "tag_name": "v0.2.9",
        "html_url": "https://example.com/release",
        "published_at": "2026-04-27T10:00:00Z",
        "assets": [
            {
                "name": "ProbRAW-0.2.9-Setup.exe",
                "browser_download_url": "https://example.com/ProbRAW-0.2.9-Setup.exe",
            }
        ],
    }

    class _FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_open(*_args, **_kwargs):
        return _FakeResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(update_mod.request, "urlopen", fake_open)
    result = update_mod.check_latest_release()
    serialized = asdict(result)
    assert serialized["latest_version"] == "0.2.9"
    assert serialized["release_url"] == "https://example.com/release"
    assert serialized["asset_name"] == "ProbRAW-0.2.9-Setup.exe"
    assert serialized["asset_url"] == "https://example.com/ProbRAW-0.2.9-Setup.exe"
    assert serialized["error"] is None


def test_check_latest_release_linux_picks_deb_not_source_artifacts(monkeypatch) -> None:
    monkeypatch.setattr(update_mod.sys, "platform", "linux")
    monkeypatch.setattr(update_mod, "_linux_distribution_ids", lambda: {"debian"})
    payload = {
        "tag_name": "v0.3.6",
        "html_url": "https://example.com/release",
        "published_at": "2026-05-02T10:00:00Z",
        "assets": [
            {
                "name": "probraw-0.3.6-py3-none-any.whl",
                "browser_download_url": "https://example.com/probraw-0.3.6-py3-none-any.whl",
            },
            {
                "name": "probraw-0.3.6.tar.gz",
                "browser_download_url": "https://example.com/probraw-0.3.6.tar.gz",
            },
            {
                "name": "probraw_0.3.6_amd64.deb",
                "browser_download_url": "https://example.com/probraw_0.3.6_amd64.deb",
            },
            {
                "name": "probraw_0.3.6_amd64.deb.sha256",
                "browser_download_url": "https://example.com/probraw_0.3.6_amd64.deb.sha256",
            },
        ],
    }

    class _FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_open(*_args, **_kwargs):
        return _FakeResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(update_mod.request, "urlopen", fake_open)
    result = update_mod.check_latest_release()

    assert result.asset_name == "probraw_0.3.6_amd64.deb"
    assert result.asset_url == "https://example.com/probraw_0.3.6_amd64.deb"


def test_check_latest_release_linux_picks_native_arch_deb_and_checksum(monkeypatch) -> None:
    monkeypatch.setattr(update_mod.sys, "platform", "linux")
    monkeypatch.setattr(update_mod, "_linux_distribution_ids", lambda: {"debian"})
    monkeypatch.setattr(update_mod, "_current_architecture_tokens", lambda: {"amd64", "x86_64", "x64"})
    payload = {
        "tag_name": "v0.3.9",
        "html_url": "https://example.com/release",
        "published_at": "2026-05-03T10:00:00Z",
        "assets": [
            {
                "name": "probraw_0.3.9_arm64.deb",
                "browser_download_url": "https://example.com/probraw_0.3.9_arm64.deb",
            },
            {
                "name": "probraw_0.3.9_amd64.deb",
                "browser_download_url": "https://example.com/probraw_0.3.9_amd64.deb",
            },
            {
                "name": "probraw_0.3.9_amd64.deb.sha256",
                "browser_download_url": "https://example.com/probraw_0.3.9_amd64.deb.sha256",
            },
        ],
    }

    class _FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_open(*_args, **_kwargs):
        return _FakeResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(update_mod.request, "urlopen", fake_open)
    result = update_mod.check_latest_release()

    assert result.asset_name == "probraw_0.3.9_amd64.deb"
    assert result.asset_url == "https://example.com/probraw_0.3.9_amd64.deb"
    assert result.checksum_name == "probraw_0.3.9_amd64.deb.sha256"
    assert result.checksum_url == "https://example.com/probraw_0.3.9_amd64.deb.sha256"


def test_check_latest_release_linux_does_not_pick_foreign_arch_deb(monkeypatch) -> None:
    monkeypatch.setattr(update_mod.sys, "platform", "linux")
    monkeypatch.setattr(update_mod, "_linux_distribution_ids", lambda: {"debian"})
    monkeypatch.setattr(update_mod, "_current_architecture_tokens", lambda: {"amd64", "x86_64", "x64"})
    payload = {
        "tag_name": "v0.3.9",
        "html_url": "https://example.com/release",
        "published_at": "2026-05-03T10:00:00Z",
        "assets": [
            {
                "name": "probraw_0.3.9_arm64.deb",
                "browser_download_url": "https://example.com/probraw_0.3.9_arm64.deb",
            },
        ],
    }

    class _FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_open(*_args, **_kwargs):
        return _FakeResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(update_mod.request, "urlopen", fake_open)
    result = update_mod.check_latest_release()

    assert result.asset_name is None
    assert result.asset_url is None


def test_check_latest_release_linux_does_not_pick_non_installer_fallback(monkeypatch) -> None:
    monkeypatch.setattr(update_mod.sys, "platform", "linux")
    monkeypatch.setattr(update_mod, "_linux_distribution_ids", lambda: {"debian"})
    payload = {
        "tag_name": "v0.3.6",
        "html_url": "https://example.com/release",
        "published_at": "2026-05-02T10:00:00Z",
        "assets": [
            {
                "name": "probraw-0.3.6-py3-none-any.whl",
                "browser_download_url": "https://example.com/probraw-0.3.6-py3-none-any.whl",
            },
            {
                "name": "probraw-0.3.6.tar.gz",
                "browser_download_url": "https://example.com/probraw-0.3.6.tar.gz",
            },
        ],
    }

    class _FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_open(*_args, **_kwargs):
        return _FakeResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(update_mod.request, "urlopen", fake_open)
    result = update_mod.check_latest_release()

    assert result.asset_name is None
    assert result.asset_url is None


def test_download_update_asset_verifies_sha256_sidecar(monkeypatch, tmp_path) -> None:
    installer_bytes = b"probraw deb payload"
    expected = hashlib.sha256(installer_bytes).hexdigest()
    result = update_mod.UpdateCheckResult(
        current_version="0.3.6",
        latest_version="0.3.9",
        update_available=True,
        is_latest=False,
        repository="example/probraw",
        release_url="https://example.com/release",
        api_url="https://example.com/api",
        asset_url="https://example.com/probraw_0.3.9_amd64.deb",
        asset_name="probraw_0.3.9_amd64.deb",
        checksum_url="https://example.com/probraw_0.3.9_amd64.deb.sha256",
        checksum_name="probraw_0.3.9_amd64.deb.sha256",
        published_at="2026-05-03T10:00:00Z",
    )

    class _FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_open(req, **_kwargs):
        url = req.full_url
        if url.endswith(".sha256"):
            return _FakeResponse(f"{expected}  dist/probraw_0.3.9_amd64.deb\n".encode("utf-8"))
        return _FakeResponse(installer_bytes)

    monkeypatch.setattr(update_mod.request, "urlopen", fake_open)

    installer = update_mod.download_update_asset(result, target_dir=tmp_path)

    assert installer == tmp_path / "probraw_0.3.9_amd64.deb"
    assert installer.read_bytes() == installer_bytes
    assert (tmp_path / "probraw_0.3.9_amd64.deb.sha256").exists()


def test_download_update_asset_rejects_sha256_mismatch(monkeypatch, tmp_path) -> None:
    result = update_mod.UpdateCheckResult(
        current_version="0.3.6",
        latest_version="0.3.9",
        update_available=True,
        is_latest=False,
        repository="example/probraw",
        release_url="https://example.com/release",
        api_url="https://example.com/api",
        asset_url="https://example.com/probraw_0.3.9_amd64.deb",
        asset_name="probraw_0.3.9_amd64.deb",
        checksum_url="https://example.com/probraw_0.3.9_amd64.deb.sha256",
        checksum_name="probraw_0.3.9_amd64.deb.sha256",
        published_at="2026-05-03T10:00:00Z",
    )

    class _FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_open(req, **_kwargs):
        if req.full_url.endswith(".sha256"):
            return _FakeResponse((("0" * 64) + "  probraw_0.3.9_amd64.deb\n").encode("utf-8"))
        return _FakeResponse(b"changed payload")

    monkeypatch.setattr(update_mod.request, "urlopen", fake_open)

    with pytest.raises(RuntimeError, match="SHA-256"):
        update_mod.download_update_asset(result, target_dir=tmp_path)


def test_linux_distribution_ids_parses_quoted_id_like(monkeypatch, tmp_path) -> None:
    os_release = tmp_path / "os-release"
    os_release.write_text('ID=ubuntu\nID_LIKE="debian rhel"\n', encoding="utf-8")
    monkeypatch.setenv("PROBRAW_OS_RELEASE", str(os_release))

    ids = update_mod._linux_distribution_ids()

    assert {"ubuntu", "debian", "rhel"} <= ids


def test_check_latest_release_alpine_does_not_offer_deb_as_automatic_installer(monkeypatch) -> None:
    monkeypatch.setattr(update_mod.sys, "platform", "linux")
    monkeypatch.setattr(update_mod, "_linux_distribution_ids", lambda: {"alpine"})
    payload = {
        "tag_name": "v0.3.6",
        "html_url": "https://example.com/release",
        "published_at": "2026-05-02T10:00:00Z",
        "assets": [
            {
                "name": "probraw_0.3.6_amd64.deb",
                "browser_download_url": "https://example.com/probraw_0.3.6_amd64.deb",
            },
        ],
    }

    class _FakeResponse(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_open(*_args, **_kwargs):
        return _FakeResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(update_mod.request, "urlopen", fake_open)
    result = update_mod.check_latest_release()

    assert result.asset_name is None
    assert result.asset_url is None


def test_launch_installer_linux_deb_uses_local_apt_install(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(update_mod.sys, "platform", "linux")
    installer = tmp_path / "probraw_0.3.6_amd64.deb"
    installer.write_bytes(b"deb")
    launched: list[list[str]] = []

    def fake_which(command: str) -> str | None:
        return {
            "pkexec": "/usr/bin/pkexec",
            "apt-get": "/usr/bin/apt-get",
        }.get(command)

    def fake_popen(args):
        launched.append(list(args))

    monkeypatch.setattr(update_mod.shutil, "which", fake_which)
    monkeypatch.setattr(update_mod.subprocess, "Popen", fake_popen)

    update_mod.launch_installer(installer)

    assert launched == [
        [
            "/usr/bin/pkexec",
            "/usr/bin/apt-get",
            "install",
            "-y",
            str(installer.resolve()),
        ]
    ]


def test_launch_installer_linux_deb_without_privilege_helper_fails_helpfully(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(update_mod.sys, "platform", "linux")
    installer = tmp_path / "probraw_0.3.6_amd64.deb"
    installer.write_bytes(b"deb")
    monkeypatch.setattr(update_mod.shutil, "which", lambda command: "/usr/bin/apt-get" if command == "apt-get" else None)

    with pytest.raises(RuntimeError, match="Instala el paquete manualmente"):
        update_mod.launch_installer(Path(installer))
