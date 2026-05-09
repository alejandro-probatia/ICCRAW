import hashlib
import subprocess
import types

from probraw import reporting


def _standard_profiles_ok():
    return {"status": "ok", "missing_required": [], "profiles": []}


def test_check_external_tools_reports_available_required_tools(monkeypatch):
    available = {"colprof", "xicclu", "cctiff", "exiftool"}

    def fake_tool_path(command):
        if command in available:
            return f"/usr/bin/{command}"
        return None

    def fake_run(command, **_kwargs):
        return subprocess.CompletedProcess(command, 0, stdout=f"{command[0]} 1.2.3\n")

    monkeypatch.setattr(reporting, "external_tool_path", fake_tool_path)
    monkeypatch.setattr(reporting, "run_external", fake_run)
    monkeypatch.setattr(reporting, "_check_standard_profiles", _standard_profiles_ok)

    result = reporting.check_external_tools()

    assert result["status"] == "ok"
    assert result["missing_required"] == []
    assert result["failing_required"] == []
    assert all(tool["available"] for tool in result["tools"])
    assert all(tool["ok"] for tool in result["tools"])


def test_check_external_tools_uses_icclu_fallback(monkeypatch):
    available = {"colprof", "icclu", "cctiff", "exiftool"}

    def fake_tool_path(command):
        if command in available:
            return f"/usr/bin/{command}"
        return None

    def fake_run(command, **_kwargs):
        return subprocess.CompletedProcess(command, 0, stdout=f"{command[0]} fallback\n")

    monkeypatch.setattr(reporting, "external_tool_path", fake_tool_path)
    monkeypatch.setattr(reporting, "run_external", fake_run)
    monkeypatch.setattr(reporting, "_check_standard_profiles", _standard_profiles_ok)

    result = reporting.check_external_tools()
    xicclu = next(tool for tool in result["tools"] if tool["name"] == "argyll-xicclu")

    assert result["status"] == "ok"
    assert xicclu["selected_command"] == "icclu"
    assert xicclu["path"] == "/usr/bin/icclu"


def test_check_external_tools_reports_missing_required(monkeypatch):
    monkeypatch.setattr(reporting, "external_tool_path", lambda _command: None)
    monkeypatch.setattr(reporting, "_check_standard_profiles", _standard_profiles_ok)

    result = reporting.check_external_tools()

    assert result["status"] == "missing_required"
    assert "argyll-colprof" in result["failing_required"]
    assert all(not tool["available"] for tool in result["tools"])
    assert all(not tool["ok"] for tool in result["tools"])


def test_check_external_tools_reports_missing_standard_profiles(monkeypatch):
    available = {"colprof", "xicclu", "cctiff", "exiftool"}

    def fake_tool_path(command):
        if command in available:
            return f"/usr/bin/{command}"
        return None

    def fake_run(command, **_kwargs):
        return subprocess.CompletedProcess(command, 0, stdout=f"{command[0]} 1.2.3\n")

    monkeypatch.setattr(reporting, "external_tool_path", fake_tool_path)
    monkeypatch.setattr(reporting, "run_external", fake_run)
    monkeypatch.setattr(
        reporting,
        "_check_standard_profiles",
        lambda: {
            "status": "missing_required",
            "missing_required": ["standard-profile-prophoto_rgb"],
            "profiles": [],
        },
    )

    result = reporting.check_external_tools()

    assert result["status"] == "missing_required"
    assert "standard-profile-prophoto_rgb" in result["missing_required"]
    assert "standard-profile-prophoto_rgb" in result["failing_required"]


def test_check_standard_profiles_reports_each_generic_profile(tmp_path, monkeypatch):
    available = {
        "srgb": tmp_path / "sRGB.icc",
        "adobe_rgb": tmp_path / "AdobeRGB1998.icc",
        "prophoto_rgb": None,
    }
    for path in (p for p in available.values() if p is not None):
        path.write_bytes(b"p" * 256)

    monkeypatch.setattr(reporting, "find_standard_output_profile", lambda key: available[key])

    result = reporting._check_standard_profiles()

    assert result["status"] == "missing_required"
    assert result["missing_required"] == ["standard-profile-prophoto_rgb"]
    profiles = {profile["key"]: profile for profile in result["profiles"]}
    assert profiles["srgb"]["available"] is True
    assert profiles["adobe_rgb"]["available"] is True
    assert profiles["prophoto_rgb"]["available"] is False


def test_check_color_environment_includes_display_profile_hash(tmp_path, monkeypatch):
    profile = tmp_path / "monitor.icc"
    profile.write_bytes(b"icc" * 128)

    monkeypatch.setattr(reporting, "detect_system_display_profile", lambda: profile)
    monkeypatch.setattr(reporting, "display_profile_label", lambda _path: "Monitor ICC")
    monkeypatch.setattr(reporting, "_check_standard_profiles", _standard_profiles_ok)
    monkeypatch.setattr(
        reporting,
        "_graphics_session_status",
        lambda: {"session_type": "x11", "is_wayland": False, "is_x11": True, "environment": {}},
    )
    monkeypatch.setattr(reporting, "_wayland_color_status", lambda: {"available": False, "color_protocol_lines": []})
    monkeypatch.setattr(reporting, "_system_color_packages", lambda: {"pacman": {"available": False, "packages": {}}})
    monkeypatch.setattr(reporting, "_desktop_status", lambda: {})
    monkeypatch.setattr(reporting, "_toolkit_status", lambda: {})
    monkeypatch.setattr(reporting, "_cmm_status", lambda: {})
    monkeypatch.setattr(reporting, "_colord_status", lambda: {})
    monkeypatch.setattr(reporting, "_os_release", lambda: {"ID": "cachyos"})

    result = reporting.check_color_environment()

    assert result["status"] == "ok"
    assert result["display_profile"]["path"] == str(profile)
    assert result["display_profile"]["label"] == "Monitor ICC"
    assert result["display_profile"]["sha256"] == hashlib.sha256(profile.read_bytes()).hexdigest()
    assert result["platform"]["os_release"]["ID"] == "cachyos"
    assert result["color_management_policy"]["preview_cmm"] == "LittleCMS2 via Pillow ImageCms"
    assert result["color_management_policy"]["monitor_profile_is_working_space"] is False


def test_check_color_environment_reports_actionable_warnings(monkeypatch):
    monkeypatch.setattr(
        reporting,
        "_display_profile_status",
        lambda: {"status": "fallback_srgb", "path": None},
    )
    monkeypatch.setattr(
        reporting,
        "_check_standard_profiles",
        lambda: {"status": "missing_required", "missing_required": ["standard-profile-prophoto_rgb"], "profiles": []},
    )
    monkeypatch.setattr(
        reporting,
        "_graphics_session_status",
        lambda: {"session_type": "wayland", "is_wayland": True, "is_x11": False, "environment": {}},
    )
    monkeypatch.setattr(reporting, "_wayland_color_status", lambda: {"available": True, "color_protocol_lines": []})
    monkeypatch.setattr(
        reporting,
        "_system_color_packages",
        lambda: {"pacman": {"available": True, "packages": {"argyllcms": {"installed": False}}}},
    )
    monkeypatch.setattr(reporting, "_desktop_status", lambda: {})
    monkeypatch.setattr(reporting, "_toolkit_status", lambda: {})
    monkeypatch.setattr(reporting, "_cmm_status", lambda: {})
    monkeypatch.setattr(reporting, "_colord_status", lambda: {})

    result = reporting.check_color_environment()

    assert result["status"] == "warning"
    assert "display_profile_not_detected" in result["warnings"]
    assert "standard-profile-prophoto_rgb" in result["warnings"]
    assert "wayland_color_protocols_not_reported" in result["warnings"]
    assert "pacman_package_missing:argyllcms" in result["warnings"]


def test_query_pacman_packages_parses_installed_versions(monkeypatch):
    monkeypatch.setattr(reporting, "external_tool_path", lambda command: "/usr/bin/pacman" if command == "pacman" else None)

    def fake_run(command, **_kwargs):
        if command[-1] == "colord":
            return subprocess.CompletedProcess(command, 0, stdout="colord 1.4.8-1\n")
        return subprocess.CompletedProcess(command, 1, stdout="")

    monkeypatch.setattr(reporting, "run_external", fake_run)

    result = reporting._query_pacman_packages(["colord", "missing"])

    assert result["available"] is True
    assert result["packages"]["colord"] == {"installed": True, "version": "1.4.8-1"}
    assert result["packages"]["missing"] == {"installed": False, "version": None}


def test_color_management_policy_is_platform_specific(monkeypatch):
    display = {"status": "ok"}
    monkeypatch.setattr(reporting.sys, "platform", "win32")
    win = reporting._color_management_policy(display_profile=display, session={"is_wayland": False})
    monkeypatch.setattr(reporting.sys, "platform", "darwin")
    mac = reporting._color_management_policy(display_profile=display, session={"is_wayland": False})
    monkeypatch.setattr(reporting.sys, "platform", "linux")
    linux = reporting._color_management_policy(display_profile=display, session={"is_wayland": True})

    assert win["os_color_system"] == "Windows WCS/ICM"
    assert win["display_profile_provider"] == "GetICMProfileW"
    assert mac["os_color_system"] == "macOS ColorSync"
    assert "ColorSync" in mac["display_profile_provider"]
    assert linux["os_color_system"] == "Linux colord/Wayland/X11"
    assert "Wayland" in linux["surface_policy"]
    assert all(policy["preview_cmm"] == "LittleCMS2 via Pillow ImageCms" for policy in (win, mac, linux))


def test_query_brew_packages_parses_installed_versions(monkeypatch):
    monkeypatch.setattr(reporting, "external_tool_path", lambda command: "/opt/homebrew/bin/brew" if command == "brew" else None)

    def fake_run(command, **_kwargs):
        if command[-1] == "argyll-cms":
            return subprocess.CompletedProcess(command, 0, stdout="argyll-cms 3.3.0\n")
        return subprocess.CompletedProcess(command, 1, stdout="")

    monkeypatch.setattr(reporting, "run_external", fake_run)

    result = reporting._query_brew_packages(["argyll-cms", "missing"])

    assert result["available"] is True
    assert result["packages"]["argyll-cms"] == {"installed": True, "version": "3.3.0"}
    assert result["packages"]["missing"] == {"installed": False, "version": None}


def test_check_amaze_backend_reports_gpl3_support(monkeypatch):
    monkeypatch.setattr(reporting, "rawpy_feature_flags", lambda: {"DEMOSAIC_PACK_GPL3": True})
    monkeypatch.setattr(reporting, "_safe_import_version", lambda _module: "0.26.0")
    monkeypatch.setattr(reporting, "_rawpy_distribution_version", lambda: "rawpy-demosaic==0.26.0")
    monkeypatch.setattr(reporting, "_libraw_version", lambda: "0.22.0")

    result = reporting.check_amaze_backend()

    assert result["status"] == "ok"
    assert result["amaze_supported"] is True
    assert result["rawpy_distribution"] == "rawpy-demosaic==0.26.0"


def test_check_c2pa_support_reports_native_runtime(tmp_path, monkeypatch):
    package = tmp_path / "c2pa"
    libs = package / "libs"
    libs.mkdir(parents=True)
    (libs / "c2pa_c.dll").write_bytes(b"dll")
    module = types.SimpleNamespace(
        __file__=str(package / "__init__.py"),
        Builder=object,
        C2paSignerInfo=object,
        C2paSigningAlg=object,
        Reader=object,
        Signer=object,
    )

    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "c2pa":
            return module
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    monkeypatch.setattr(reporting, "_safe_distribution_version", lambda name: "0.32.3" if name == "c2pa-python" else "not-available")

    result = reporting.check_c2pa_support()

    assert result["status"] == "ok"
    assert result["available"] is True
    assert result["c2pa_python_distribution"] == "0.32.3"


def test_check_c2pa_support_detects_linux_native_runtime(tmp_path, monkeypatch):
    package = tmp_path / "c2pa"
    libs = package / "libs"
    libs.mkdir(parents=True)
    (libs / "libc2pa_c.so").write_bytes(b"so")
    module = types.SimpleNamespace(
        __file__=str(package / "__init__.py"),
        Builder=object,
        C2paSignerInfo=object,
        C2paSigningAlg=object,
        Reader=object,
        Signer=object,
    )

    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "c2pa":
            return module
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    monkeypatch.setattr(reporting, "_safe_distribution_version", lambda name: "0.32.3" if name == "c2pa-python" else "not-available")

    result = reporting.check_c2pa_support()

    assert result["status"] == "ok"
    assert result["native_libraries"] == [str(libs / "libc2pa_c.so")]
