# Licencias de terceros (resumen operativo)

Este archivo resume licencias de componentes clave y como se integran en ICCRAW.

Fecha de revision: 2026-04-23.

## 1) ICCRAW (repositorio principal)

- Licencia: `AGPL-3.0-or-later`.
- Codigo mantenido por la comunidad de la Asociacion Espanola de Imagen Cientifica y Forense.

## 2) ArgyllCMS (`colprof`)

- Uso en ICCRAW: herramienta externa por subprocess para generar perfiles ICC.
- Licencia declarada por ArgyllCMS: AGPL para el paquete principal.
- Politica en ICCRAW:
  - no se redistribuyen binarios dentro del repositorio,
  - se exige instalacion desde fuente oficial o paquete del sistema,
  - se registran version y contexto en trazabilidad.

## 3) LibRaw / rawpy

- Uso en ICCRAW: motor único de revelado RAW mediante dependencia Python
  `rawpy`, vinculada a LibRaw.
- Licencia declarada: dual LGPL-2.1/CDDL (segun LibRaw/rawpy).
- Politica en ICCRAW:
  - se registra version de `rawpy` y LibRaw en contexto de ejecucion,
  - se incluyen avisos de licencia al publicar builds que redistribuyan wheels.

## 4) PySide6 / Qt (GUI opcional)

- Uso en ICCRAW: interfaz grafica opcional.
- Licencia comunitaria de Qt for Python: LGPLv3/GPLv3 (segun documentacion oficial de Qt).
- Politica en ICCRAW:
  - dependencia opcional (`pip install -e .[gui]`),
  - mantener avisos de licencia al redistribuir builds con GUI.

## 5) LittleCMS (`tificc`)

- Uso en ICCRAW: CMM externo para convertir TIFFs desde perfil ICC de entrada a
  perfil de salida, actualmente sRGB.
- Licencia: MIT-like open source segun proyecto LittleCMS.
- Politica en ICCRAW:
  - se invoca como herramienta externa,
  - no se redistribuyen binarios dentro del repositorio,
  - se comprueba con `scripts/check_tools.sh`.

## 6) Dependencias Python relevantes

- `opencv-python-headless`: BSD-3-Clause (OpenCV).
- `tifffile`: BSD.
- `numpy`: BSD-3-Clause.
- `scipy`: BSD-3-Clause.
- `PyYAML`: MIT.
- `colour-science`: BSD-3-Clause.
- `Pillow`: HPND-like (PIL Software License).
- `rawpy`: licencia dual LGPL-2.1/CDDL (segun LibRaw/rawpy).

## 7) Herramientas de empaquetado Windows

- `PyInstaller`: herramienta de build para crear los ejecutables Windows.
- `Inno Setup`: herramienta externa para generar el instalador `.exe`.
- Politica en ICCRAW:
  - se usan como herramientas de construccion,
  - no se versionan binarios generados en el repositorio,
  - revisar licencias y avisos antes de publicar una beta redistribuible.

## 8) Regla de distribucion del proyecto

Antes de publicar release/binarios/contenedor:

1. incluir `LICENSE` (AGPL) del proyecto,
2. incluir este archivo o equivalente actualizado,
3. incluir instrucciones para obtener codigo fuente correspondiente,
4. verificar licencias de binarios de sistema empaquetados (si se empaquetan).
