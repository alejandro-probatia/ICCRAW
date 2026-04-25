# Paquete Debian beta

La beta `0.1` se distribuye como paquete Debian binario:

- version de aplicacion Python: `0.1.0b3`,
- version Debian: `0.1.0~beta3`,
- arquitectura generada: la de la maquina de build (`dpkg --print-architecture`).

El paquete instala:

- entorno Python autocontenido en `/opt/iccraw/venv`,
- dependencia Python `rawpy`/LibRaw dentro del entorno de la aplicacion; para
  builds con AMaZE debe sustituirse por `rawpy-demosaic` o por una wheel GPL3
  propia,
- lanzador CLI `/usr/bin/iccraw`,
- lanzador GUI `/usr/bin/iccraw-ui`,
- entrada de escritorio en `/usr/share/applications/iccraw.desktop`,
- documentacion basica en `/usr/share/doc/iccraw/`.

Dependencias de sistema declaradas:

- `python3`,
- `argyll`,
- `liblcms2-utils`,
- `exiftool`,
- librerias minimas de Qt/OpenGL/XCB para la GUI.

## Construccion

Desde la raiz del repositorio:

```bash
bash packaging/debian/build_deb.sh
```

El artefacto queda en:

```text
dist/iccraw_0.1.0~beta3_amd64.deb
```

El nombre exacto puede variar si se construye en otra arquitectura.

## Instalacion local

```bash
sudo apt install ./dist/iccraw_0.1.0~beta3_amd64.deb
iccraw --version
iccraw check-tools --strict
iccraw-ui
```

## Verificacion recomendada

Antes de publicar o entregar una beta:

```bash
.venv/bin/python -m pytest
bash scripts/check_tools.sh
bash packaging/debian/build_deb.sh
dpkg-deb --info dist/iccraw_0.1.0~beta3_amd64.deb
```

Para una prueba de instalacion aislada, usar una maquina Debian/Ubuntu limpia y
ejecutar `iccraw check-tools --strict` tras instalar el `.deb`.

Para validar soporte AMaZE en la beta instalada:

```bash
/opt/iccraw/venv/bin/python /usr/share/doc/iccraw/check_amaze_support.py
```

Si el instalador redistribuye AMaZE, aplicar tambien `docs/AMAZE_GPL3.md` y
actualizar los avisos de licencia del paquete.
