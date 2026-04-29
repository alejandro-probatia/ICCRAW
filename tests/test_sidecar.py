from __future__ import annotations

import json
from pathlib import Path

from probraw.core.models import Recipe
from probraw.sidecar import RAW_SIDECAR_SCHEMA, load_raw_sidecar, raw_sidecar_path, write_raw_sidecar


def test_write_raw_sidecar_records_recipe_profile_and_output(tmp_path: Path):
    root = tmp_path / "session"
    raw = root / "raw" / "capture.NEF"
    profile = root / "profiles" / "session.icc"
    tiff = root / "exports" / "tiff" / "capture.tiff"
    proof = tiff.with_suffix(".tiff.probraw.proof.json")
    raw.parent.mkdir(parents=True)
    profile.parent.mkdir(parents=True)
    tiff.parent.mkdir(parents=True)
    raw.write_bytes(b"raw bytes")
    profile.write_bytes(b"icc bytes")
    tiff.write_bytes(b"tiff bytes")
    proof.write_bytes(b"proof bytes")

    sidecar = write_raw_sidecar(
        raw,
        recipe=Recipe(exposure_compensation=0.25),
        development_profile={"id": "carta", "name": "Carta", "kind": "chart"},
        detail_adjustments={"sharpen": 12},
        render_adjustments={"brightness_ev": 0.1},
        icc_profile_path=profile,
        color_management_mode="camera_rgb_with_input_icc",
        session_root=root,
        session_name="Sesion",
        output_tiff=tiff,
        proof_path=proof,
        status="rendered",
    )

    assert sidecar == raw_sidecar_path(raw)
    payload = load_raw_sidecar(raw)
    assert payload["schema"] == RAW_SIDECAR_SCHEMA
    assert payload["source"]["relative_path"] == "raw/capture.NEF"
    assert payload["development_profile"]["id"] == "carta"
    assert payload["development_profile"]["profile_type"] == "advanced"
    assert payload["recipe"]["exposure_compensation"] == 0.25
    assert payload["color_management"]["icc_profile_role"] == "session_input_icc"
    assert payload["color_management"]["icc_profile_path"] == "profiles/session.icc"
    assert payload["outputs"][0]["tiff_path"] == "exports/tiff/capture.tiff"


def test_write_raw_sidecar_preserves_output_history(tmp_path: Path):
    raw = tmp_path / "capture.NEF"
    raw.write_bytes(b"raw bytes")

    first = tmp_path / "first.tiff"
    second = tmp_path / "second.tiff"
    first.write_bytes(b"first")
    second.write_bytes(b"second")

    write_raw_sidecar(raw, recipe=Recipe(), output_tiff=first, status="rendered")
    write_raw_sidecar(raw, recipe=Recipe(exposure_compensation=0.5), output_tiff=second, status="rendered")

    payload = load_raw_sidecar(raw)
    assert [Path(item["tiff_path"]).name for item in payload["outputs"]] == ["first.tiff", "second.tiff"]
    assert payload["recipe"]["exposure_compensation"] == 0.5


def test_write_raw_sidecar_records_generic_output_icc_role(tmp_path: Path):
    raw = tmp_path / "capture.NEF"
    generic_profile = tmp_path / "profiles" / "ProPhoto.icm"
    raw.write_bytes(b"raw bytes")
    generic_profile.parent.mkdir()
    generic_profile.write_bytes(b"icc bytes")

    write_raw_sidecar(
        raw,
        recipe=Recipe(output_space="prophoto_rgb", output_linear=False),
        development_profile={"id": "manual", "name": "Manual", "kind": "manual"},
        icc_profile_path=generic_profile,
        color_management_mode="standard_prophoto_rgb_output_icc",
        session_root=tmp_path,
    )

    payload = load_raw_sidecar(raw)
    assert payload["development_profile"]["profile_type"] == "basic"
    assert payload["color_management"]["icc_profile_role"] == "generic_output_icc"
    assert payload["color_management"]["icc_profile_path"] == "profiles/ProPhoto.icm"


def test_legacy_nexoraw_sidecar_is_loaded_and_migrated_on_write(tmp_path: Path):
    raw = tmp_path / "capture.NEF"
    raw.write_bytes(b"raw bytes")
    legacy = raw.with_name(raw.name + ".nexoraw.json")
    legacy.write_text(
        json.dumps(
            {
                "schema": "org.probatia.nexoraw.raw-sidecar.v1",
                "created_at": "2026-04-01T10:00:00+00:00",
                "outputs": [{"tiff_path": "old.tiff"}],
            }
        ),
        encoding="utf-8",
    )

    assert load_raw_sidecar(raw)["schema"] == "org.probatia.nexoraw.raw-sidecar.v1"

    new_sidecar = write_raw_sidecar(
        raw,
        recipe=Recipe(exposure_compensation=0.5),
        output_tiff=tmp_path / "new.tiff",
        status="rendered",
    )

    assert new_sidecar == raw_sidecar_path(raw)
    payload = load_raw_sidecar(raw)
    assert payload["schema"] == RAW_SIDECAR_SCHEMA
    assert payload["created_at"] == "2026-04-01T10:00:00+00:00"
    assert [Path(item["tiff_path"]).name for item in payload["outputs"]] == ["old.tiff", "new.tiff"]
