import subprocess
import types

from nexoraw import reporting


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

    result = reporting.check_external_tools()
    xicclu = next(tool for tool in result["tools"] if tool["name"] == "argyll-xicclu")

    assert result["status"] == "ok"
    assert xicclu["selected_command"] == "icclu"
    assert xicclu["path"] == "/usr/bin/icclu"


def test_check_external_tools_reports_missing_required(monkeypatch):
    monkeypatch.setattr(reporting, "external_tool_path", lambda _command: None)

    result = reporting.check_external_tools()

    assert result["status"] == "missing_required"
    assert "argyll-colprof" in result["failing_required"]
    assert all(not tool["available"] for tool in result["tools"])
    assert all(not tool["ok"] for tool in result["tools"])


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
