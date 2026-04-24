# Cumplimiento Legal y Licencias

## Alcance

Este documento define el marco de cumplimiento legal de ICCRAW para uso cientifico y forense.

## Licencia del proyecto

- ICCRAW se distribuye bajo `AGPL-3.0-or-later`.
- Toda redistribucion (codigo fuente o binarios) debe preservar:
  - aviso de copyright,
  - licencia AGPL,
  - acceso a la fuente correspondiente.
- Si el software se ofrece como servicio de red, debe mantenerse el acceso a la fuente correspondiente para usuarios remotos (AGPL).
- El proyecto tiene objetivo cientifico/comunitario sin finalidad comercial, pero la AGPL no impone una prohibicion general de uso comercial por terceros.

## Herramientas externas del flujo

ICCRAW utiliza herramientas externas ejecutadas por subprocess:

- `dcraw` para revelado RAW.
- `ArgyllCMS` (`colprof`) para construccion de perfiles ICC.
- `LittleCMS` (`tificc`) para conversiones ICC de salida.
- `exiftool` para metadatos.
- `PySide6` (Qt for Python, opcional) para GUI.

Notas de licencia relevantes:

1. ArgyllCMS publica su paquete principal bajo AGPL (segun documentacion oficial del proyecto).
2. `dcraw.c` incluye condiciones propias del autor; ICCRAW lo usa como herramienta externa y no redistribuye el codigo/binario dentro de este repositorio.
3. LittleCMS se distribuye como software open source permisivo; ICCRAW lo invoca como herramienta externa.
4. PySide6 comunitario se distribuye bajo LGPLv3/GPLv3; en ICCRAW se usa como dependencia opcional de GUI.

Politica de integracion:

1. no se embeben ni redistribuyen binarios de terceros dentro del repositorio,
2. la instalacion se realiza desde paquetes oficiales del sistema o fuentes oficiales,
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
6. Si se redistribuye `dcraw` junto al producto final fuera de repositorio, revisar expresamente los terminos del codigo `dcraw.c` de la version distribuida.

## Gobernanza comunitaria

El mantenimiento del proyecto recae en la comunidad de la:

- **Asociacion Espanola de Imagen Cientifica y Forense**.

Se recomienda revisiones periodicas de cumplimiento legal y trazabilidad para entornos de peritaje y cadena de custodia digital.

## Fuentes de referencia (consultadas el 2026-04-23)

- ArgyllCMS Home: https://argyllcms.com/
- ArgyllCMS Licensing/Commercial Use: https://argyllcms.com/commercialuse.html
- Argyll Documentation (copyright/licensing): https://www.argyllcms.com/doc/ArgyllDoc.html
- Qt for Python LGPL overview: https://doc.qt.io/qtforpython-6/overviews/qtdoc-lgpl.html
- dcraw homepage: https://www.dechifro.org/dcraw/
- dcraw source header (Debian mirror): https://sources.debian.org/src/dcraw/9.28-2/dcraw.c/

Resumen operativo por componente:

- `docs/THIRD_PARTY_LICENSES.md`
