_Spanish version: [DEBIAN_PACKAGE.es.md](DEBIAN_PACKAGE.es.md)_

# Debian package

The current release can be built as a binary Debian package:

- Python application version: read from `src/probraw/version.py`,
- Debian version: derived from the application version,
- generated architecture: that of the build machine (`dpkg --print-architecture`).

The package installs:

- self-contained Python environment in `/opt/probraw/venv`,
- Qt GUI, CLI, ProbRAW Proof and C2PA support within the application environment,
- Python `rawpy`/LibRaw dependency within the application environment; in
  builds with AMaZE, `build_deb.sh` automatically replaces that backend with
  `rawpy-demosaic` and check `DEMOSAIC_PACK_GPL3=True`,
- CLI launcher `/usr/bin/probraw`,
- GUI launcher `/usr/bin/probraw-ui`,
- desktop entry in `/usr/share/applications/probraw.desktop`,
- hicolor SVG/PNG icons for integration with the system menu,
- fallback `/usr/share/pixmaps/probraw.png` for menus that do not resolve the
  hicolor theme,
- user documentation, methodology, release and licenses in
  `/usr/share/doc/probraw/`.

Declared system dependencies:

- `python3`,
- `argyll`,
- `exiftool`,
- `colord` to detect the monitor ICC profile configured on the system,
- minimal Qt/OpenGL/XCB libraries for the GUI,
- native embedded LibRaw AMaZE runtime (`libgomp1`, `liblcms2-2`,
  `libjpeg-turbo8`, `libstdc++6`),
- `desktop-file-utils` and `hicolor-icon-theme` to register launcher and icon.

Package `probraw` declares `Replaces/Conflicts: iccraw` for removal
correctly old beta installations released with the name `iccraw`.
The Linux installer does not create launchers or internal scripts named
old

## Construction

From the root of the repository:
```bash
bash packaging/debian/build_deb.sh
```
The Debian build installs and enforces AMaZE by default using a pinned Git source
by `rawpy-demosaic`. If that check fails, the package should not be published.

Explicit build with AMaZE from the default Git source:
```bash
PROBRAW_BUILD_AMAZE=1 PROBRAW_REQUIRE_AMAZE=1 bash packaging/debian/build_deb.sh
```
Build with AMaZE from another source installable by `pip` and traced:
```bash
PROBRAW_BUILD_AMAZE=1 \
PROBRAW_REQUIRE_AMAZE=1 \
PROBRAW_RAWPY_DEMOSAIC_SOURCE="git+https://github.com/exfab/rawpy-demosaic.git@8b17075" \
bash packaging/debian/build_deb.sh
```
Build with AMaZE from a traced wheel:
```bash
PROBRAW_REQUIRE_AMAZE=1 \
PROBRAW_RAWPY_DEMOSAIC_WHEEL=/ruta/rawpy_demosaic-*.whl \
bash packaging/debian/build_deb.sh
```
The artifact is in:
```text
dist/probraw_<version>_amd64.deb
```
The exact name may vary if built on another architecture.

## Local installation
```bash
sudo apt install ./dist/probraw_<version>_amd64.deb
probraw --version
probraw check-tools --strict
probraw check-c2pa
probraw check-display-profile
probraw-ui
```
## Recommended verification

Before publishing or delivering a release, this verification is mandatory:
```bash
.venv/bin/python -m pytest
bash scripts/check_tools.sh
bash packaging/debian/build_deb.sh
packaging/debian/validate_deb.sh dist/probraw_<version>_amd64.deb
sudo apt install ./dist/probraw_<version>_amd64.deb
scripts/validate_linux_install.sh
```
For an isolated installation test, use a clean Debian/Ubuntu machine.
Do not upload `.deb` to GitHub Releases or the repository if any of them fail.
these points:

- `Package: probraw`, `Replaces: iccraw` and `Conflicts: iccraw`,
- absence of `/usr/bin/iccraw`, `/usr/bin/iccraw-ui` and internal scripts
  `/opt/probraw/venv/bin/iccraw*`,
- desktop input `Name=ProbRAW`, `Exec=probraw-ui`, `Icon=probraw` and
  category `Graphics;Photography;`,
- real hicolor `probraw.png` icons `16/32/48/64/128/256/512`, SVG icon
  and fallback `/usr/share/pixmaps/probraw.png`,
- user manual and methodology included in `/usr/share/doc/probraw/`,
- `probraw check-tools --strict`,
- `probraw check-c2pa`,
- `probraw check-display-profile`,
- `probraw check-amaze`.

To validate AMaZE support in the installed release:
```bash
/opt/probraw/venv/bin/python /usr/share/doc/probraw/check_amaze_support.py
```
If the installer redistributes AMaZE, the build writes metadata to
`/usr/share/doc/probraw/third_party/rawpy-demosaic/`. Apply too
`docs/AMAZE_GPL3.md` and update the package license notices when
use your own wheel.