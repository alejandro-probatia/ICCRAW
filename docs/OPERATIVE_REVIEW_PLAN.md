# Revision operativa y plan de profesionalizacion

Fecha de revision: 2026-04-24.

Estado: documento rector para convertir el prototipo actual en una herramienta
operativa, auditable y apta para validacion cientifica.

## 1. Alcance

Este documento recoge los hallazgos tecnicos detectados en la revision del
proyecto NexoRAW y define un plan de trabajo estructurado para implementar las
correcciones de forma profesional.

El objetivo no es convertir el proyecto en un editor fotografico generalista.
El objetivo es un pipeline controlado para captura, revelado RAW, perfilado ICC,
aplicacion a lotes, validacion colorimetrica y trazabilidad de uso cientifico,
documental y forense.

## 2. Resumen ejecutivo

NexoRAW ya tiene una base razonable:

- arquitectura Python modular,
- CLI funcional,
- GUI inicial,
- recetas reproducibles,
- integracion con LibRaw/rawpy, `exiftool` y ArgyllCMS,
- sidecars JSON y manifiestos de lote,
- tests unitarios iniciales.

Pero el proyecto aun no debe considerarse operativo en produccion cientifica.
Los principales bloqueos estan en:

1. contrato de revelado RAW insuficientemente estricto,
2. gestion de color ICC no alineada con un flujo CMM estandar,
3. validacion que no comprueba realmente el perfil ICC generado,
4. deteccion de carta demasiado permisiva,
5. recetas que declaran parametros que el codigo no aplica,
6. ausencia de dataset RAW real para regresion.

La prioridad es cerrar estos puntos antes de ampliar GUI, automatizaciones o
funciones avanzadas.

## 3. Referencias tecnicas y estandares

El desarrollo debe alinearse, como minimo, con estas referencias:

- ISO 17321-1:2012: caracterizacion de color de camaras digitales.
  https://www.iso.org/standard/56537.html
- ISO 12234-4:2026: Digital Negative (DNG), formato RAW abierto/normalizado.
  https://www.iso.org/standard/86123.html
- ICC v4.4 / ISO 15076: arquitectura y formato de perfiles ICC.
  https://color.org/index.xalter
- ISO/CIE 11664-4:2019: CIE 1976 L*a*b*.
  https://www.iso.org/standard/74166.html
- CIE 199:2011: recomendacion de CIELAB/CIEDE2000 para diferencias de color.
  https://www.cie.co.at/publications/methods-evaluating-colour-differences-images
- ISO 15739:2023: ruido y rango dinamico en camaras digitales.
  https://www.iso.org/standard/82233.html
- ISO 17957:2015: medicion de shading en camaras digitales.
  https://www.iso.org/standard/31974.html
- EMVA 1288 Release 4.0: caracterizacion objetiva de camaras/sensores.
  https://www.emva.org/news/new-release-4-0-of-emva-1288-standard-for-camera-characterization-in-effect/
- ArgyllCMS `colprof`: generacion de perfiles desde valores de carta.
  https://argyllcms.com/doc/colprof.html

## 4. Hallazgos tecnicos

### H-001 Gestion ICC no estandar en salida de lote

Criticidad: critica.

Estado de implementacion:

- mitigacion inicial implementada: la exportacion de lote ya separa RGB de camara
  con perfil de entrada incrustado y conversion a sRGB mediante LittleCMS
  (`tificc`).
- pendiente: validacion cruzada externa mas amplia de perfiles ICC reales.

Situacion detectada en la revision inicial:

- `batch_develop` revela a TIFF lineal, aplica una matriz propia
  `camera_to_xyz -> sRGB` y despues incrusta el ICC generado.
- Esto mezcla dos conceptos distintos:
  - asignar un perfil de entrada a datos RGB de camara,
  - convertir datos a un espacio de salida mediante un CMM.

Evidencia local:

- `src/iccraw/profile/export.py`: `batch_develop` y `apply_profile_matrix`.
- `src/iccraw/profile/builder.py`: calculo de `matrix_camera_to_xyz` y sidecar
  `.profile.json`.

Riesgo:

- conversion doble,
- clipping no controlado,
- TIFF que declara un perfil que no describe realmente sus pixeles,
- resultados distintos segun aplicacion externa.

Direccion tecnica:

1. Definir dos modos explicitos:
   - `assign-input-profile`: TIFF en RGB camara + perfil ICC de entrada incrustado.
   - `convert-to-output-profile`: transformacion con CMM real a sRGB/AdobeRGB/XYZ/Lab.
2. Integrar un CMM real para conversiones ICC:
   - LittleCMS via `Pillow.ImageCms`, `lcms2` o herramienta externa equivalente,
   - o ArgyllCMS (`cctiff`/flujo validado) si se decide mantener dependencia CLI.
3. Eliminar la aplicacion silenciosa de la matriz lateral como salida principal.
4. Mantener la matriz solo como artefacto diagnostico, no como sustituto del ICC.

Criterios de aceptacion:

- un TIFF convertido a sRGB declara perfil sRGB, no perfil de camara,
- un TIFF en RGB camara declara perfil de camara y no ha sido transformado,
- pruebas comparan transformacion ICC con herramienta externa de referencia,
- el manifiesto declara modo de gestion de color usado.

### H-002 Receta RAW declara algoritmos no soportados por el backend

Criticidad: critica.

Estado de implementacion:

- mitigado: el proyecto usa LibRaw/rawpy como unico backend RAW, recetas de
  ejemplo con `demosaic_algorithm: dcb` y validacion estricta.

Situacion detectada en la revision inicial:

- La receta de ejemplo usaba `demosaic_algorithm: rcd`.
- El codigo mapeaba nombres no soportados a otro algoritmo de forma silenciosa.

Evidencia local:

- `testdata/recipes/scientific_recipe.yml`: receta cientifica.
- `src/iccraw/raw/pipeline.py`: validacion `LIBRAW_DEMOSAIC_MAP`.

Riesgo:

- la trazabilidad dice que se uso RCD, pero realmente se uso AHD,
- un cambio de demosaicing invalida comparaciones colorimetricas,
- no hay fallo temprano cuando la receta no es ejecutable.

Direccion tecnica:

1. Sustituir mapeos silenciosos por validacion estricta.
2. Introducir `effective_recipe` o `execution_contract` en sidecars.
3. Mantener LibRaw/rawpy como backend unico y ampliar solo algoritmos soportados
   por ese motor.

Criterios de aceptacion:

- receta con algoritmo no soportado falla antes de procesar,
- sidecar registra comando real y parametros efectivos,
- tests cubren recetas validas e invalidas por backend.

### H-003 `audit_linear_tiff` puede no ser lineal

Criticidad: alta.

Estado de implementacion:

- mitigado: `audit_linear_tiff` se escribe antes de compensacion de exposicion y
  curvas de salida.

Situacion detectada en la revision inicial:

- El TIFF de auditoria se escribe despues de aplicar compensacion de exposicion y
  posible curva tonal.

Evidencia local:

- `src/iccraw/raw/pipeline.py`: `develop_controlled`.

Riesgo:

- el artefacto llamado "linear" no garantiza linealidad escena/sensor,
- no sirve como evidencia intermedia fiable.

Direccion tecnica:

1. Separar estados internos:
   - `developed_scene_linear`,
   - `rendered_output`,
   - `profiled_output`.
2. Escribir `audit_linear_tiff` inmediatamente despues de revelado lineal y antes
   de curvas, OETF o conversion de salida.
3. Registrar en metadatos si se aplicaron WB, black/white level, demosaicing y
   normalizacion.

Criterios de aceptacion:

- test con `tone_curve: srgb` demuestra que `audit_linear_tiff` no cambia,
- nombre de archivo y sidecar describen claramente cada estado,
- no hay curva tonal en modo `profiling_mode`.

### H-004 Validacion basada en matriz lateral, no en perfil ICC real

Criticidad: alta.

Estado de implementacion:

- mitigado: `validate-profile` consulta el ICC real con ArgyllCMS (`xicclu` o
  `icclu`) y ya no depende de la matriz del sidecar `.profile.json`.
- pendiente: separar formalmente muestras de entrenamiento y validacion cuando
  exista dataset de capturas reales suficiente.

Situacion detectada en la revision inicial:

- `validate-profile` carga `.profile.json` y aplica la matriz propia.
- No valida la transformacion ICC generada por `colprof`.
- No obliga a separar muestras de entrenamiento y validacion.

Evidencia local:

- `src/iccraw/profile/builder.py`: `validate_profile`.
- `src/iccraw/profile/builder.py`: `_build_profile_with_argyll`.

Riesgo:

- metricas DeltaE optimistas o no representativas,
- el ICC puede ser invalido aunque la matriz lateral parezca aceptable,
- no hay control de generalizacion entre capturas.

Direccion tecnica:

1. Validar el ICC real con CMM/ArgyllCMS, no solo la matriz lateral.
2. Separar:
   - `fit_report`: errores sobre muestras usadas para construir perfil,
   - `validation_report`: errores sobre capturas independientes.
3. Registrar DeltaE76 y DeltaE2000, ademas de outliers por parche.
4. Definir umbrales por caso de uso y tipo de carta.

Criterios de aceptacion:

- validacion falla si falta el ICC aunque exista sidecar,
- validacion cruzada usa capturas no incluidas en construccion,
- reporte incluye media, mediana, p95, maximo y parches fuera de tolerancia.

### H-005 Deteccion de carta demasiado permisiva

Criticidad: alta.

Estado de implementacion:

- mitigado: la deteccion fallback queda marcada como `detection_mode=fallback`,
  tiene confianza maxima 0.05 y `valid_patch_ratio=0.0`.
- mitigado: `auto-profile-batch` y la generacion automatica de perfil rechazan
  fallback por defecto; solo se acepta con opt-in explicito.
- mitigado: la deteccion automatica incorpora ajuste por patron interno de
  parches ColorChecker24, validado con dos DNG reales de Pixel 6a.
- mitigado: `detect-chart --manual-corners` permite marcar cuatro esquinas y
  generar `detection.json` revisable con overlay.
- mitigado: la GUI permite marcar cuatro puntos en el visor y guardar una
  deteccion manual con overlay.
- pendiente: enlazar detecciones manuales guardadas con cada captura dentro del
  flujo batch automatico.

Situacion detectada en la revision inicial:

- Si no se detecta contorno, se usa un bbox de fallback.
- Ese fallback puede devolver una confianza alta si la geometria aparente encaja.

Evidencia local:

- `src/iccraw/chart/detection.py`: `detect_chart` y `_confidence_score`.
- Observado en smoke test: warning de fallback con `confidence_score: 1.0`.

Riesgo:

- muestreo de zonas incorrectas,
- perfil construido con muestras erroneas,
- resultados aparentemente validos pero cientificamente invalidos.

Direccion tecnica:

1. Fallback geometrico debe tener confianza baja o requerir confirmacion manual.
2. `auto-profile-batch` no debe aceptar fallback sin opt-in explicito.
3. La deteccion debe incorporar checks de orientacion, patch layout y coherencia
   cromatica/luminancia.
4. Añadir modo manual asistido para esquinas de carta.
5. Añadir detector por patron de parches para cartas Passport o escenas con
   contorno exterior ambiguo.

Criterios de aceptacion:

- fallback no supera `min_confidence` por defecto,
- reporte marca `detection_mode: automatic|manual|fallback`,
- overlay y JSON incluyen warnings bloqueantes cuando proceda.
- dos DNG reales con ColorChecker Passport detectan la carta inferior de forma
  automatica con confianza alta.

### H-005b Perfil de revelado cientifico previo al ICC

Criticidad: alta.

Estado de implementacion:

- mitigado: `build-develop-profile` calcula WB fijo y compensacion EV desde la
  fila neutra de la carta.
- mitigado: la compensacion EV se limita por preservacion de altas luces de la
  carta para evitar clipping.
- mitigado: `auto-profile-batch` ejecuta doble pasada:
  receta base -> perfil de revelado -> receta calibrada -> ICC.
- mitigado: la geometria detectada se reutiliza en la pasada calibrada para que
  el muestreo no dependa del renderizado.

Riesgo:

- si el ICC absorbe errores de exposición, densidad o neutralidad, el perfil
  deja de describir solo la respuesta cromatica de cámara + iluminante.

Direccion tecnica:

1. Separar perfil de revelado y perfil ICC como artefactos distintos.
2. Usar carta para normalizar neutralidad y densidad antes de perfilar.
3. Mantener nitidez/contraste local como QA medible, no como ajuste creativo.

### H-006 Parametros de receta ignorados por el muestreo

Criticidad: media.

Estado de implementacion:

- mitigado: `sampling_trim_percent` y `sampling_reject_saturated` se cargan desde
  recetas YAML/JSON y se aplican en el muestreo.
- pendiente: margen de parche configurable y criterios avanzados de exclusion.

Situacion detectada en la revision inicial:

- La receta declara `trim_percent` y `reject_saturated`.
- El codigo normaliza `sampling_strategy` a un string y usa `0.1` fijo.

Evidencia local:

- `testdata/recipes/scientific_recipe.yml`: bloque `sampling_strategy`.
- `src/iccraw/core/recipe.py`: `_normalize_recipe_payload`.
- `src/iccraw/chart/sampling.py`: `_sample_patch`.

Riesgo:

- el operador cree que controla el muestreo, pero el codigo no obedece,
- se reduce reproducibilidad y auditabilidad.

Direccion tecnica:

1. Modelar `sampling_strategy` como estructura, no solo string.
2. Aplicar `trim_percent`, `reject_saturated`, margen de parche y criterios de
   exclusion desde receta.
3. Registrar parametros efectivos por parche.

Criterios de aceptacion:

- tests demuestran que cambiar `trim_percent` cambia el resultado,
- sidecar de muestras incluye parametros efectivos,
- receta invalida falla con mensaje claro.

### H-007 Referencias de carta y observador insuficientemente tipadas

Criticidad: media.

Estado de implementacion:

- mitigado: `ReferenceCatalog.from_path()` valida metadatos obligatorios,
  iluminante D50, observador 2 grados, fuente de referencia, ids de parche y
  valores Lab.
- pendiente: soportar adaptacion cromatica documentada para referencias no D50
  si se decide ampliar el pipeline.

Situacion detectada en la revision inicial:

- El catalogo lee `observer`, pero el perfilado fija internamente D50.
- No se valida que `reference_lab` corresponda al iluminante/observador esperado.

Evidencia local:

- `src/iccraw/chart/sampling.py`: `ReferenceCatalog`.
- `src/iccraw/profile/builder.py`: `D50_XYZ`.

Riesgo:

- mezcla involuntaria de referencias D50/D65 u observador 2/10 grados,
- DeltaE no comparable entre sesiones.

Direccion tecnica:

1. Tipar catalogo de referencia con iluminante, observador, fuente y version.
2. Validar compatibilidad entre referencia, receta e iluminacion de sesion.
3. Soportar adaptacion cromatica documentada si se aceptan referencias no D50.

Criterios de aceptacion:

- referencia sin iluminante/observador falla en modo estricto,
- reporte incluye fuente/version de referencia,
- tests cubren D50 compatible y referencia incompatible.

### H-008 Falta dataset RAW real para regresion

Criticidad: critica para produccion, alta para desarrollo.

Situacion:

- Los archivos `testdata/raw/*.nef` y `*.cr3` actuales son marcadores de texto.
- Las pruebas no ejercitan revelado RAW real.

Evidencia local:

- `testdata/raw/mock_capture.nef`.
- `testdata/raw/batch/session_001.nef`.
- `testdata/raw/batch/session_002.cr3`.
- `tests/test_pipeline_libraw.py` cubre contrato de parametros LibRaw; falta
  dataset RAW real para integracion.

Riesgo:

- CI verde sin cubrir el punto mas importante del proyecto,
- incompatibilidades con camaras reales detectadas tarde,
- no se puede medir determinismo entre versiones.

Direccion tecnica:

1. Crear dataset minimo con DNG/NEF/CR2/ARW reales, licencia clara y tamaño
   controlado.
2. Mantener subset pequeño en repo o descargarlo en CI con checksum.
3. Separar tests unitarios, smoke e integracion pesada.

Criterios de aceptacion:

- al menos un test revela un RAW/DNG real con herramientas externas,
- checksums de salidas son estables bajo tolerancia definida,
- CI distingue tests que requieren RAW real/`colprof`.

## 5. Plan de trabajo profesional

### Fase 0 - Cierre de contrato tecnico

Objetivo:

- convertir decisiones implicitas en contratos de ejecucion verificables.

Entregables:

1. Documento de contrato de pipeline:
   - estados de imagen,
   - espacios de color,
   - uso de ICC,
   - artefactos intermedios,
   - invariantes cientificas.
2. ADRs para:
   - backend RAW primario,
   - motor CMM,
   - politica de perfiles ICC,
   - politica de validacion DeltaE.
3. Tabla de compatibilidad de receta por backend.

Criterio de salida:

- ninguna funcion critica acepta parametros que no pueda ejecutar fielmente.

### Fase 1 - P0 RAW y trazabilidad

Objetivo:

- asegurar que el revelado ejecutado coincide exactamente con lo declarado.

Tareas:

1. Validacion estricta de receta.
2. Registro de parametros efectivos LibRaw y versiones externas.
3. Separacion de `audit_linear_tiff` y salida renderizada.
4. Tests de recetas validas/invalidas.
5. Dataset RAW real minimo.

Criterio de salida:

- el pipeline falla temprano ante configuracion no soportada y genera sidecars
  suficientes para repetir la ejecucion.

### Fase 2 - P0 gestion ICC y salida de lote

Objetivo:

- alinear la salida con un flujo ICC interoperable.

Tareas:

1. Definir modos de salida:
   - `camera_rgb_with_input_icc`,
   - `converted_srgb`,
   - `converted_xyz_or_lab` si se justifica cientificamente.
2. Integrar CMM real.
3. Sustituir aplicacion de matriz por transformacion ICC validada.
4. Validar perfiles con herramientas externas (`iccdump`, ArgyllCMS, LittleCMS).
5. Documentar comportamiento de TIFF final.

Criterio de salida:

- cualquier TIFF exportado puede abrirse en software color-managed y su perfil
  describe correctamente los pixeles.

### Fase 3 - P1 carta, muestreo y QA de captura

Objetivo:

- impedir que una deteccion o muestra mala produzca un perfil aparentemente valido.

Tareas:

1. Reducir confianza del fallback y hacerlo bloqueante por defecto.
2. Añadir modo manual asistido para esquinas de carta.
3. Aplicar parametros reales de muestreo desde receta.
4. Detectar saturacion, bajo nivel, no uniformidad e iluminacion irregular.
5. Reportar outliers por parche y motivo de exclusion.

Criterio de salida:

- una captura deficiente produce un diagnostico claro y no genera perfil sin
  confirmacion explicita.

### Fase 4 - P1 validacion colorimetrica

Objetivo:

- separar construccion, validacion y aptitud de uso del perfil.

Tareas:

1. Split de muestras: entrenamiento/validacion.
2. Validacion del ICC real mediante CMM.
3. Umbrales DeltaE por disciplina o preset.
4. Reportes comparables entre sesiones.
5. Pruebas de estabilidad entre ejecuciones repetidas.

Criterio de salida:

- un perfil tiene estado `draft`, `validated`, `rejected` o `expired`, con
  razones auditables.

### Fase 5 - P2 reproducibilidad, CI y distribucion

Objetivo:

- hacer que el comportamiento sea sostenible por la comunidad.

Tareas:

1. CI con matrices:
   - unit,
   - integration-with-tools,
   - optional-gui-smoke.
2. Checks de versiones de herramientas externas.
3. Contenedor o entorno reproducible para validacion.
4. Benchmark de determinismo y rendimiento.
5. Auditoria de licencias antes de releases.

Criterio de salida:

- una release puede reconstruirse, probarse y auditarse con instrucciones claras.

### Fase 6 - P3 ampliacion controlada

Objetivo:

- ampliar capacidades sin comprometer trazabilidad.

Tareas:

1. Soporte IT8 completo.
2. Perfiles LUT si el caso de uso lo justifica.
3. Comparador de perfiles entre sesiones/iluminantes.
4. C2PA/CAI para cadena de custodia.
5. Internacionalizacion y presets por disciplina.

Criterio de salida:

- las funciones avanzadas heredan el mismo contrato de validacion y auditoria.

## 6. Definicion de "hecho"

Una tarea critica se considera terminada solo si cumple:

1. codigo implementado con tests unitarios,
2. smoke test CLI documentado,
3. sidecars/manifiestos actualizados,
4. documentacion de usuario o tecnica actualizada,
5. entrada en `CHANGELOG.md`,
6. impacto en reproducibilidad evaluado,
7. no introduce cambios silenciosos en salida colorimetrica.

## 7. Criterios de operatividad minima

El proyecto podra considerarse "operativo para pruebas cientificas controladas"
cuando cumpla:

1. revelado RAW real probado con dataset minimo,
2. recetas estrictas sin mapeos silenciosos,
3. audit TIFF realmente lineal,
4. salida ICC interoperable,
5. validacion del ICC real,
6. fallback de carta bloqueante por defecto,
7. reportes DeltaE con umbrales y outliers,
8. manifiesto de lote con hashes, versiones, perfil y modo de color.

No deberia considerarse "validado para produccion forense" hasta contar ademas
con:

1. protocolo de captura aprobado,
2. dataset de regresion multi-camara,
3. validacion independiente por laboratorio o comunidad tecnica,
4. cadena de custodia documentada,
5. control de versiones de perfiles y recetas por sesion.

## 8. Orden recomendado de implementacion

1. Validacion estricta de receta y eliminacion de mapeos silenciosos.
2. Correccion de `audit_linear_tiff`.
3. Separacion de modos ICC en batch.
4. Integracion de CMM real.
5. Validacion del ICC real.
6. Bloqueo de fallback de carta.
7. Parametros de muestreo completos.
8. Dataset RAW real y CI de integracion.
9. Reportes de calidad por sesion.
10. C2PA/CAI y empaquetado reproducible.

## 9. Riesgos principales

1. Compatibilidad RAW:
   - LibRaw/rawpy cubre mas formatos modernos, pero puede variar entre versiones.
   - Mitigacion: registrar version LibRaw/rawpy y usar dataset RAW de regresion.
2. Interoperabilidad ICC:
   - no todos los consumidores interpretan igual perfiles de entrada.
   - Mitigacion: validar con LittleCMS/ArgyllCMS y TIFFs de referencia.
3. Datos de referencia:
   - cartas envejecen, referencias cambian y metrologia puede no estar trazada.
   - Mitigacion: versionar referencias y registrar fuente/espectrofotometro.
4. Uso forense:
   - una herramienta tecnica no basta sin protocolo de captura y custodia.
   - Mitigacion: documentar procedimiento y separar resultado tecnico de dictamen.

## 10. Estado de pruebas observado en esta revision

Entorno local:

- `rawpy`/LibRaw: disponible en entorno de desarrollo.
- `colprof 3.1.0`: disponible.
- `exiftool 12.76`: disponible.
- tests Python en `.venv`: `21 passed`.

Smoke test con TIFF sintetico:

- deteccion, muestreo, build-profile, validate-profile y batch-develop ejecutan,
- el perfil ICC se genera con ArgyllCMS,
- el TIFF final incrusta ICC,
- se observa que la matriz lateral puede producir clipping y que el fallback de
  deteccion puede devolver confianza demasiado alta.

Limitacion importante:

- no se ha validado con RAW real porque los RAW de `testdata/raw` son ficheros
  de texto de placeholder.
