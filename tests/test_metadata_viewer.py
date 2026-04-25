from pathlib import Path
import json

from iccraw import metadata_viewer
from iccraw.metadata_viewer import (
    inspect_file_metadata,
    metadata_display_sections,
    metadata_sections_text,
    read_exif_gps_metadata,
)


class FakeCompletedProcess:
    def __init__(self, stdout: str, returncode: int = 0) -> None:
        self.stdout = stdout
        self.returncode = returncode


class FakeC2PAClient:
    def read_manifest_store(self, asset_path: Path) -> dict:
        return {
            "active_manifest": "urn:nexoraw:test",
            "manifests": {
                "urn:nexoraw:test": {
                    "signature_info": {"alg": "Ps256", "common_name": "Test"},
                    "assertions": [
                        {"label": "c2pa.actions.v2", "data": {}},
                        {"label": "org.probatia.iccraw.raw-link", "data": {"schema": "org.probatia.iccraw.raw-link.v1"}},
                    ],
                }
            },
            "validation_status": [],
        }


def test_read_exif_gps_metadata_groups_exif_and_gps(tmp_path: Path, monkeypatch):
    image = tmp_path / "capture.tiff"
    image.write_bytes(b"tiff")
    exif_payload = [
        {
            "EXIF:Make": "Nikon",
            "EXIF:Model": "D850",
            "EXIF:DateTimeOriginal": "2026:04:25 12:00:00",
            "EXIF:ExposureTime": 0.004,
            "EXIF:FNumber": 8,
            "EXIF:ISO": 100,
            "EXIF:FocalLength": 50,
            "GPS:GPSLatitude": 40.0,
            "Composite:GPSLongitude": -3.0,
            "File:FileName": "capture.tiff",
        }
    ]

    monkeypatch.setattr(metadata_viewer, "external_tool_path", lambda name: "exiftool")
    monkeypatch.setattr(
        metadata_viewer.subprocess,
        "run",
        lambda *args, **kwargs: FakeCompletedProcess(json.dumps(exif_payload)),
    )

    result = read_exif_gps_metadata(image)

    assert result["status"] == "ok"
    assert result["exif"]["EXIF:Make"] == "Nikon"
    assert result["exif"]["EXIF:Model"] == "D850"
    assert result["gps"]["GPS:GPSLatitude"] == 40.0
    assert result["gps"]["Composite:GPSLongitude"] == -3.0
    assert "File" in result["groups"]

    display = metadata_display_sections({"file": {"basename": "capture.tiff"}, "exif_gps": result, "c2pa": {}})
    capture_group = next(group for group in display["summary"] if group["title"] == "Captura")
    capture_items = {item["label"]: item["value"] for item in capture_group["items"]}
    assert capture_items["Exposición"].startswith("1/250 s")
    assert capture_items["Apertura"] == "f/8"
    assert capture_items["ISO"] == "100"


def test_read_exif_gps_metadata_reports_missing_exiftool(tmp_path: Path, monkeypatch):
    image = tmp_path / "capture.tiff"
    image.write_bytes(b"tiff")
    monkeypatch.setattr(metadata_viewer, "external_tool_path", lambda name: None)

    result = read_exif_gps_metadata(image)

    assert result["status"] == "unavailable"
    assert result["gps"] == {}


def test_inspect_file_metadata_includes_c2pa_summary(tmp_path: Path, monkeypatch):
    image = tmp_path / "signed.tiff"
    image.write_bytes(b"tiff")
    monkeypatch.setattr(metadata_viewer, "external_tool_path", lambda name: None)

    result = inspect_file_metadata(image, c2pa_client=FakeC2PAClient())
    sections = metadata_sections_text(result)

    assert result["c2pa"]["status"] == "ok"
    assert result["c2pa"]["active_manifest_id"] == "urn:nexoraw:test"
    assert "c2pa.actions.v2" in result["c2pa"]["assertion_labels"]
    assert "signed.tiff" in sections["summary"]
