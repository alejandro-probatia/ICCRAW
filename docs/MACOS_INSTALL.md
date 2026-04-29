_Spanish version: [MACOS_INSTALL.es.md](MACOS_INSTALL.es.md)_

# Installation on macOS

ProbRAW should preferably be distributed through an installer when it exists
validated macOS artifact. As long as there is no macOS installer published, the path
supported for testing is installation from code with external dependencies of the
system.

## System dependencies

With Homebrew:
```bash
brew install python argyll-cms exiftool
```
If using MacPorts or other manual installation, the required executables must
be available as `colprof`, `xicclu` or `icclu`, `cctiff` and `exiftool`.

ProbRAW searches for tools in `PATH` and, also, in common macOS paths
when the GUI is launched outside of a terminal:

- `/opt/homebrew/bin`
- `/opt/homebrew/opt/argyll-cms/bin`
- `/usr/local/bin`
- `/usr/local/opt/argyll-cms/bin`
- `/opt/local/bin`

An explicit route can also be set with `PROBRAW_TOOL_DIR`.

## Python installation

From the root of the repository:
```bash
python3 -m venv .venv
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