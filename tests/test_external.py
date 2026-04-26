import subprocess

from iccraw.core import external


class FakeStartupInfo:
    def __init__(self) -> None:
        self.dwFlags = 0
        self.wShowWindow = None


def test_run_external_hides_console_on_windows(monkeypatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(external.os, "name", "nt", raising=False)
    monkeypatch.setattr(external.subprocess, "STARTUPINFO", FakeStartupInfo, raising=False)
    monkeypatch.setattr(external.subprocess, "STARTF_USESHOWWINDOW", 4, raising=False)
    monkeypatch.setattr(external.subprocess, "SW_HIDE", 0, raising=False)
    monkeypatch.setattr(external.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    monkeypatch.setattr(external.subprocess, "run", fake_run)

    result = external.run_external(["tool"], creationflags=0x10, text=True)

    assert result.returncode == 0
    assert captured["command"] == ["tool"]
    assert captured["kwargs"]["text"] is True
    assert captured["kwargs"]["creationflags"] & 0x08000000
    assert captured["kwargs"]["creationflags"] & 0x10
    assert isinstance(captured["kwargs"]["startupinfo"], FakeStartupInfo)
    assert captured["kwargs"]["startupinfo"].dwFlags & 4


def test_run_external_leaves_non_windows_kwargs_unchanged(monkeypatch):
    captured = {}

    def fake_run(command, **kwargs):
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(external.os, "name", "posix", raising=False)
    monkeypatch.setattr(external.subprocess, "run", fake_run)

    external.run_external(["tool"], text=True)

    assert captured["kwargs"] == {"text": True}
