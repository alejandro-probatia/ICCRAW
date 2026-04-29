# Instalacion en macOS

ProbRAW debe distribuirse preferentemente mediante instalador cuando exista
artefacto macOS validado. Mientras no haya instalador macOS publicado, la ruta
soportada para pruebas es instalacion desde codigo con dependencias externas del
sistema.

## Dependencias del sistema

Con Homebrew:

```bash
brew install python argyll-cms exiftool
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
python3 -m venv .venv
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
