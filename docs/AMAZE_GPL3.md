_Spanish version: [AMAZE_GPL3.es.md](AMAZE_GPL3.es.md)_

# Support AMaZE and GPL demosaic packs

## License decision

ProbRAW is distributed under `AGPL-3.0-or-later`. This license is compatible with
the GPL3+ condition required by the LibRaw GPL3 demosaic pack, which includes the
AMaZE algorithm.

The AMaZE integration must maintain these rules:

1. retain `LICENSE` and the project's copyright notices,
2. retain notices/licenses of `rawpy-demosaic`, LibRaw and the demosaic packs,
3. distribute the corresponding source code together with the binary or through a
   Equivalent public URL,
4. document in each release which build of `rawpy`/LibRaw has been used,
5. do not present AMaZE as available if `rawpy.flags["DEMOSAIC_PACK_GPL3"]`
   It is not `True`.

## Recommended backend

The preferred path is to use `rawpy-demosaic`, a GPL3 fork of `rawpy` that
includes the GPL2/GPL3 LibRaw packages and exports the same Python module
`rawpy`.

Installation when there is a compatible wheel published in the configured index
from `pip`:
```bash
python scripts/install_amaze_backend.py --pypi
python scripts/check_amaze_support.py
```
Building a Linux wheel from pinned Git source:
```bash
python scripts/build_rawpy_demosaic_wheel.py \
  --python .venv/bin/python \
  --work-dir tmp/rawpy-demosaic-build \
  --output-dir tmp/wheels \
  --force
.venv/bin/python scripts/install_amaze_backend.py --wheel tmp/wheels/rawpy_demosaic-*.whl
.venv/bin/python scripts/check_amaze_support.py
```
With your own wheel:
```bash
python scripts/install_amaze_backend.py --wheel /ruta/rawpy_demosaic-*.whl
python scripts/check_amaze_support.py
```
The command should report:
```json
{
  "amaze_supported": true
}
```
## Windows

If PyPI does not offer wheel compatible with the version of Python used for the
Windows installer, you have to build your own wheel for `rawpy-demosaic` or
`rawpy` linked with LibRaw compiled with:
```text
LIBRAW_DEMOSAIC_PACK_GPL2
LIBRAW_DEMOSAIC_PACK_GPL3
```
The resulting wheel and ProbRAW installer must include license notices
GPL3/AGPL and a clear way to obtain the corresponding source code.

ProbRAW includes a manual GitHub Actions workflow to build the wheel
`rawpy-demosaic` Windows with MSVC:
```text
Build rawpy-demosaic Windows wheel
```
The workflow uses by default the commit legacy `8b17075` of
`rawpy-demosaic`, which links LibRaw 0.18.7 with the GPL2/GPL3 demosaic packs.
This point is deliberate: the recent `rawpy` standard wheels do not include
`DEMOSAIC_PACK_GPL3=True`, and the modern build of `rawpy-demosaic` does not expose
AMaZE as a GPL3 pack on Windows in this flow. Releases that redistribute
AMaZE must preserve the exact commit, submodules and SHA256 hash of the
wheel.

Once the wheel is downloaded:
```powershell
$wheel = (Get-ChildItem -Recurse .\tmp\wheels -Filter "rawpy_demosaic-*.whl" | Select-Object -First 1).FullName
.\scripts\install_amaze_backend.ps1 -Wheel $wheel
.\.venv\Scripts\python.exe -m probraw check-amaze
```
To package Windows with AMaZE:
```powershell
.\packaging\windows\build_installer.ps1 -RawpyDemosaicWheel $wheel -RequireAmaze
```
If a compatible wheel exists in PyPI, the installer can resolve it during installation.
build:
```powershell
.\packaging\windows\build_installer.ps1 -Amaze -RequireAmaze
```
## Debian/Ubuntu

Package `.deb` installs and verifies the AMaZE backend during build
by default. From the root of the repository:
```bash
PROBRAW_BUILD_AMAZE=1 PROBRAW_REQUIRE_AMAZE=1 bash packaging/debian/build_deb.sh
```
The default Git source used to build the embedded wheel is:
```text
git+https://github.com/exfab/rawpy-demosaic.git@8b17075
```
It can be replaced by another font plotted with `PROBRAW_RAWPY_DEMOSAIC_SOURCE`
if that source is installable directly by `pip`, or by a wheel already
built with `PROBRAW_RAWPY_DEMOSAIC_WHEEL`.

With a local wheel:
```bash
PROBRAW_REQUIRE_AMAZE=1 \
PROBRAW_RAWPY_DEMOSAIC_WHEEL=/ruta/rawpy_demosaic-*.whl \
bash packaging/debian/build_deb.sh
```
The build registers `check-amaze.json` and `build-metadata.json` in
`/usr/share/doc/probraw/third_party/rawpy-demosaic/`. The validation prior to
release fails if `check-amaze.json` does not contain `amaze_supported: true`.

## macOS

The supported path on macOS is installation from code. The installer
AMaZE cross-platform backend is the same Python script:
```bash
python scripts/install_amaze_backend.py --pypi
probraw check-amaze
```
If there is no compatible wheel for the Python version/architecture used, create
or download your own wheel:
```bash
python scripts/install_amaze_backend.py --wheel /ruta/rawpy_demosaic-*.whl
probraw check-amaze
```
`rawpy-demosaic` exports the Python module `rawpy`, but its Python distribution
It is called `rawpy-demosaic`. That is why `pip` can warn that it is not installed
the distribution `rawpy>=0.26` although the runtime import `import rawpy`
works with AMaZE. The mandatory check to publish a build is
`probraw check-amaze`.

## Operational check

ProbRAW does not infer AMaZE support due to the presence of the enum
`rawpy.DemosaicAlgorithm.AMAZE`; that constant can exist even if the pack does not
is compiled. The valid check is:
```python
import rawpy
assert rawpy.flags["DEMOSAIC_PACK_GPL3"] is True
```
If the check fails, the GUI downgrades AMaZE recipes to `dcb` to avoid
crashes during interactive calibration. The CLI and backend fail with a
explicit error to preserve reproducibility.