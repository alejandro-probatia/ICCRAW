# Prioritized Issues

Este backlog resume el plan de implementacion. La justificacion tecnica y los
criterios de aceptacion completos estan en:

- [Revision operativa y plan de profesionalizacion](OPERATIVE_REVIEW_PLAN.md)

## P0

1. [x] Validar recetas de forma estricta y eliminar mapeos silenciosos de algoritmos
   RAW no soportados por el backend activo.
2. [x] Corregir `audit_linear_tiff` para que se escriba antes de curvas tonales,
   conversiones o renderizado de salida.
3. [x] Separar en `batch-develop` los modos:
   - asignar perfil ICC de entrada a RGB camara,
   - convertir con CMM real a un perfil de salida.
4. [x] Integrar un CMM real para conversiones ICC y dejar la matriz lateral como
   diagnostico, no como salida principal.
5. [x] Validar el perfil ICC real generado por ArgyllCMS, no solo la matriz del
   sidecar `.profile.json`.
6. [ ] Añadir dataset RAW/DNG real con licencia clara y checksums para tests de
   integracion.
7. [ ] Garantizar ArgyllCMS (`colprof`) y herramientas externas en CI para tests
   de integracion reales.

## P1

1. [x] Hacer que el fallback de deteccion de carta sea bloqueante por defecto o tenga
   confianza baja.
2. [x] Añadir modo manual asistido para marcar esquinas de carta en CLI y GUI.
3. [x] Aplicar parametros completos de muestreo desde receta (`trim_percent`,
   `reject_saturated`, margen de parche, criterios de exclusion).
4. [x] Validar iluminante, observador, fuente y version de la referencia de carta.
5. [ ] Implementar validacion cruzada con capturas no usadas para construir perfil.
6. [x] Mejorar deteccion automatica de ColorChecker24 en condiciones no ideales.
7. [ ] Completar soporte IT8 (deteccion + referencia + validacion).
8. [x] Añadir export CGATS completo para interoperabilidad externa.
9. [x] Añadir referencia ColorChecker 2005 D50 no sintetica para flujo operativo.
10. [ ] Integrar detecciones manuales guardadas por captura en `auto-profile-batch`.

## P2

1. Validar determinismo del pipeline en ejecuciones repetidas.
2. Benchmark de rendimiento y paralelizacion de lote.
3. Paquetizacion reproducible (wheel + contenedor).
4. Guia de contribucion cientifica (captura, iluminacion, QA colorimetrico).
5. Tests automaticos de smoke para GUI Qt en CI (modo headless).
6. Automatizar auditoria de licencias y avisos para releases AGPL.

## P3

1. Integrar manifiestos C2PA/CAI firmados para cadena de custodia del proceso.
2. Perfilado avanzado LUT ademas de matriz 3x3.
3. Comparador automatico entre perfiles de sesiones/iluminantes distintos.
4. Internacionalizacion GUI (es/en) y presets tecnicos por disciplina.
