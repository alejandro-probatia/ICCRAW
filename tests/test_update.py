from __future__ import annotations

from dataclasses import asdict
import io
import json

import iccraw.update as update_mod


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
    payload = {
        "tag_name": "v0.2.9",
        "html_url": "https://example.com/release",
        "published_at": "2026-04-27T10:00:00Z",
        "assets": [
            {
                "name": "NexoRAW-0.2.9-Setup.exe",
                "browser_download_url": "https://example.com/NexoRAW-0.2.9-Setup.exe",
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
    assert serialized["asset_name"] == "NexoRAW-0.2.9-Setup.exe"
    assert serialized["asset_url"] == "https://example.com/NexoRAW-0.2.9-Setup.exe"
    assert serialized["error"] is None

