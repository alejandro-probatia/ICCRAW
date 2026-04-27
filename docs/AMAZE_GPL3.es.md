# Soporte AMaZE y demosaic packs GPL

## Decisión de licencia

NexoRAW se distribuye bajo `AGPL-3.0-or-later`. Esta licencia es compatible con
la condición GPL3+ exigida por el demosaic pack GPL3 de LibRaw, que incluye el
algoritmo AMaZE.

La integración de AMaZE debe mantener estas reglas:

1. conservar `LICENSE` y los avisos de copyright del proyecto,
2. conservar avisos/licencias de `rawpy-demosaic`, LibRaw y los demosaic packs,
3. distribuir el código fuente correspondiente junto al binario o mediante una
   URL pública equivalente,
4. documentar en cada release qué build de `rawpy`/LibRaw se ha usado,
5. no presentar AMaZE como disponible si `rawpy.flags["DEMOSAIC_PACK_GPL3"]`
   no es `True`.

## Backend recomendado

El camino preferente es usar `rawpy-demosaic`, un fork GPL3 de `rawpy` que
incluye los packs GPL2/GPL3 de LibRaw y exporta el mismo módulo Python
`rawpy`.

Instalación cuando exista wheel compatible publicada en el indice configurado
de `pip`:

```bash
python scripts/install_amaze_backend.py --pypi
python scripts/check_amaze_support.py
```

Construccion de una wheel Linux desde fuente Git fijada:

```bash
python scripts/build_rawpy_demosaic_wheel.py \
  --python .venv/bin/python \
  --work-dir tmp/rawpy-demosaic-build \
  --output-dir tmp/wheels \
  --force
.venv/bin/python scripts/install_amaze_backend.py --wheel tmp/wheels/rawpy_demosaic-*.whl
.venv/bin/python scripts/check_amaze_support.py
```

Con una wheel propia:

```bash
python scripts/install_amaze_backend.py --wheel /ruta/rawpy_demosaic-*.whl
python scripts/check_amaze_support.py
```

El comando debe informar:

```json
{
  "amaze_supported": true
}
```

## Windows

Si PyPI no ofrece wheel compatible con la versión de Python usada para el
instalador Windows, hay que construir una wheel propia de `rawpy-demosaic` o de
`rawpy` enlazada con LibRaw compilado con:

```text
LIBRAW_DEMOSAIC_PACK_GPL2
LIBRAW_DEMOSAIC_PACK_GPL3
```

La wheel resultante y el instalador de NexoRAW deben incluir avisos de licencia
GPL3/AGPL y una forma clara de obtener el código fuente correspondiente.

NexoRAW incluye un workflow manual de GitHub Actions para construir la wheel
Windows de `rawpy-demosaic` con MSVC:

```text
Build rawpy-demosaic Windows wheel
```

El workflow usa por defecto el commit legacy `8b17075` de
`rawpy-demosaic`, que enlaza LibRaw 0.18.7 con los demosaic packs GPL2/GPL3.
Este punto es deliberado: los wheels estandar recientes de `rawpy` no incluyen
`DEMOSAIC_PACK_GPL3=True`, y la build moderna de `rawpy-demosaic` no expone
AMaZE como pack GPL3 en Windows en este flujo. Las releases que redistribuyan
AMaZE deben conservar el commit exacto, los submodulos y el hash SHA256 de la
wheel.

Una vez descargada la wheel:

```powershell
$wheel = (Get-ChildItem -Recurse .\tmp\wheels -Filter "rawpy_demosaic-*.whl" | Select-Object -First 1).FullName
.\scripts\install_amaze_backend.ps1 -Wheel $wheel
.\.venv\Scripts\python.exe -m nexoraw check-amaze
```

Para empaquetar Windows con AMaZE:

```powershell
.\packaging\windows\build_installer.ps1 -RawpyDemosaicWheel $wheel -RequireAmaze
```

Si existe wheel compatible en PyPI, el instalador puede resolverla durante la
build:

```powershell
.\packaging\windows\build_installer.ps1 -Amaze -RequireAmaze
```

## Debian/Ubuntu

El paquete `.deb` instala y verifica el backend AMaZE durante la construccion
por defecto. Desde la raiz del repositorio:

```bash
NEXORAW_BUILD_AMAZE=1 NEXORAW_REQUIRE_AMAZE=1 bash packaging/debian/build_deb.sh
```

La fuente Git por defecto usada para construir la wheel embebida es:

```text
git+https://github.com/exfab/rawpy-demosaic.git@8b17075
```

Se puede sustituir por otra fuente trazada con `NEXORAW_RAWPY_DEMOSAIC_SOURCE`
si esa fuente es instalable directamente por `pip`, o por una wheel ya
construida con `NEXORAW_RAWPY_DEMOSAIC_WHEEL`.

Con una wheel local:

```bash
NEXORAW_REQUIRE_AMAZE=1 \
NEXORAW_RAWPY_DEMOSAIC_WHEEL=/ruta/rawpy_demosaic-*.whl \
bash packaging/debian/build_deb.sh
```

La build registra `check-amaze.json` y `build-metadata.json` en
`/usr/share/doc/nexoraw/third_party/rawpy-demosaic/`. La validacion previa a
release falla si `check-amaze.json` no contiene `amaze_supported: true`.

## macOS

La ruta soportada en macOS es la instalacion desde codigo. El instalador
multiplataforma de backend AMaZE es el mismo script Python:

```bash
python scripts/install_amaze_backend.py --pypi
nexoraw check-amaze
```

Si no hay wheel compatible para la version de Python/arquitectura usada, crear
o descargar una wheel propia:

```bash
python scripts/install_amaze_backend.py --wheel /ruta/rawpy_demosaic-*.whl
nexoraw check-amaze
```

`rawpy-demosaic` exporta el modulo Python `rawpy`, pero su distribucion Python
se llama `rawpy-demosaic`. Por eso `pip` puede avisar de que no esta instalada
la distribucion `rawpy>=0.26` aunque la importacion runtime `import rawpy`
funcione con AMaZE. La comprobacion obligatoria para publicar una build es
`nexoraw check-amaze`.

## Comprobación operativa

NexoRAW no infiere soporte AMaZE por la presencia del enum
`rawpy.DemosaicAlgorithm.AMAZE`; esa constante puede existir aunque el pack no
esté compilado. La comprobación válida es:

```python
import rawpy
assert rawpy.flags["DEMOSAIC_PACK_GPL3"] is True
```

Si la comprobación falla, la GUI degrada las recetas AMaZE a `dcb` para evitar
bloqueos durante la calibración interactiva. La CLI y el backend fallan con un
error explícito para preservar reproducibilidad.
