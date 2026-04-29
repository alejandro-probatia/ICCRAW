from pathlib import Path
import json

from probraw import metadata_viewer
from probraw.metadata_viewer import (
    inspect_file_metadata,
    metadata_display_sections,
    metadata_sections_text,
    read_exif_gps_metadata,
    read_probraw_proof_metadata,
)
from probraw.provenance.c2pa import RAW_LINK_ASSERTION_LABEL


class FakeCompletedProcess:
    def __init__(self, stdout: str, returncode: int = 0) -> None:
        self.stdout = stdout
        self.returncode = returncode


class FakeC2PAClient:
    def read_manifest_store(self, asset_path: Path) -> dict:
        return {
            "active_manifest": "urn:probraw:test",
            "manifests": {
                "urn:probraw:test": {
                    "signature_info": {"alg": "Ps256", "common_name": "Test"},
                    "assertions": [
                        {"label": "c2pa.actions.v2", "data": {}},
                        {"label": RAW_LINK_ASSERTION_LABEL, "data": {"schema": RAW_LINK_ASSERTION_LABEL}},
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
        metadata_viewer,
        "run_external",
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
    assert result["c2pa"]["active_manifest_id"] == "urn:probraw:test"
    assert "c2pa.actions.v2" in result["c2pa"]["assertion_labels"]
    assert "signed.tiff" in sections["summary"]


def test_c2pa_absence_is_not_reported_as_valid():
    display = metadata_display_sections(
        {
            "file": {"basename": "unsigned.tiff"},
            "exif_gps": {"groups": {}, "all": {}, "gps": {}},
            "c2pa": {"status": "absent_or_invalid", "reason": "no manifest", "manifest_store": None},
        }
    )

    c2pa_items = {
        item["label"]: item["value"]
        for group in display["c2pa"]
        for item in group["items"]
    }
    assert c2pa_items["Estado"] == "Ausente o no valido"
    assert c2pa_items["Validacion"] == "no manifest"
    assert c2pa_items["Vinculo RAW-TIFF C2PA"] == "No disponible"


def test_probraw_proof_metadata_reads_legacy_nexoraw_sidecar(tmp_path: Path):
    image = tmp_path / "rendered.tiff"
    image.write_bytes(b"tiff")
    legacy_proof = image.with_suffix(image.suffix + ".nexoraw.proof.json")
    legacy_proof.write_text(
        json.dumps({"schema": "org.probatia.nexoraw.proof.v1"}),
        encoding="utf-8",
    )

    result = read_probraw_proof_metadata(image)

    assert result["status"] == "invalid"
    assert result["proof_path"] == str(legacy_proof)


def test_metadata_display_exposes_probraw_proof_render_settings():
    display = metadata_display_sections(
        {
            "file": {"basename": "rendered.tiff"},
            "exif_gps": {"groups": {}, "all": {}, "gps": {}},
            "c2pa": {"status": "skipped"},
            "probraw_proof": {
                "status": "ok",
                "proof_path": "rendered.tiff.probraw.proof.json",
                "signature_valid": True,
                "public_key_sha256_actual": "pub",
                "proof": {
                    "subject": {
                        "source_raw": {"sha256": "raw-sha", "basename": "capture.NEF"},
                        "output_tiff": {"sha256": "tiff-sha", "basename": "rendered.tiff"},
                    },
                    "signer": {"name": "Unit Test"},
                    "process": {
                        "recipe_sha256": "recipe-sha",
                        "render_settings_sha256": "settings-sha",
                        "demosaicing_algorithm": "dcb",
                        "color_management_mode": "camera_rgb_with_input_icc",
                        "render_settings": {
                            "settings_sha256": "settings-sha",
                            "recipe_parameters": {
                                "raw_developer": "libraw",
                                "demosaic_algorithm": "dcb",
                                "black_level_mode": "metadata",
                                "white_balance_mode": "camera_metadata",
                                "wb_multipliers": [2.0, 1.0, 1.4, 1.0],
                                "exposure_compensation": 0.25,
                                "tone_curve": "linear",
                                "working_space": "scene_linear_camera_rgb",
                                "output_space": "camera_rgb",
                                "output_linear": True,
                            },
                            "detail_adjustments": {
                                "sharpen_amount": 0.7,
                                "sharpen_radius": 1.2,
                            },
                            "render_adjustments": {
                                "contrast": 0.18,
                                "brightness_ev": 0.1,
                            },
                            "color_management": {
                                "mode": "camera_rgb_with_input_icc",
                                "working_space": "scene_linear_camera_rgb",
                                "output_space": "camera_rgb",
                                "raw_color_pipeline": {
                                    "raw_engine": "LibRaw/rawpy",
                                    "camera_to_xyz": "deferred_to_embedded_session_input_icc",
                                    "export_transform": "embed_session_input_icc_without_output_conversion",
                                    "display_transform": "preview_sRGB_to_monitor_ICC_with_LittleCMS_ImageCms",
                                    "libraw_linear_steps": ["raw_unpack", "demosaicing"],
                                },
                            },
                            "reproducibility": {
                                "complete_settings_embedded": True,
                                "settings_sha256_role": "integrity_check",
                                "experimental_replay_inputs": ["recipe_parameters"],
                            },
                            "context": {"entrypoint": "unit-test"},
                        },
                    },
                },
            },
        }
    )

    c2pa_items = {
        item["label"]: item["value"]
        for group in display["c2pa"]
        for item in group["items"]
    }
    titles = [group["title"] for group in display["c2pa"]]
    assert "Ajustes TIFF ProbRAW Proof: detalle y nitidez" in titles
    assert c2pa_items["sharpen_amount"] == "0.7"
    assert c2pa_items["contrast"] == "0.18"
    assert c2pa_items["Camera RGB -> XYZ/RGB"] == "deferred_to_embedded_session_input_icc"
    assert c2pa_items["Ajustes completos incrustados"] == "True"
