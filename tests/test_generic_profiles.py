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
