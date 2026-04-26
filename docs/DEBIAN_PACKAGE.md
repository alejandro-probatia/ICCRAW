# Paquete Debian beta

La beta `0.1` se distribuye como paquete Debian binario:

- version de aplicacion Python: `0.1.0b5`,
- version Debian: `0.1.0~beta5`,
- arquitectura generada: la de la maquina de build (`dpkg --print-architecture`).

El paquete instala:

- entorno Python autocontenido en `/opt/nexoraw/venv`,
- GUI Qt, CLI, NexoRAW Proof y soporte C2PA dentro del entorno de aplicacion,
- dependencia Python `rawpy`/LibRaw dentro del entorno de la aplicacion; en
  builds con AMaZE, `build_deb.sh` sustituye automaticamente ese backend por
  `rawpy-demosaic` y verifica `DEMOSAIC_PACK_GPL3=True`,
- lanzador CLI `/usr/bin/nexoraw`,
- lanzador GUI `/usr/bin/nexoraw-ui`,
- entrada de escritorio en `/usr/share/applications/nexoraw.desktop`,
- iconos hicolor SVG/PNG para integracion con el menu del sistema,
- fallback `/usr/share/pixmaps/nexoraw.png` para menus que no resuelvan el
  tema hicolor,
- documentacion basica en `/usr/share/doc/nexoraw/`.

Dependencias de sistema declaradas:

- `python3`,
- `argyll`,
- `exiftool`,
- librerias minimas de Qt/OpenGL/XCB para la GUI,
- runtime nativo de LibRaw AMaZE embebido (`libgomp1`, `liblcms2-2`,
  `libjpeg-turbo8`, `libstdc++6`),
- `desktop-file-utils` y `hicolor-icon-theme` para registrar lanzador e icono.

El paquete `nexoraw` declara `Replaces/Conflicts: iccraw` para retirar
correctamente instalaciones beta antiguas publicadas con el nombre `iccraw`.
El instalador Linux no crea lanzadores ni scripts internos con el nombre
antiguo.

## Construccion

Desde la raiz del repositorio:

```bash
bash packaging/debian/build_deb.sh
```

La build Debian instala y exige AMaZE por defecto usando una fuente Git fijada
de `rawpy-demosaic`. Si esa comprobacion falla, el paquete no debe publicarse.

Build explicita con AMaZE desde la fuente Git fijada por defecto:

```bash
NEXORAW_BUILD_AMAZE=1 NEXORAW_REQUIRE_AMAZE=1 bash packaging/debian/build_deb.sh
```

Build con AMaZE desde otra fuente instalable por `pip` y trazada:

```bash
NEXORAW_BUILD_AMAZE=1 \
NEXORAW_REQUIRE_AMAZE=1 \
NEXORAW_RAWPY_DEMOSAIC_SOURCE="git+https://github.com/exfab/rawpy-demosaic.git@8b17075" \
bash packaging/debian/build_deb.sh
```

Build con AMaZE desde una wheel trazada:

```bash
NEXORAW_REQUIRE_AMAZE=1 \
NEXORAW_RAWPY_DEMOSAIC_WHEEL=/ruta/rawpy_demosaic-*.whl \
bash packaging/debian/build_deb.sh
```

El artefacto queda en:

```text
dist/nexoraw_0.1.0~beta5_amd64.deb
```

El nombre exacto puede variar si se construye en otra arquitectura.

## Instalacion local

```bash
sudo apt install ./dist/nexoraw_0.1.0~beta5_amd64.deb
nexoraw --version
nexoraw check-tools --strict
nexoraw check-c2pa
nexoraw-ui
```

## Verificacion recomendada

Antes de publicar o entregar una beta, esta verificacion es obligatoria:

```bash
.venv/bin/python -m pytest
bash scripts/check_tools.sh
bash packaging/debian/build_deb.sh
packaging/debian/validate_deb.sh dist/nexoraw_0.1.0~beta5_amd64.deb
sudo apt install ./dist/nexoraw_0.1.0~beta5_amd64.deb
scripts/validate_linux_install.sh
```

Para una prueba de instalacion aislada, usar una maquina Debian/Ubuntu limpia.
No subir el `.deb` a GitHub Releases ni al repositorio si falla cualquiera de
estos puntos:

- `Package: nexoraw`, `Replaces: iccraw` y `Conflicts: iccraw`,
- ausencia de `/usr/bin/iccraw`, `/usr/bin/iccraw-ui` y scripts internos
  `/opt/nexoraw/venv/bin/iccraw*`,
- entrada de escritorio `Name=NexoRAW`, `Exec=nexoraw-ui`, `Icon=nexoraw` y
  categoria `Graphics;Photography;`,
- iconos `nexoraw.png` reales en hicolor `16/32/48/64/128/256/512`, icono SVG
  y fallback `/usr/share/pixmaps/nexoraw.png`,
- `nexoraw check-tools --strict`,
- `nexoraw check-c2pa`,
- `nexoraw check-amaze`.

Para validar soporte AMaZE en la beta instalada:

```bash
/opt/nexoraw/venv/bin/python /usr/share/doc/nexoraw/check_amaze_support.py
```

Si el instalador redistribuye AMaZE, la build escribe metadatos en
`/usr/share/doc/nexoraw/third_party/rawpy-demosaic/`. Aplicar tambien
`docs/AMAZE_GPL3.md` y actualizar los avisos de licencia del paquete cuando se
use una wheel propia.
