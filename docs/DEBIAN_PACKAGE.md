# Paquete Debian beta

La beta `0.1` se distribuye como paquete Debian binario:

- version de aplicacion Python: `0.1.0b4`,
- version Debian: `0.1.0~beta4`,
- arquitectura generada: la de la maquina de build (`dpkg --print-architecture`).

El paquete instala:

- entorno Python autocontenido en `/opt/nexoraw/venv`,
- dependencia Python `rawpy`/LibRaw dentro del entorno de la aplicacion; para
  builds con AMaZE debe sustituirse por `rawpy-demosaic` o por una wheel GPL3
  propia,
- lanzador CLI `/usr/bin/nexoraw`,
- lanzador GUI `/usr/bin/nexoraw-ui`,
- entrada de escritorio en `/usr/share/applications/nexoraw.desktop`,
- documentacion basica en `/usr/share/doc/nexoraw/`.

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
dist/nexoraw_0.1.0~beta4_amd64.deb
```

El nombre exacto puede variar si se construye en otra arquitectura.

## Instalacion local

```bash
sudo apt install ./dist/nexoraw_0.1.0~beta4_amd64.deb
nexoraw --version
nexoraw check-tools --strict
nexoraw-ui
```

## Verificacion recomendada

Antes de publicar o entregar una beta:

```bash
.venv/bin/python -m pytest
bash scripts/check_tools.sh
bash packaging/debian/build_deb.sh
dpkg-deb --info dist/nexoraw_0.1.0~beta4_amd64.deb
```

Para una prueba de instalacion aislada, usar una maquina Debian/Ubuntu limpia y
ejecutar `nexoraw check-tools --strict` tras instalar el `.deb`.

Para validar soporte AMaZE en la beta instalada:

```bash
/opt/nexoraw/venv/bin/python /usr/share/doc/nexoraw/check_amaze_support.py
```

Si el instalador redistribuye AMaZE, aplicar tambien `docs/AMAZE_GPL3.md` y
actualizar los avisos de licencia del paquete.
