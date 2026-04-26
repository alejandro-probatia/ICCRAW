from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


def _load_install_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "install_amaze_backend.py"
    spec = importlib.util.spec_from_file_location("install_amaze_backend", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_install_amaze_backend_dry_run_uses_pypi(capsys):
    module = _load_install_module()

    status = module.main(["--python", sys.executable, "--pypi", "--dry-run"])

    assert status == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "dry_run"
    assert payload["source"] == "rawpy-demosaic"
    assert payload["commands"][0][-2:] == ["rawpy", "rawpy-demosaic"]
    assert payload["commands"][1][-1] == "rawpy-demosaic"
    assert payload["commands"][2][-1].endswith("check_amaze_support.py")


def test_install_amaze_backend_dry_run_uses_wheel(tmp_path: Path, capsys):
    module = _load_install_module()
    wheel = tmp_path / "rawpy_demosaic-0.0-py3-none-any.whl"

    status = module.main(["--python", sys.executable, "--wheel", str(wheel), "--dry-run"])

    assert status == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["source"].endswith("rawpy_demosaic-0.0-py3-none-any.whl")
    assert payload["commands"][1][-1].endswith("rawpy_demosaic-0.0-py3-none-any.whl")


def test_install_amaze_backend_requires_source(capsys):
    module = _load_install_module()

    status = module.main(["--python", sys.executable, "--dry-run"])

    assert status == 2
    assert "indica --wheel PATH o --pypi" in capsys.readouterr().err
