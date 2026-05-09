from pathlib import Path

import probraw.profile.generic as generic_module
from probraw.profile.generic import find_standard_output_profile


def test_standard_profile_search_prefers_exact_profile_before_compatible(tmp_path: Path, monkeypatch):
    argyll_ref = tmp_path / "argyll" / "ref"
    system_color = tmp_path / "system" / "color"
    argyll_ref.mkdir(parents=True)
    system_color.mkdir(parents=True)
    compatible = argyll_ref / "ClayRGB1998.icm"
    exact = system_color / "AdobeRGB1998.icc"
    compatible.write_bytes(b"c" * 256)
    exact.write_bytes(b"a" * 256)

    monkeypatch.setattr(generic_module, "_standard_profile_search_dirs", lambda: [argyll_ref, system_color])

    assert find_standard_output_profile("adobe_rgb") == exact


def test_standard_profile_search_finds_argyllcms_ref_next_to_arch_binary(tmp_path: Path, monkeypatch):
    bin_dir = tmp_path / "bin"
    ref_dir = tmp_path / "share" / "argyllcms" / "ref"
    bin_dir.mkdir(parents=True)
    ref_dir.mkdir(parents=True)
    prophoto = ref_dir / "ProPhoto.icm"
    prophoto.write_bytes(b"p" * 256)

    monkeypatch.delenv("PROBRAW_STANDARD_ICC_DIR", raising=False)
    monkeypatch.delenv("PROBRAW_ARGYLL_REF_DIR", raising=False)
    monkeypatch.setattr(
        generic_module,
        "external_tool_path",
        lambda command: str(bin_dir / command) if command == "colprof" else None,
    )

    assert find_standard_output_profile("prophoto_rgb") == prophoto


def test_standard_profile_search_accepts_colord_prophoto_filename(tmp_path: Path, monkeypatch):
    profile_dir = tmp_path / "color" / "icc" / "colord"
    profile_dir.mkdir(parents=True)
    prophoto = profile_dir / "ProPhotoRGB.icc"
    prophoto.write_bytes(b"p" * 256)

    monkeypatch.setattr(generic_module, "_standard_profile_search_dirs", lambda: [profile_dir])

    assert find_standard_output_profile("prophoto_rgb") == prophoto


def test_standard_profile_search_uses_system_profile_description(tmp_path: Path, monkeypatch):
    system_dir = tmp_path / "system" / "icc"
    nested = system_dir / "manufacturer"
    nested.mkdir(parents=True)
    profile = nested / "camera-output.icc"
    profile.write_bytes(b"p" * 256)

    monkeypatch.setattr(generic_module, "_standard_profile_search_dirs", lambda: [system_dir])
    monkeypatch.setattr(generic_module, "_profile_description", lambda path: "ProPhoto RGB" if path == profile else "")

    assert find_standard_output_profile("prophoto_rgb") == profile


def test_standard_profile_search_rejects_linear_prophoto_description(tmp_path: Path, monkeypatch):
    system_dir = tmp_path / "system" / "icc"
    system_dir.mkdir(parents=True)
    linear = system_dir / "ProPhotoLin.icm"
    linear.write_bytes(b"p" * 256)

    monkeypatch.setattr(generic_module, "_standard_profile_search_dirs", lambda: [system_dir])
    monkeypatch.setattr(generic_module, "_profile_description", lambda path: "ProPhoto RGB (Linear)")

    assert find_standard_output_profile("prophoto_rgb") is None


def test_standard_profile_search_dirs_include_xdg_and_colord_locations(tmp_path: Path, monkeypatch):
    data_home = tmp_path / "data-home"
    data_dir = tmp_path / "data-dir"
    monkeypatch.setattr(generic_module.sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    monkeypatch.setenv("XDG_DATA_DIRS", str(data_dir))
    monkeypatch.delenv("PROBRAW_STANDARD_ICC_DIR", raising=False)
    monkeypatch.delenv("PROBRAW_ARGYLL_REF_DIR", raising=False)
    monkeypatch.setattr(generic_module, "external_tool_path", lambda _command: None)

    dirs = generic_module.standard_profile_search_dirs()

    assert data_home / "color" / "icc" in dirs
    assert data_dir / "color" / "icc" in dirs
    assert Path("/var/lib/colord/icc") in dirs
