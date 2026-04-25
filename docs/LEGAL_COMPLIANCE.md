# Cumplimiento Legal y Licencias

## Alcance

Este documento define el marco de cumplimiento legal de NexoRAW para uso
cientifico y forense.

## Licencia del proyecto

- NexoRAW se distribuye bajo `AGPL-3.0-or-later`.
- Toda redistribucion (codigo fuente o binarios) debe preservar:
  - aviso de copyright,
  - licencia AGPL,
  - acceso a la fuente correspondiente.
- Si el software se ofrece como servicio de red, debe mantenerse el acceso a la
  fuente correspondiente para usuarios remotos (AGPL).
- El proyecto tiene objetivo cientifico/comunitario sin finalidad comercial,
  pero la AGPL no impone una prohibicion general de uso comercial por terceros.

## AMaZE y demosaic packs GPL

NexoRAW puede usar AMaZE si el modulo `rawpy` instalado esta vinculado a LibRaw
con `LIBRAW_DEMOSAIC_PACK_GPL3` habilitado. Este caso exige GPL3+ para el
producto resultante; `AGPL-3.0-or-later` cumple ese requisito.

Politica:

1. mantener NexoRAW bajo `AGPL-3.0-or-later`,
2. preferir `rawpy-demosaic` para builds con AMaZE cuando exista wheel
   compatible o se construya una wheel propia,
3. no anunciar AMaZE como disponible salvo que
   `rawpy.flags["DEMOSAIC_PACK_GPL3"]` sea `True`,
4. incluir avisos GPL3/AGPL y fuente correspondiente en cualquier instalador o
   contenedor que redistribuya AMaZE,
5. documentar el backend exacto en `run_context` y reportes de release.

## Herramientas externas del flujo

NexoRAW combina dependencias Python y herramientas externas:

- `rawpy`/LibRaw o `rawpy-demosaic`/LibRaw para revelado RAW.
- `ArgyllCMS` (`colprof`) para construccion de perfiles ICC.
- `LittleCMS` (`tificc`) para conversiones ICC de salida.
- `exiftool` para metadatos.
- `PySide6` (Qt for Python, opcional) para GUI.

Notas de licencia relevantes:

1. ArgyllCMS publica su paquete principal bajo AGPL (segun documentacion oficial del proyecto).
2. LibRaw declara licencias LGPL/CDDL para el nucleo; sus demosaic packs GPL
   imponen GPL2+ o GPL3+ segun el pack usado.
3. `rawpy` estandar es MIT y no incluye los packs GPL en sus wheels.
4. `rawpy-demosaic` es `GPL-3.0-or-later` e incluye los packs GPL2/GPL3.
5. LittleCMS se distribuye como software open source permisivo; NexoRAW lo invoca como herramienta externa.
6. PySide6 comunitario se distribuye bajo LGPLv3/GPLv3; en NexoRAW se usa como dependencia opcional de GUI.

Politica de integracion:

1. no se embeben binarios de terceros dentro del repositorio,
2. la instalacion se realiza desde paquetes oficiales del sistema, PyPI o fuentes oficiales,
3. se registran versiones de dependencias en `run_context` para auditoria.

## Reglas de cumplimiento operativo

1. No eliminar ni modificar avisos de licencia de terceros.
2. Mantener este archivo y `LICENSE` sincronizados con la politica vigente.
3. Documentar en `CHANGELOG.md` cualquier cambio de licencia o dependencia critica.
4. Antes de publicar builds o contenedores, verificar que:
   - se adjunta licencia AGPL del proyecto,
   - se documentan dependencias externas,
   - existe mecanismo claro para obtener la fuente correspondiente.
5. Si se distribuye una build que incluya GUI Qt, incluir avisos de licencia de Qt/PySide6 y componentes vinculados.
6. Si se redistribuyen wheels/binarios de `rawpy`, `rawpy-demosaic` o LibRaw,
   incluir sus avisos de licencia.

## Gobernanza comunitaria

El mantenimiento del proyecto recae en la comunidad de la:

- **Asociacion Espanola de Imagen Cientifica y Forense**.

Se recomienda revisiones periodicas de cumplimiento legal y trazabilidad para
entornos de peritaje y cadena de custodia digital.

## Fuentes de referencia (consultadas el 2026-04-25)

- ArgyllCMS Home: https://argyllcms.com/
- ArgyllCMS Licensing/Commercial Use: https://argyllcms.com/commercialuse.html
- Argyll Documentation (copyright/licensing): https://www.argyllcms.com/doc/ArgyllDoc.html
- Qt for Python LGPL overview: https://doc.qt.io/qtforpython-6/overviews/qtdoc-lgpl.html
- LibRaw demosaic packs: https://sources.debian.org/src/libraw/0.16.0-9%2Bdeb8u3/README.demosaic-packs
- LibRaw AMaZE/GPL3 note: https://www.libraw.org/news/libraw-0.12.html
- rawpy: https://github.com/letmaik/rawpy
- rawpy PyPI optional features: https://pypi.org/project/rawpy/
- rawpy-demosaic: https://pypi.org/project/rawpy-demosaic/

Resumen operativo por componente:

- `docs/THIRD_PARTY_LICENSES.md`
- `docs/AMAZE_GPL3.md`
