_Spanish version: [WINDOWS_INSTALLER.es.md](WINDOWS_INSTALLER.es.md)_

# Windows Installer

This document prepares the construction and testing flow to generate
a NexoRAW Windows installer.

## Scope

The Windows installer packages the Python application with PyInstaller and generates a
`.exe` installable with Inno Setup 6.

The installer redistributes the Python application and packages the tools
critical externals under `{app}\tools\...` for the entire pipeline to work
without editing the system `PATH`:

- ArgyllCMS: `colprof`, `xicclu`/`icclu` and `cctiff`.
- ExifTool: `exiftool`.
- `c2pa-python` and its native library `c2pa_c.dll` to read and embed
  C2PA manifests when exporting final TIFFs.

Also copy the user manual, the RAW/ICC methodology, the
AMaZE policy, technical decisions, licenses and release notes.

The diagnosis is verified with:
```powershell
nexoraw check-tools --strict
nexoraw check-c2pa
```
## Preparation of the development environment

From the root of the repository:
```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev,gui,installer,c2pa]"
```
Install Inno Setup 6 to generate the installer:
```powershell
winget install --id JRSoftware.InnoSetup -e
```
## Local tests

Python tests and non-strict diagnosis:
```powershell
.\scripts\run_checks.ps1
```
Testing with mandatory external dependencies:
```powershell
.\scripts\run_checks.ps1 -StrictExternalTools
```
On computers where `cctiff` is missing, the Python suite may pass with a test
jumped, but `-StrictExternalTools` should fail. This failure is intentional to
Avoid publishing a release without a working CMM.

## Build application without installer

Generate `dist\windows\NexoRAW\` with `nexoraw.exe` and `nexoraw-ui.exe`:
```powershell
.\packaging\windows\build_installer.ps1 -NoInstaller
```
## Installer Build

Generate the application and then the installer:
```powershell
.\packaging\windows\build_installer.ps1
```
Expected artifact:
```text
dist\windows\installer\NexoRAW-<version>-Setup.exe
```
For release preparation, execute with strict external tools:
```powershell
.\packaging\windows\build_installer.ps1 -StrictExternalTools
```
The release build requires AMaZE by default. If `check-amaze` does not report
`DEMOSAIC_PACK_GPL3=True`, the script fails before generating the installer.

## Build with AMaZE

AMaZE requires a `rawpy` backend linked to LibRaw with
`DEMOSAIC_PACK_GPL3=True`. The standard `rawpy` wheels do not include it.

If PyPI offers a `rawpy-demosaic` compatible wheel for Python
packaged, the build installs it automatically:
```powershell
.\packaging\windows\build_installer.ps1 -Amaze -RequireAmaze
```
If PyPI does not offer a compatible wheel, use the manual workflow:
```text
Build rawpy-demosaic Windows wheel
```
The downloaded artifact can be installed locally with:
```powershell
$wheel = (Get-ChildItem -Recurse .\tmp\wheels -Filter "rawpy_demosaic-*.whl" | Select-Object -First 1).FullName
.\scripts\install_amaze_backend.ps1 -Wheel $wheel
.\.venv\Scripts\python.exe -m nexoraw check-amaze
```
To publish an installer that fails if AMaZE is not active:
```powershell
.\packaging\windows\build_installer.ps1 `
  -RawpyDemosaicWheel $wheel `
  -RequireAmaze
```
The installer copies build metadata and `rawpy-demosaic` warnings to
`{app}\docs\third_party\rawpy-demosaic\`.
The wheel workflow uses by default the commit legacy `8b17075` of
`rawpy-demosaic`, with LibRaw 0.18.7 and `DEMOSAIC_PACK_GPL3=True`; preserve the
SHA256 hash of the wheel and the metadata included in the installer is part
of release traceability.

## Manual verification recommended

On a clean Windows machine:

1. Install `.exe`.
2. Open `NexoRAW` from the start menu.
3. Run `Diagnostico herramientas` from the shortcut group.
4. Confirm:
   - `nexoraw --version`,
   - `nexoraw check-tools --strict`,
   - `nexoraw check-c2pa`,
   - `nexoraw check-amaze`,
   - `nexoraw-ui` starts,
   - sliders and tone curve respond without blocking the window during play
     drag,
   - a test of `detect-chart`/`sample-chart` with `testdata` works,
   - a `output_space=srgb` conversion is only approved if `cctiff` exists.

Recommended automated GUI benchmark before publishing:
```powershell
$env:QT_QPA_PLATFORM="offscreen"
.\.venv\Scripts\python.exe scripts\benchmark_gui_interaction.py `
  --raw .\ruta\a\captura.NEF `
  --algorithm dcb `
  --full-resolution `
  --out .\tmp\gui_benchmark\release_ui.json
```
## Maintenance Notes

- The PyInstaller specification is in `packaging/windows/nexoraw.spec`.
- The Inno Setup template is in `packaging/windows/nexoraw.iss`.
- The `build_installer.ps1` script installs the extras `dev`, `gui`,
  `installer` and `c2pa` before packaging.
- The installer copies ArgyllCMS (`bin` and `ref`, including `sRGB.icm`) and ExifTool into
  `{app}\tools\...` and the application resolves them from there before
  consult system `PATH`.
- To publish an installer with AMaZE, use `-RequireAmaze`; the build must
  report `rawpy.flags["DEMOSAIC_PACK_GPL3"] == True`.
- If the user does not configure an external C2PA certificate, NexoRAW creates a
  Local and self-issued C2PA identity under `%USERPROFILE%\.nexoraw\c2pa`.
  C2PA readers can mark it as `signingCredential.untrusted`; that is
  expected and means that the signature does not belong to a central CAI list, not that
  The NexoRAW RAW-TIFF link is missing.
- The generated binaries are in `dist\windows\`; the storms in
  `build\windows\`.
