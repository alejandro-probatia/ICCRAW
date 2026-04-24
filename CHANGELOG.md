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

### Changed

- `batch-develop` separa gestion ICC en modos explicitos:
  - RGB de camara con perfil ICC de entrada incrustado,
  - conversion a sRGB mediante LittleCMS (`tificc`) con perfil sRGB incrustado.
- `validate-profile` valida el perfil ICC real con ArgyllCMS (`xicclu`/`icclu`)
  en lugar de calcular DeltaE con la matriz lateral del sidecar.
- La deteccion de carta por fallback queda marcada como modo `fallback`, con
  confianza baja y bloqueo por defecto en flujos automaticos.
- El muestreo de carta aplica `sampling_trim_percent` y
  `sampling_reject_saturated` desde la receta.
- Las referencias de carta cargadas desde JSON se validan en modo estricto
  (fuente, D50, observador 2 grados, ids únicos y Lab completo).
- Nuevo comando `export-cgats` para exportar muestras a CGATS/CTI3 interoperable.
- La matriz `matrix_camera_to_xyz` queda como artefacto diagnostico/compatibilidad,
  no como sustituto de la conversion ICC en exportacion de lote ni de la
  validacion del perfil.
- Las recetas de ejemplo pasan de `demosaic_algorithm: rcd` a `ahd`, el modo
  soportado por `dcraw`.
- La GUI deja de ofrecer algoritmos de demosaicing que el backend `dcraw` no
  puede ejecutar.
- Reorganización estructural del proyecto para crecer como base Python única:
  - eliminada la capa Rust (`Cargo.toml`, `Cargo.lock`, `core/`, `cli/` Rust, `tests/` Rust) que ya no se usaba,
  - paquete renombrado `icc_entrada` → `iccraw` alineado con el nombre del repo y del proyecto,
  - código organizado en subpaquetes por dominio: `core/`, `raw/`, `chart/`, `profile/`,
  - `__version__` centralizado en `iccraw/version.py` y expuesto por `__init__.py`,
  - entry points CLI/GUI renombrados a `iccraw` y `iccraw-ui`,
  - `python -m iccraw` operativo vía `__main__.py`,
  - tests unificados en `tests/` (antes `tests_py/`) con imports actualizados,
  - docs duplicadas eliminadas de la raíz (canónicas en `docs/`), rutas absolutas Linux sustituidas por relativas en README.

### Added

- Validacion estricta de `demosaic_algorithm` para backend `dcraw`; una receta
  con algoritmo no soportado falla antes de procesar.
- Integracion de LittleCMS (`tificc`) como CMM externo para conversion ICC a
  sRGB.
- Metadatos de modo de gestion de color en manifiestos de lote.
- Tests P0 para demosaicing no soportado, `audit_linear_tiff` realmente lineal y
  exportacion ICC/CMM.
- Tests P0 que demuestran que `validate-profile` usa el ICC real aunque exista
  un sidecar con matriz incorrecta.
- Tests P1 para deteccion fallback de baja confianza y muestreo controlado por
  parametros de receta.
- Tests P1 para rechazo de referencias de carta incompletas/incompatibles.
- Tests P1 para exportacion CGATS/CTI3 de muestras.
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
- Nuevo módulo `session` para gestión persistente de sesiones con creación de estructura de directorios:
  - `charts/`, `raw/`, `profiles/`, `exports/`, `config/`, `work/`.
- Nueva pestaña `1. Sesión` para crear/abrir/guardar sesión con metadatos de iluminación y toma.
- Nueva pestaña `3. Cola de Revelado` con cola de archivos, estado por imagen y ejecución de lote desde cola.
- Persistencia de estado por sesión en `config/session.json`:
  - rutas operativas,
  - configuración de revelado/perfil,
  - perfil activo,
  - cola de revelado.
- Test unitario `tests_py/test_session.py` para estructura, carga y normalización de sesión.

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
- Reorganización de pestañas principales para flujo centrado en sesión:
  - `Sesión`,
  - `Revelado y Perfil ICC`,
  - `Cola de Revelado`.
- La GUI de trabajo se reorganiza en dos fases operativas:
  - `1. Calibrar sesión`: capturas de carta -> perfil de revelado + ICC,
  - `2. Aplicar sesión`: RAW/TIFF objetivo -> TIFF con receta calibrada + ICC.
- El ajuste manual visible queda limitado a nitidez; exposición, densidad,
  balance de blancos y base colorimétrica proceden de la carta.
- El procesamiento por lote en GUI ahora tolera errores por archivo y devuelve resumen `OK/errores` sin abortar todo el lote.
- `auto_generate_profile_from_charts` acepta una lista explícita de capturas de
  carta para que la GUI pueda usar una selección de miniaturas en vez de todo
  un directorio.

### Docs

- Nuevo documento `docs/OPERATIVE_REVIEW_PLAN.md` con hallazgos tecnicos,
  criterios de aceptacion y plan profesional por fases para convertir el
  prototipo en pipeline operativo y auditable.
- `ROADMAP.md`, `ISSUES.md`, `COLOR_PIPELINE.md` y `README.md` enlazados al
  plan operativo y actualizados con prioridades P0-P3.
- Política legal ampliada para:
  - compatibilidad AGPL con objetivo comunitario no comercial,
  - notas de licencia de ArgyllCMS, dcraw y PySide6,
  - obligaciones de redistribución y trazabilidad.
- Nuevo documento `docs/THIRD_PARTY_LICENSES.md` con inventario operativo de licencias de terceros.
- Advertencia explícita en README y manual: el estado actual es de desarrollo y la aplicación aún no se considera plenamente funcional/validada para producción científica o forense.

### Fixed

- `audit_linear_tiff` se escribe antes de compensacion de exposicion y curvas de
  salida, conservando el estado lineal desarrollado.
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
