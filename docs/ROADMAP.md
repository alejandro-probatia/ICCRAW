# Roadmap

Documento rector del plan operativo:

- [Revision operativa y plan de profesionalizacion](OPERATIVE_REVIEW_PLAN.md)

## Fase 0 (completada)

- base Python modular,
- CLI MVP funcional,
- pipeline reproducible con recipe,
- tests iniciales,
- trazabilidad JSON,
- GUI Qt inicial para previsualización técnica y flujo automático.

## Fase 1 - Contrato RAW y trazabilidad (P0)

Objetivo: asegurar que lo ejecutado coincide exactamente con lo declarado.

- validacion estricta de recetas,
- eliminacion de mapeos silenciosos de demosaicing,
- registro de comando efectivo y versiones externas,
- correccion de `audit_linear_tiff` para que sea realmente lineal,
- dataset RAW real minimo para regresion.

## Fase 2 - Gestion ICC interoperable (P0)

Objetivo: separar asignacion de perfil de conversion colorimetrica.

- modos de salida explicitos:
  - RGB camara con perfil de entrada,
  - conversion a espacio de salida mediante CMM,
- integracion de CMM real,
- sustitucion de matriz lateral como salida principal,
- validacion externa de perfiles ICC,
- manifiesto de lote con modo de gestion de color.

## Fase 3 - Carta, muestreo y QA de captura (P1)

Objetivo: impedir que detecciones o muestras defectuosas generen perfiles
aparentemente validos.

- fallback de carta bloqueante por defecto,
- deteccion automatica por patron interno de parches ColorChecker24,
- modo manual asistido para esquinas de carta en CLI y GUI,
- referencia ColorChecker 2005 D50 para uso operativo,
- perfil de revelado cientifico derivado de fila neutra: WB, densidad y EV,
- doble pasada carta -> receta calibrada -> ICC,
- flujo GUI en dos pasos: calibrar sesion y aplicar esa sesion a imagenes objetivo,
- parametros de muestreo completos desde receta,
- deteccion de saturacion, bajo nivel y estimacion de iluminacion irregular,
- reportes de outliers por parche en QA de sesion,
- integracion de detecciones manuales por captura en el flujo batch automatico.

## Fase 4 - Validacion colorimetrica (P1)

Objetivo: validar el ICC real y la aptitud del perfil para una sesion.

- separacion entrenamiento/validacion,
- validacion con CMM/ArgyllCMS del perfil ICC generado,
- reporte QA de sesion con estado `validated`, `rejected` o `not_validated`,
- umbrales DeltaE por disciplina o preset,
- estados operacionales de perfil: `draft`, `validated`, `rejected`, `expired`,
- reportes comparables entre sesiones mediante CLI/GUI.

## Fase 5 - Reproducibilidad, CI y distribucion (P2)

Objetivo: hacer que el comportamiento sea sostenible por la comunidad.

- CI con tests unitarios e integracion con herramientas externas,
- checks de versiones de `dcraw`, ArgyllCMS y `exiftool`,
- contenedor o entorno reproducible,
- benchmarks de determinismo y rendimiento,
- auditoria de licencias para releases AGPL.

## Fase 6 - Ampliacion controlada (P3)

Objetivo: ampliar capacidades sin comprometer trazabilidad.

- soporte IT8 completo,
- perfiles LUT si el caso de uso lo justifica,
- comparador automatico de perfiles entre sesiones/iluminantes,
- C2PA/CAI para cadena de custodia,
- internacionalizacion GUI (es/en) y presets tecnicos por disciplina.
