_Spanish version: [MACOS_INSTALL.es.md](MACOS_INSTALL.es.md)_

# Installation and Build on macOS

ProbRAW can run from source on macOS and can also be packaged locally as
`ProbRAW.app` with PyInstaller. The build script is designed to reduce manual
steps; Developer ID signing and notarization remain external publication steps.

## System Dependencies

With Homebrew:

```bash
brew install python@3.12 argyll-cms exiftool
```

If using MacPorts or another manual installation, the required executables must
be available as `colprof`, `xicclu` or `icclu`, `cctiff` and `exiftool`.

ProbRAW searches for tools in `PATH` and also in common macOS paths when the GUI
is launched outside a terminal:

- `/opt/homebrew/bin`
- `/opt/homebrew/opt/argyll-cms/bin`
- `/usr/local/bin`
- `/usr/local/opt/argyll-cms/bin`
- `/opt/local/bin`

An explicit path can also be set with `PROBRAW_TOOL_DIR`.

## Python Installation

From the root of the repository:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[gui]"
```

Testing:

```bash
bash scripts/check_tools.sh
probraw check-tools --strict
probraw-ui
```

## Local `.app` Build

Run the reproducible macOS build from a Mac:

```bash
bash packaging/macos/build_app.sh
```

Default outputs:

- `dist/macos/ProbRAW.app`
- `dist/macos/probraw/probraw`
- `dist/macos/ProbRAW-<version>-macos-<arch>.zip`
- `dist/macos/ProbRAW-<version>-macos-<arch>.zip.sha256`

Quick validation:

```bash
dist/macos/probraw/probraw --version
dist/macos/probraw/probraw check-tools --strict
open dist/macos/ProbRAW.app
```

Release build with external tools and AMaZE required:

```bash
PROBRAW_REQUIRE_AMAZE=1 \
PROBRAW_MACOS_STRICT_TOOLS=1 \
bash packaging/macos/build_app.sh
```

Useful variables:

- `PROBRAW_MACOS_PYTHON=/path/python`: use a specific Python or venv.
- `PROBRAW_MACOS_SKIP_TESTS=1`: skip pytest for local iterations.
- `PROBRAW_MACOS_SKIP_TOOL_CHECK=1`: skip the Argyll/ExifTool check.
- `PROBRAW_RAWPY_DEMOSAIC_WHEEL=/path/rawpy_demosaic-*.whl`: install a custom
  AMaZE wheel before packaging.
- `PROBRAW_RAWPY_DEMOSAIC_SOURCE=git+https://...`: install AMaZE from source.
- `PROBRAW_MACOS_CODESIGN_IDENTITY="Developer ID Application: ..."`: sign the
  generated `.app` after the build. Use `-` for local ad-hoc signing.
- `PROBRAW_MACOS_CREATE_ZIP=0`: leave only the `.app` folder and packaged CLI.

## AMaZE

AMaZE requires `rawpy-demosaic` or a build of `rawpy`/LibRaw with the demosaic
GPL3 pack. If there is a compatible wheel for the Python version used:

```bash
python scripts/install_amaze_backend.py --pypi
probraw check-amaze
```

With your own wheel:

```bash
python scripts/install_amaze_backend.py --wheel /ruta/rawpy_demosaic-*.whl
probraw check-amaze
```

The build is considered valid for AMaZE only if `probraw check-amaze` reports
`amaze_supported: true`.

Practical note: use Python 3.11 or 3.12. On Apple Silicon, use native arm64
Python. On Intel Macs or x86_64 Rosetta environments, a binary wheel for
`rawpy>=0.26` may be unavailable and `pip` may try to compile `rawpy` from
source.
