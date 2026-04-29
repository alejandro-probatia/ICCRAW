# Licencias de terceros (resumen operativo)

Este archivo resume licencias de componentes clave y como se integran en ProbRAW.

Fecha de revision: 2026-04-25.

## 1) ProbRAW (repositorio principal)

- Licencia: `AGPL-3.0-or-later`.
- Proyecto liderado por Probatia Forensics SL (https://probatia.com) en
  colaboracion con la Asociacion Espanola de Imagen Cientifica y Forense
  (https://imagencientifica.es).

## 2) ArgyllCMS (`colprof`, `xicclu`, `cctiff`)

- Uso en ProbRAW: herramienta externa por subprocess para generar perfiles ICC,
  validar el ICC real y convertir TIFFs finales a perfiles de salida.
- Licencia declarada por ArgyllCMS: AGPL para el paquete principal.
- Politica en ProbRAW:
  - no se redistribuyen binarios dentro del repositorio,
  - se exige instalacion desde fuente oficial o paquete del sistema,
  - se registran version y contexto en trazabilidad.

## 3) LibRaw / rawpy / rawpy-demosaic

- Uso en ProbRAW: motor unico de revelado RAW mediante el modulo Python
  `rawpy`, vinculado a LibRaw.
- Dependencia base instalable: `rawpy`, vinculada a LibRaw.
- Backend GPL3 para AMaZE: `rawpy-demosaic`, fork GPL3 de `rawpy` que incluye
  los demosaic packs GPL2/GPL3 de LibRaw y exporta el mismo modulo `rawpy`.
- Licencias declaradas:
  - LibRaw: LGPL/CDDL segun upstream.
  - `rawpy`: MIT, sin demosaic packs GPL en wheels estandar.
  - `rawpy-demosaic`: `GPL-3.0-or-later`.
  - LibRaw demosaic pack GPL3: GPL3+, incluye AMaZE.
- Politica en ProbRAW:
  - ProbRAW se mantiene bajo `AGPL-3.0-or-later`, compatible con GPL3+,
  - se registra version de `rawpy`, distribucion instalada (`rawpy` o
    `rawpy-demosaic`), LibRaw y `rawpy.flags` en contexto de ejecucion,
  - AMaZE solo se anuncia como disponible cuando `DEMOSAIC_PACK_GPL3=True`,
  - se incluyen avisos de licencia al publicar builds que redistribuyan wheels.

## 4) PySide6 / Qt (GUI opcional)

- Uso en ProbRAW: interfaz grafica opcional.
- Licencia comunitaria de Qt for Python: LGPLv3/GPLv3 (segun documentacion oficial de Qt).
- Politica en ProbRAW:
  - dependencia opcional (`pip install -e .[gui]`),
  - mantener avisos de licencia al redistribuir builds con GUI.

## 5) c2pa-python (C2PA/CAI para TIFF final firmado)

- Uso en ProbRAW: firma y lectura de manifiestos C2PA embebidos en TIFF final.
- Licencia declarada por `contentauth/c2pa-python`: Apache-2.0 o MIT.
- Politica en ProbRAW:
  - dependencia instalada mediante extra (`pip install -e .[c2pa]`),
  - obligatoria para generar TIFFs finales ProbRAW,
  - no sustituye `batch_manifest.json`, hashes SHA-256 ni auditoria lineal,
  - la clave privada se pasa por ruta de archivo y no se registra en logs,
  - revisar certificados, TSA y politica de confianza antes de uso probatorio.

## 6) Dependencias Python relevantes

- `opencv-python-headless`: BSD-3-Clause (OpenCV).
- `tifffile`: BSD.
- `numpy`: BSD-3-Clause.
- `scipy`: BSD-3-Clause.
- `PyYAML`: MIT.
- `colour-science`: BSD-3-Clause.
- `Pillow`: HPND-like (PIL Software License). ProbRAW usa `ImageCms` solo
  para conversion ICC de monitor en el visor; el pipeline cientifico/export
  sigue usando ArgyllCMS para perfilado, validacion y conversiones ICC finales.
- `rawpy`: MIT; wheels estandar sin demosaic packs GPL.
- `rawpy-demosaic`: GPL-3.0-or-later; habilita demosaic packs GPL2/GPL3.
- `c2pa-python`: Apache-2.0 o MIT; requerido para firmar TIFFs finales.

## 8) Herramientas de empaquetado Windows

- `PyInstaller`: herramienta de build para crear los ejecutables Windows.
- `Inno Setup`: herramienta externa para generar el instalador `.exe`.
- Politica en ProbRAW:
  - se usan como herramientas de construccion,
  - no se versionan binarios generados en el repositorio,
  - revisar licencias y avisos antes de publicar una release redistribuible.

## 9) Regla de distribucion del proyecto

Antes de publicar release/binarios/contenedor:

1. incluir `LICENSE` (AGPL) del proyecto,
2. incluir este archivo o equivalente actualizado,
3. incluir instrucciones para obtener codigo fuente correspondiente,
4. verificar licencias de binarios de sistema empaquetados (si se empaquetan),
5. si se distribuye AMaZE, incluir avisos GPL3 de `rawpy-demosaic`, LibRaw y
   demosaic packs, junto con el codigo fuente correspondiente o URL publica.

## 10) Contributor Covenant 2.1 (codigo de conducta)

- Uso en ProbRAW: textos `CODE_OF_CONDUCT.md` y `CODE_OF_CONDUCT.es.md`.
- Fuente: `https://www.contributor-covenant.org/version/2/1/code_of_conduct/`.
- Licencia declarada por el proyecto Contributor Covenant: CC-BY-4.0.
- Politica en ProbRAW:
  - se conserva la atribucion al texto original,
  - solo se sustituye el metodo de contacto por el del mantenedor del proyecto.
