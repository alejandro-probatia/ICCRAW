# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
    copy_metadata,
)


root = Path(SPECPATH).resolve().parents[1]
build_root = root / "build" / "macos"
icon_path = build_root / "probraw-icon.icns"
version = os.environ.get("PROBRAW_MACOS_VERSION", "0.0.0")
bundle_identifier = os.environ.get("PROBRAW_MACOS_BUNDLE_IDENTIFIER", "org.aeicf.probraw")
codesign_identity = os.environ.get("PROBRAW_MACOS_PYINSTALLER_CODESIGN_IDENTITY") or None
entitlements_file = os.environ.get("PROBRAW_MACOS_ENTITLEMENTS") or None


def _safe(callable_, *args):
    try:
        return callable_(*args)
    except Exception:
        return []


datas = collect_data_files("probraw.resources")
for dist_name in ("rawpy-demosaic", "rawpy", "imagecodecs", "c2pa-python"):
    datas += _safe(copy_metadata, dist_name)

hiddenimports = collect_submodules("probraw")
hiddenimports += _safe(collect_submodules, "c2pa")
hiddenimports += _safe(collect_submodules, "imagecodecs")

binaries = []
binaries += _safe(collect_dynamic_libs, "rawpy")
binaries += _safe(collect_dynamic_libs, "c2pa")
binaries += _safe(collect_dynamic_libs, "imagecodecs")
datas += _safe(collect_data_files, "c2pa")

def _analysis_kwargs():
    return {
        "pathex": [str(root)],
        "binaries": list(binaries),
        "datas": list(datas),
        "hiddenimports": list(hiddenimports),
        "hookspath": [],
        "hooksconfig": {},
        "runtime_hooks": [],
        "excludes": [],
        "noarchive": False,
        "optimize": 0,
    }

a_cli = Analysis(
    [str(root / "packaging" / "macos" / "launcher_cli.py")],
    **_analysis_kwargs(),
)
pyz_cli = PYZ(a_cli.pure)

cli = EXE(
    pyz_cli,
    a_cli.scripts,
    [],
    exclude_binaries=True,
    name="probraw",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=codesign_identity,
    entitlements_file=entitlements_file,
)

cli_coll = COLLECT(
    cli,
    a_cli.binaries,
    a_cli.zipfiles,
    a_cli.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="probraw",
)

a_gui = Analysis(
    [str(root / "packaging" / "macos" / "launcher_gui.py")],
    **_analysis_kwargs(),
)
pyz_gui = PYZ(a_gui.pure)

gui = EXE(
    pyz_gui,
    a_gui.scripts,
    [],
    exclude_binaries=True,
    name="probraw-ui",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=codesign_identity,
    entitlements_file=entitlements_file,
    icon=str(icon_path) if icon_path.exists() else None,
)

gui_coll = COLLECT(
    gui,
    a_gui.binaries,
    a_gui.zipfiles,
    a_gui.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ProbRAW",
)

app = BUNDLE(
    gui_coll,
    name="ProbRAW.app",
    icon=str(icon_path) if icon_path.exists() else None,
    bundle_identifier=bundle_identifier,
    version=version,
    info_plist={
        "CFBundleName": "ProbRAW",
        "CFBundleDisplayName": "ProbRAW",
        "CFBundleShortVersionString": version,
        "CFBundleVersion": version,
        "NSHighResolutionCapable": True,
        "NSPrincipalClass": "NSApplication",
        "LSMinimumSystemVersion": "12.0",
    },
)
