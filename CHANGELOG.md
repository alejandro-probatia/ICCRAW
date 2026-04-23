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
