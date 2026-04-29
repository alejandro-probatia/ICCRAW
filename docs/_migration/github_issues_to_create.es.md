# Issues de GitHub a crear (migracion desde `docs/ISSUES.md`)

Este archivo traduce cada entrada P0-P3 a un issue operativo en GitHub.

- Fuente canonica: `docs/ISSUES.md`.
- Criterios de aceptacion: derivados de `docs/OPERATIVE_REVIEW_PLAN.md`.
- Script asociado: `scripts/create_github_issues.sh`.

Formato por issue:

- Titulo sugerido (imperativo y accionable).
- Etiquetas: prioridad + area + tipo.
- Marcado `good-first-issue` cuando aplica.
- Cuerpo sugerido para pegar en GitHub.

## P0

### [P0-01] Validar recetas de forma estricta y eliminar mapeos silenciosos de algoritmos RAW
<!-- labels: P0,raw,bug -->
<!-- good_first_issue: no -->
```issue-body
### Contexto
El contrato RAW debe fallar temprano cuando la receta declara parametros que el backend activo no puede ejecutar fielmente.

### Criterios de aceptacion
- Receta invalida falla antes de procesar.
- Sidecar reporta parametros efectivos de ejecucion.
- Tests cubren recetas validas e invalidas por backend.

### Archivos probablemente afectados
- src/nexoraw/core/recipe.py
- src/nexoraw/raw/pipeline.py
- src/nexoraw/workflow.py
```

### [P0-02] Corregir audit_linear_tiff para garantizar salida lineal previa a curvas y conversiones
<!-- labels: P0,raw,bug -->
<!-- good_first_issue: no -->
```issue-body
### Contexto
El TIFF de auditoria lineal debe representar el estado de revelado lineal antes de cualquier transformacion tonal o conversion de salida.

### Criterios de aceptacion
- Test con `tone_curve: srgb` demuestra que `audit_linear_tiff` no cambia.
- Sidecar diferencia estado lineal y estado renderizado.
- En `profiling_mode` no se aplica curva tonal.

### Archivos probablemente afectados
- src/nexoraw/raw/pipeline.py
- src/nexoraw/workflow.py
- src/nexoraw/core/models.py
```

### [P0-03] Separar en batch-develop los modos de asignar ICC de entrada y convertir con CMM
<!-- labels: P0,profile,enhancement -->
<!-- good_first_issue: no -->
```issue-body
### Contexto
La exportacion de lote debe distinguir entre RGB de camara con ICC de entrada y conversion explicita de salida via CMM.

### Criterios de aceptacion
- TIFF convertido a sRGB declara perfil sRGB.
- TIFF camera RGB conserva perfil ICC de entrada sin conversion doble.
- Manifiesto declara modo de gestion de color utilizado.

### Archivos probablemente afectados
- src/nexoraw/profile/export.py
- src/nexoraw/workflow.py
- src/nexoraw/gui.py
```

### [P0-04] Integrar un CMM real para conversiones ICC y dejar la matriz lateral solo como diagnostico
<!-- labels: P0,profile,enhancement -->
<!-- good_first_issue: no -->
```issue-body
### Contexto
La matriz lateral de diagnostico no debe sustituir transformaciones ICC reales en salidas operativas.

### Criterios de aceptacion
- Conversiones se ejecutan con ArgyllCMS (`cctiff`/`xicclu`) u otro CMM documentado.
- Matriz 3x3 queda en sidecar como diagnostico.
- No hay conversion de salida basada solo en matriz lateral.

### Archivos probablemente afectados
- src/nexoraw/profile/export.py
- src/nexoraw/profile/builder.py
- src/nexoraw/core/external.py
```

### [P0-05] Validar el perfil ICC real generado por ArgyllCMS en lugar de solo la matriz del sidecar
<!-- labels: P0,profile,enhancement -->
<!-- good_first_issue: no -->
```issue-body
### Contexto
La validacion colorimetrica debe evaluar el ICC real para evitar metricas optimistas basadas en aproximaciones laterales.

### Criterios de aceptacion
- `validate-profile` falla si falta ICC aunque exista `.profile.json`.
- Reporte incluye media, mediana, p95, maximo y outliers.
- Se distingue fit/training de validacion independiente.

### Archivos probablemente afectados
- src/nexoraw/profile/builder.py
- src/nexoraw/workflow.py
- src/nexoraw/cli.py
```

### [P0-06] Anadir dataset RAW-DNG real con licencia clara y checksums para integracion
<!-- labels: P0,raw,task -->
<!-- good_first_issue: no -->
```issue-body
### Contexto
Los placeholders actuales en `testdata/raw` no cubren regresion real de revelado RAW y reducen validez de CI.

### Criterios de aceptacion
- Existe dataset minimo real con licencia explicita.
- Se publican SHA-256 y procedencia por archivo.
- Al menos un test de integracion usa RAW/DNG real.

### Archivos probablemente afectados
- testdata/raw/
- tests/test_pipeline_libraw.py
- docs/THIRD_PARTY_LICENSES.md
```

### [P0-07] Garantizar ArgyllCMS y herramientas externas en CI para pruebas de integracion reales
<!-- labels: P0,ci,task -->
<!-- good_first_issue: no -->
```issue-body
### Contexto
Sin ArgyllCMS y ExifTool en CI no se valida el pipeline operativo completo.

### Criterios de aceptacion
- Job de CI instala y verifica `colprof`, `cctiff`, `xicclu`, `exiftool`.
- Se ejecuta test de integracion condicionado por herramientas externas.
- Falla de herramientas deja diagnostico claro en logs de CI.

### Archivos probablemente afectados
- .github/workflows/
- scripts/check_tools.sh
- src/nexoraw/reporting.py
```

## P1

### [P1-01] Hacer bloqueante por defecto el fallback de deteccion de carta
<!-- labels: P1,chart,bug -->
<!-- good_first_issue: no -->
```issue-body
### Contexto
Un fallback demasiado permisivo puede perfilar regiones incorrectas con apariencia de validez.

### Criterios de aceptacion
- Fallback no supera `min_confidence` por defecto.
- `auto-profile-batch` rechaza fallback sin opt-in explicito.
- Reporte indica `detection_mode` y warnings bloqueantes.

### Archivos probablemente afectados
- src/nexoraw/chart/detection.py
- src/nexoraw/workflow.py
- src/nexoraw/cli.py
```

### [P1-02] Anadir modo manual asistido para marcar esquinas de carta en CLI y GUI
<!-- labels: P1,chart,enhancement -->
<!-- good_first_issue: no -->
```issue-body
### Contexto
En capturas con contorno ambiguo se requiere marcado manual reproducible para evitar falsos positivos.

### Criterios de aceptacion
- CLI acepta esquinas manuales y guarda `detection.json` revisable.
- GUI permite marcado de cuatro puntos con overlay.
- Deteccion manual queda trazada en artefactos de sesion.

### Archivos probablemente afectados
- src/nexoraw/chart/detection.py
- src/nexoraw/cli.py
- src/nexoraw/gui.py
```

### [P1-03] Aplicar parametros completos de muestreo desde receta en lugar de valores fijos
<!-- labels: P1,chart,bug -->
<!-- good_first_issue: no -->
```issue-body
### Contexto
El muestreo debe obedecer la receta declarada para preservar reproducibilidad.

### Criterios de aceptacion
- Cambiar `trim_percent` modifica resultados de muestreo.
- Se aplican `reject_saturated` y criterios de exclusion configurados.
- Sidecar registra parametros efectivos por parche.

### Archivos probablemente afectados
- src/nexoraw/core/recipe.py
- src/nexoraw/chart/sampling.py
- src/nexoraw/workflow.py
```

### [P1-04] Validar iluminante, observador, fuente y version de referencia de carta en modo estricto
<!-- labels: P1,chart,enhancement -->
<!-- good_first_issue: no -->
```issue-body
### Contexto
Referencias insuficientemente tipadas generan DeltaE no comparables entre sesiones.

### Criterios de aceptacion
- Referencia sin iluminante/observador falla en modo estricto.
- Reporte incluye fuente y version de referencia usada.
- Tests cubren referencia compatible e incompatible.

### Archivos probablemente afectados
- src/nexoraw/chart/sampling.py
- src/nexoraw/profile/builder.py
- src/nexoraw/workflow.py
```

### [P1-05] Implementar validacion cruzada con capturas de holdout independientes
<!-- labels: P1,profile,enhancement -->
<!-- good_first_issue: no -->
```issue-body
### Contexto
Sin holdout independiente no se puede estimar generalizacion del perfil por sesion.

### Criterios de aceptacion
- Se separan muestras de entrenamiento y validacion.
- Reporte QA muestra metricas de ambos conjuntos.
- Estado final del perfil depende de umbrales sobre validacion.

### Archivos probablemente afectados
- src/nexoraw/workflow.py
- src/nexoraw/profile/builder.py
- src/nexoraw/cli.py
```

### [P1-06] Mejorar deteccion automatica de ColorChecker24 en condiciones no ideales
<!-- labels: P1,chart,enhancement -->
<!-- good_first_issue: no -->
```issue-body
### Contexto
Las condiciones reales de captura requieren robustez frente a contornos ambiguos, ruido y perspectiva.

### Criterios de aceptacion
- Dos capturas reales de referencia detectan carta con confianza alta.
- Se reducen falsos positivos en escenas complejas.
- Overlay incluye diagnostico de calidad de deteccion.

### Archivos probablemente afectados
- src/nexoraw/chart/detection.py
- src/nexoraw/workflow.py
- tests/test_detection_sampling.py
```

### [P1-07] Completar soporte IT8 (deteccion, referencia y validacion)
<!-- labels: P1,chart,enhancement -->
<!-- good_first_issue: no -->
```issue-body
### Contexto
El soporte IT8 ampliaria cobertura metrologica para laboratorios y patrimonio.

### Criterios de aceptacion
- `detect-chart` soporta `--chart-type it8` con geometria valida.
- Catalogo de referencia IT8 incluye metadatos obligatorios.
- QA y validacion reportan metricas para IT8.

### Archivos probablemente afectados
- src/nexoraw/chart/detection.py
- src/nexoraw/chart/sampling.py
- src/nexoraw/resources/references/
```

### [P1-08] Anadir export CGATS completo para interoperabilidad externa
<!-- labels: P1,profile,enhancement -->
<!-- good_first_issue: no -->
```issue-body
### Contexto
Export CGATS facilita auditoria y comparacion con herramientas externas de perfilado.

### Criterios de aceptacion
- Export incluye campos minimos esperados por herramientas externas.
- Se conserva trazabilidad de referencia e iluminante.
- Test de smoke valida formato generado.

### Archivos probablemente afectados
- src/nexoraw/profile/export.py
- src/nexoraw/cli.py
- tests/test_export.py
```

### [P1-09] Anadir referencia ColorChecker 2005 D50 no sintetica para flujo operativo
<!-- labels: P1,chart,task -->
<!-- good_first_issue: no -->
```issue-body
### Contexto
Una referencia operativa no sintetica mejora comparabilidad de resultados en campo.

### Criterios de aceptacion
- Referencia D50 queda versionada con fuente y licencia.
- CLI/GUI la usan por defecto en flujo operativo.
- Documentacion indica alcance y limites de referencia.

### Archivos probablemente afectados
- src/nexoraw/resources/references/
- testdata/references/
- docs/METODOLOGIA_COLOR_RAW.md
```

### [P1-10] Anadir perfil de revelado cientifico previo al perfil ICC
<!-- labels: P1,profile,enhancement -->
<!-- good_first_issue: no -->
```issue-body
### Contexto
El ICC no debe absorber errores de neutralidad y densidad que deben corregirse antes.

### Criterios de aceptacion
- Se genera `development_profile` separado del ICC.
- Receta calibrada actualiza WB y EV con limites de altas luces.
- Trazabilidad registra recipe base y recipe calibrada.

### Archivos probablemente afectados
- src/nexoraw/profile/development.py
- src/nexoraw/workflow.py
- src/nexoraw/cli.py
```

### [P1-11] Ejecutar auto-profile-batch en doble pasada receta base -> receta calibrada -> ICC
<!-- labels: P1,profile,enhancement -->
<!-- good_first_issue: no -->
```issue-body
### Contexto
La doble pasada desacopla correccion de revelado y perfilado ICC de sesion.

### Criterios de aceptacion
- Primera pasada construye perfil de revelado y receta calibrada.
- Segunda pasada usa receta calibrada y geometria reutilizada.
- Resultado final incluye ambos artefactos en manifiesto.

### Archivos probablemente afectados
- src/nexoraw/workflow.py
- src/nexoraw/profile/development.py
- src/nexoraw/cli.py
```

### [P1-12] Reorganizar la GUI como flujo por archivo con mochila por RAW y copia-pegado de ajustes
<!-- labels: P1,gui,enhancement -->
<!-- good_first_issue: no -->
```issue-body
### Contexto
La GUI debe reflejar un flujo operativo por archivo y sesion, no solo acciones aisladas.

### Criterios de aceptacion
- Se distinguen perfil avanzado con carta y perfil basico manual.
- Ajustes se guardan por RAW en sidecar de sesion.
- Copia/pegado de ajustes funciona entre miniaturas seleccionadas.

### Archivos probablemente afectados
- src/nexoraw/gui.py
- src/nexoraw/sidecar.py
- src/nexoraw/session.py
```

### [P1-13] Integrar detecciones manuales guardadas por captura dentro de auto-profile-batch
<!-- labels: P1,chart,enhancement -->
<!-- good_first_issue: no -->
```issue-body
### Contexto
Las detecciones manuales deben ser reutilizables para evitar repetir marcado y reducir error operacional.

### Criterios de aceptacion
- `auto-profile-batch` consume detecciones manuales guardadas.
- Se traza si una captura uso deteccion manual o automatica.
- Flujo GUI y CLI comparten mismo formato de deteccion persistida.

### Archivos probablemente afectados
- src/nexoraw/workflow.py
- src/nexoraw/gui.py
- src/nexoraw/chart/detection.py
```

### [P1-14] Anadir QA de nitidez-MTF y contraste local con criterio medible
<!-- labels: P1,profile,enhancement -->
<!-- good_first_issue: no -->
```issue-body
### Contexto
La calidad de captura requiere metricas objetivas mas alla del ajuste visual subjetivo.

### Criterios de aceptacion
- QA reporta metrica de nitidez/MTF repetible.
- QA reporta indicador de contraste local.
- Reporte separa advertencias de calidad de color y calidad espacial.

### Archivos probablemente afectados
- src/nexoraw/workflow.py
- src/nexoraw/reporting.py
- src/nexoraw/gui.py
```

## P2

### [P2-01] Validar determinismo del pipeline en ejecuciones repetidas
<!-- labels: P2,ci,task -->
<!-- good_first_issue: no -->
```issue-body
### Contexto
La reproducibilidad exige estabilidad entre ejecuciones equivalentes en entorno controlado.

### Criterios de aceptacion
- Test repetido verifica tolerancias de hash o metricas definidas.
- Diferencias no deterministas quedan documentadas.
- CI publica resultado de prueba de determinismo.

### Archivos probablemente afectados
- tests/
- scripts/benchmark_pipeline.py
- .github/workflows/
```

### [P2-02] Medir rendimiento y paralelizacion de lote con benchmark reproducible
<!-- labels: P2,ci,enhancement -->
<!-- good_first_issue: no -->
```issue-body
### Contexto
El proyecto necesita baseline de rendimiento para priorizar optimizaciones medibles.

### Criterios de aceptacion
- Benchmark reporta tiempos por etapa y hardware.
- Se compara modo secuencial y paralelo.
- Resultado queda versionado en docs o artefactos de CI.

### Archivos probablemente afectados
- scripts/benchmark_pipeline.py
- src/nexoraw/workflow.py
- docs/OPERATIVE_REVIEW_PLAN.md
```

### [P2-03] Consolidar empaquetado reproducible para Linux y Windows
<!-- labels: P2,ci,task -->
<!-- good_first_issue: no -->
```issue-body
### Contexto
Las releases deben reconstruirse con pasos repetibles y auditoria de dependencias externas.

### Criterios de aceptacion
- Scripts de build generan artefactos repetibles por version.
- Se documenta entorno y entradas de build.
- Validacion automatica de instaladores publicada en CI.

### Archivos probablemente afectados
- packaging/debian/
- packaging/windows/
- docs/RELEASE_INSTALLERS.md
```

### [P2-04] Publicar guia de contribucion cientifica para captura, iluminacion y QA colorimetrico
<!-- labels: P2,docs,task -->
<!-- good_first_issue: yes -->
```issue-body
### Contexto
La comunidad necesita una guia operativa para contribuir evidencia tecnica comparable.

### Criterios de aceptacion
- Documento explica protocolo minimo de captura y carta.
- Define metadatos obligatorios para reportar DeltaE.
- Enlaza a plantillas de issue de validacion colorimetrica.

### Archivos probablemente afectados
- docs/
- CONTRIBUTING.md
- README.md
```

### [P2-05] Mantener smoke tests GUI Qt en modo headless local
<!-- labels: P2,gui,task -->
<!-- good_first_issue: no -->
```issue-body
### Contexto
Los smoke GUI evitan regresiones obvias de interfaz en cambios de flujo y empaquetado.

### Criterios de aceptacion
- Smoke local de GUI se ejecuta con entorno headless.
- Error en carga minima de GUI falla la pipeline de checks.
- Documentacion describe como reproducir localmente.

### Archivos probablemente afectados
- tests/
- scripts/run_checks.sh
- src/nexoraw/gui.py
```

### [P2-06] Llevar smoke GUI a CI multiplataforma
<!-- labels: P2,ci,task -->
<!-- good_first_issue: no -->
```issue-body
### Contexto
El comportamiento GUI debe verificarse en Linux, macOS y Windows para release confiable.

### Criterios de aceptacion
- Job de CI ejecuta smoke GUI en matriz multiplataforma.
- Fallos por dependencias graficas quedan diagnosticados.
- Resultado de smoke queda visible en estado de PR.

### Archivos probablemente afectados
- .github/workflows/
- tests/
- docs/WINDOWS_INSTALLER.md
```

### [P2-07] Automatizar auditoria de licencias y avisos para releases AGPL
<!-- labels: P2,legal,task -->
<!-- good_first_issue: yes -->
```issue-body
### Contexto
Cada release debe validar compatibilidad de licencias y avisos de redistribucion.

### Criterios de aceptacion
- Script lista dependencias y licencias detectadas.
- Falla release si faltan avisos obligatorios.
- Resultado se integra en flujo de release/CI.

### Archivos probablemente afectados
- docs/THIRD_PARTY_LICENSES.md
- scripts/
- .github/workflows/
```

## P3

### [P3-01] Integrar manifiestos C2PA-CAI firmados para cadena de custodia del proceso
<!-- labels: P3,legal,enhancement -->
<!-- good_first_issue: no -->
```issue-body
### Contexto
La cadena de custodia interoperable requiere firma y verificacion de manifiestos C2PA junto al proof propio.

### Criterios de aceptacion
- TIFF final puede firmarse y verificarse con C2PA.
- Verificacion cruza hash RAW-TIFF y estado de firma.
- Se documentan limites de confianza (`untrusted` local).

### Archivos probablemente afectados
- src/nexoraw/provenance/c2pa.py
- src/nexoraw/provenance/nexoraw_proof.py
- docs/C2PA_CAI.md
```

### [P3-02] Anadir perfilado avanzado LUT ademas de matriz 3x3
<!-- labels: P3,profile,enhancement -->
<!-- good_first_issue: no -->
```issue-body
### Contexto
Algunos casos de uso requieren modelos de perfil mas complejos que una matriz 3x3.

### Criterios de aceptacion
- Se habilita flujo LUT documentado y reproducible.
- QA compara matriz vs LUT con metricas consistentes.
- Sidecar indica modelo de perfil usado.

### Archivos probablemente afectados
- src/nexoraw/profile/builder.py
- src/nexoraw/profile/export.py
- src/nexoraw/workflow.py
```

### [P3-03] Crear comparador automatico de perfiles entre sesiones e iluminantes
<!-- labels: P3,profile,enhancement -->
<!-- good_first_issue: no -->
```issue-body
### Contexto
Comparar perfiles entre sesiones ayuda a detectar deriva y cambios instrumentales.

### Criterios de aceptacion
- CLI compara al menos dos reportes de QA/perfiles.
- Reporte resume diferencias clave y outliers.
- GUI puede visualizar resumen comparativo.

### Archivos probablemente afectados
- src/nexoraw/qa_compare.py
- src/nexoraw/cli.py
- src/nexoraw/gui.py
```

### [P3-04] Implementar internacionalizacion GUI es-en y presets tecnicos por disciplina
<!-- labels: P3,gui,enhancement -->
<!-- good_first_issue: no -->
```issue-body
### Contexto
La adopcion comunitaria mejora con interfaz bilingue y presets segun disciplina.

### Criterios de aceptacion
- GUI soporta cambio de idioma es/en.
- Presets por disciplina quedan versionados y trazables.
- Tests de smoke cubren seleccion de idioma y preset.

### Archivos probablemente afectados
- src/nexoraw/gui.py
- src/nexoraw/resources/
- docs/MANUAL_USUARIO.md
```
