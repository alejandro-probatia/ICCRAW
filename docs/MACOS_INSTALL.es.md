# Instalacion y build en macOS

ProbRAW puede ejecutarse desde codigo en macOS y tambien puede empaquetarse como
`ProbRAW.app` local mediante PyInstaller. El script de build esta pensado para
reducir pasos manuales; la firma Developer ID y la notarizacion siguen siendo un
paso externo de publicacion.

## Dependencias del sistema

Con Homebrew:

```bash
brew install python@3.12 argyll-cms exiftool
```

Si se usa MacPorts u otra instalacion manual, los ejecutables requeridos deben
estar disponibles como `colprof`, `xicclu` o `icclu`, `cctiff` y `exiftool`.

ProbRAW busca herramientas en el `PATH` y, ademas, en rutas habituales de macOS
cuando la GUI se lanza fuera de una terminal:

- `/opt/homebrew/bin`
- `/opt/homebrew/opt/argyll-cms/bin`
- `/usr/local/bin`
- `/usr/local/opt/argyll-cms/bin`
- `/opt/local/bin`

Tambien puede fijarse una ruta explicita con `PROBRAW_TOOL_DIR`.

## Instalacion Python

Desde la raiz del repositorio:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[gui]"
```

Comprobacion:

```bash
bash scripts/check_tools.sh
probraw check-tools --strict
probraw-ui
```

## Build local `.app`

El build reproducible para macOS se ejecuta desde un Mac:

```bash
bash packaging/macos/build_app.sh
```

Salidas por defecto:

- `dist/macos/ProbRAW.app`
- `dist/macos/probraw/probraw`
- `dist/macos/ProbRAW-<version>-macos-<arch>.zip`
- `dist/macos/ProbRAW-<version>-macos-<arch>.zip.sha256`

Validacion rapida:

```bash
dist/macos/probraw/probraw --version
dist/macos/probraw/probraw check-tools --strict
open dist/macos/ProbRAW.app
```

Build de release con herramientas externas y AMaZE obligatorios:

```bash
PROBRAW_REQUIRE_AMAZE=1 \
PROBRAW_MACOS_STRICT_TOOLS=1 \
bash packaging/macos/build_app.sh
```

Variables utiles:

- `PROBRAW_MACOS_PYTHON=/ruta/python`: usa un Python/venv concreto.
- `PROBRAW_MACOS_SKIP_TESTS=1`: omite pytest para iteraciones locales.
- `PROBRAW_MACOS_SKIP_TOOL_CHECK=1`: omite la comprobacion de Argyll/ExifTool.
- `PROBRAW_RAWPY_DEMOSAIC_WHEEL=/ruta/rawpy_demosaic-*.whl`: instala una wheel
  AMaZE propia antes de empaquetar.
- `PROBRAW_RAWPY_DEMOSAIC_SOURCE=git+https://...`: instala AMaZE desde fuente.
- `PROBRAW_MACOS_CODESIGN_IDENTITY="Developer ID Application: ..."`: firma el
  `.app` generado despues del build. Usa `-` para firma ad-hoc local.
- `PROBRAW_MACOS_CREATE_ZIP=0`: deja solo la carpeta `.app` y la CLI empaquetada.

## AMaZE

AMaZE requiere `rawpy-demosaic` o una build de `rawpy`/LibRaw con el demosaic
pack GPL3. Si existe wheel compatible para la version de Python usada:

```bash
python scripts/install_amaze_backend.py --pypi
probraw check-amaze
```

Con una wheel propia:

```bash
python scripts/install_amaze_backend.py --wheel /ruta/rawpy_demosaic-*.whl
probraw check-amaze
```

La build se considera valida para AMaZE solo si `probraw check-amaze` informa
`amaze_supported: true`.

Nota practica: usar Python 3.11 o 3.12. En Apple Silicon conviene usar Python
arm64 nativo. En Mac Intel o entornos x86_64 bajo Rosetta puede no existir wheel
binaria compatible para `rawpy>=0.26`, y `pip` intentara compilar `rawpy` desde
fuente.
