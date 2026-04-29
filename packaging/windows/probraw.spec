# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
    copy_metadata,
)


root = Path(SPECPATH).resolve().parents[1]
icon_path = root / "src" / "probraw" / "resources" / "icons" / "probraw-icon.ico"
datas = collect_data_files("probraw.resources")
for dist_name in ("rawpy-demosaic", "rawpy"):
    try:
        datas += copy_metadata(dist_name)
    except Exception:
        pass
hiddenimports = collect_submodules("probraw")
hiddenimports += collect_submodules("c2pa")
rawpy_binaries = collect_dynamic_libs("rawpy")
c2pa_binaries = collect_dynamic_libs("c2pa")
datas += collect_data_files("c2pa")

a_cli = Analysis(
    [str(root / "packaging" / "windows" / "launcher_cli.py")],
    pathex=[str(root)],
    binaries=rawpy_binaries + c2pa_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
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
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_path),
)

a_gui = Analysis(
    [str(root / "packaging" / "windows" / "launcher_gui.py")],
    pathex=[str(root)],
    binaries=rawpy_binaries + c2pa_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
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
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_path),
)

coll = COLLECT(
    cli,
    gui,
    a_cli.binaries,
    a_cli.zipfiles,
    a_cli.datas,
    a_gui.binaries,
    a_gui.zipfiles,
    a_gui.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ProbRAW",
)
