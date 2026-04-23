# Changelog

Todos los cambios relevantes de ICCRAW se documentan en este archivo.

Este proyecto sigue:

- formato inspirado en Keep a Changelog,
- versionado SemVer,
- trazabilidad de cambios orientada a uso científico y forense.

## Política de actualización

Para mantener trazabilidad completa, cada cambio debe:

1. añadir una línea en `Unreleased` antes de merge/push,
2. mover entradas a una versión fechada en cada release,
3. referenciar, cuando aplique, impacto en reproducibilidad, legalidad o cadena de custodia.

## [Unreleased]

### Added

- Plantilla de mantenimiento continuo del changelog y política de actualización.
- Módulo `preview` para carga de imagen/RAW en previsualización, ajustes técnicos y análisis lineal.
- GUI nueva basada en Qt/PySide6 (`app-ui`, `app-ui-qt`) con:
  - previsualización técnica con perfil ICC,
  - ajustes de nitidez y reducción de ruido,
  - ejecución de flujo automático carta -> perfil -> lote.
- Dependencia opcional `gui` en `pyproject.toml`.
- Script `scripts/run_ui_qt.sh`.
- Navegador visual de directorios y miniaturas RAW/imagen integrado en GUI para selección de archivos clave.
- Acción GUI para revelar archivo seleccionado a TIFF 16-bit con perfil ICC opcional.
- Ajustes de ruido separados en luminancia y color.
- Menu superior en GUI con accesos a configuracion y operaciones (`Archivo`, `Configuracion`, `Perfil ICC`, `Vista`, `Ayuda`).
- Soporte de exploracion multiunidad en GUI para navegar el arbol completo del sistema de archivos.
- Panel de configuracion RAW ampliado (demosaic, WB, black/white level, tone curve, espacios, sampling, profiling mode).
- Panel de configuracion de perfil ICC ampliado (tipo `-a`, calidad `-q`, args extra `colprof`, formato `.icc/.icm`).
- Optimizacion de carga y previsualizacion RAW/DNG:
  - modo rapido con miniatura embebida o decodificacion `dcraw -h`,
  - downscale configurable de preview para reducir latencia en archivos grandes,
  - cache de previews por archivo+recipe para recargas inmediatas.
- Nueva función de backend `auto_generate_profile_from_charts` para generar perfil ICC sin ejecutar batch.
- Reorganización funcional en 3 pestañas principales:
  - Generación Perfil ICC,
  - Revelado RAW,
  - Monitoreo Flujo.
- Revelado por lotes integrado en pestaña de Revelado RAW (selección o directorio completo).

### Changed

- Se reemplaza completamente la GUI anterior (tkinter) por implementación Qt.
- `apply_profile_matrix` pasa a API pública en `icc_entrada.export` para reutilización en previsualización.
- Documentación y roadmap actualizados para reflejar GUI Qt y política legal AGPL + dependencias.
- Rediseño de GUI a layout de 3 paneles (explorador, visor principal, panel de control) priorizando espacio de imagen y flujo práctico de producción.
- Reorganizacion de GUI para flujo de trabajo tipo revelador RAW (navegacion, seleccion visual y maximo espacio para imagen).
- Renombrada pestaña de ajustes visuales de `Vista` a `Nitidez`.
- El flujo de perfilado y el flujo de revelado por lotes se separan explícitamente para mayor claridad operativa.
- La previsualización aplica perfil ICC desactivado por defecto para evitar dominantes cuando el perfil no corresponde al set cámara+iluminación+recipe activo.
- La ventana Qt guarda/restaura tamaño y distribución de paneles para mejorar trabajo en pantallas de distinto tamaño.

### Docs

- Política legal ampliada para:
  - compatibilidad AGPL con objetivo comunitario no comercial,
  - notas de licencia de ArgyllCMS, dcraw y PySide6,
  - obligaciones de redistribución y trazabilidad.
- Nuevo documento `docs/THIRD_PARTY_LICENSES.md` con inventario operativo de licencias de terceros.
- Advertencia explícita en README y manual: el estado actual es de desarrollo y la aplicación aún no se considera plenamente funcional/validada para producción científica o forense.

### Fixed

- Corrección de previsualización RAW rápida:
  - salida de `dcraw` para preview en espacio sRGB (`-o 1`) en lugar de cámara nativa sin conversión,
  - normalización de miniatura embebida a lineal para evitar doble corrección gamma.
- Salvaguarda en preview con perfil ICC:
  - si falta sidecar `.profile.json` o se detecta clipping/dominante extrema, la vista cae a modo sin perfil con aviso en log.

## [0.1.0] - 2026-04-23

### Added

- Estructura inicial del proyecto modular (`core`, `src`, `cli`, `docs`, `tests`).
- CLI funcional para flujo técnico: `raw-info`, `develop`, `detect-chart`, `sample-chart`, `build-profile`, `validate-profile`, `batch-develop`.
- GUI ligera en `tkinter` para operar el flujo completo sin línea de comandos.
- Flujo automático extremo a extremo (`auto-profile-batch`) para carta -> perfil ICC -> lote TIFF 16-bit.
- Script de verificación de herramientas externas: `scripts/check_tools.sh`.
- Manual de usuario en español.
- Documento técnico de integración `dcraw + ArgyllCMS`.
- Documento de cumplimiento legal y política de licencias.

### Changed

- Interfaz gráfica traducida completamente al español.
- Motor de revelado RAW fijado a `dcraw` como backend único soportado.
- Motor de perfil ICC fijado a ArgyllCMS (`colprof`) como backend único soportado.
- Metadatos de licencia del proyecto actualizados a `AGPL-3.0-or-later`.
- Gobernanza declarada para mantenimiento comunitario por la Asociación Española de Imagen Científica y Forense.

### Fixed

- Formato `.ti3` para `colprof` ajustado (`DEVICE_CLASS`/`COLOR_REP` y orden de campos) para compatibilidad real con ArgyllCMS.
- Detección y registro de versión `dcraw` en contexto de ejecución mejorada.

### Docs

- Arquitectura, roadmap, decisiones y manual alineados con:
  - pipeline estricto `dcraw + ArgyllCMS`,
  - requisitos de reproducibilidad,
  - cumplimiento legal AGPL para distribución y uso en red.
