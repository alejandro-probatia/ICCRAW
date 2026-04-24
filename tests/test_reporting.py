import subprocess

from iccraw import reporting


def test_check_external_tools_reports_available_required_tools(monkeypatch):
    available = {"colprof", "xicclu", "tificc", "exiftool"}

    def fake_which(command):
        if command in available:
            return f"/usr/bin/{command}"
        return None

    def fake_run(command, **_kwargs):
        return subprocess.CompletedProcess(command, 0, stdout=f"{command[0]} 1.2.3\n")

    monkeypatch.setattr(reporting.shutil, "which", fake_which)
    monkeypatch.setattr(reporting.subprocess, "run", fake_run)

    result = reporting.check_external_tools()

    assert result["status"] == "ok"
    assert result["missing_required"] == []
    assert result["failing_required"] == []
    assert all(tool["available"] for tool in result["tools"])
    assert all(tool["ok"] for tool in result["tools"])


def test_check_external_tools_uses_icclu_fallback(monkeypatch):
    available = {"colprof", "icclu", "tificc", "exiftool"}

    def fake_which(command):
        if command in available:
            return f"/usr/bin/{command}"
        return None

    def fake_run(command, **_kwargs):
        return subprocess.CompletedProcess(command, 0, stdout=f"{command[0]} fallback\n")

    monkeypatch.setattr(reporting.shutil, "which", fake_which)
    monkeypatch.setattr(reporting.subprocess, "run", fake_run)

    result = reporting.check_external_tools()
    xicclu = next(tool for tool in result["tools"] if tool["name"] == "argyll-xicclu")

    assert result["status"] == "ok"
    assert xicclu["selected_command"] == "icclu"
    assert xicclu["path"] == "/usr/bin/icclu"


def test_check_external_tools_reports_missing_required(monkeypatch):
    monkeypatch.setattr(reporting.shutil, "which", lambda _command: None)

    result = reporting.check_external_tools()

    assert result["status"] == "missing_required"
    assert "argyll-colprof" in result["failing_required"]
    assert all(not tool["available"] for tool in result["tools"])
    assert all(not tool["ok"] for tool in result["tools"])
