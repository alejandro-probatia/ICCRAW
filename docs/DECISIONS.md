# Technical Decisions

## DEC-0001: Lenguaje principal del núcleo

- Estado: aceptada
- Fecha: 2026-04-23

Decisión:

- usar **Python** como lenguaje principal del núcleo y CLI para maximizar mantenibilidad comunitaria y velocidad de iteración científica.

Motivación:

1. ecosistema científico maduro,
2. menor barrera de contribución,
3. integración directa con tooling de visión/colorimetría.

## DEC-0002: Motor de perfil ICC

- Estado: aceptada
- Fecha: 2026-04-23

Decisión:

- motor de build de perfil ICC: **ArgyllCMS** (`colprof`) como único backend soportado.

Motivación:

1. ArgyllCMS es referencia técnica consolidada,
2. permite validación/contraste externo,
3. evita divergencias entre motores y mejora la reproducibilidad entre entornos.

## DEC-0003: Dependencias de imagen y RAW

- Estado: aceptada
- Fecha: 2026-04-23

Decisión:

- `dcraw` como motor principal de revelado RAW (invocado por subprocess),
- `rawpy` como dependencia opcional para metadatos RAW enriquecidos,
- `opencv-python-headless` para detección geométrica,
- `tifffile` para export TIFF 16-bit,
- `colour-science` para métricas y conversiones colorimétricas.

## DEC-0004: Licencia inicial

- Estado: aceptada
- Fecha: 2026-04-23

Decisión:

- licencia del repositorio: `AGPL-3.0-or-later`.
- gobernanza y mantenimiento: comunidad de la **Asociacion Espanola de Imagen Cientifica y Forense**.

Compatibilidad (resumen):

1. `dcraw` y `ArgyllCMS` se usan como herramientas externas (subproceso), evitando acoplamiento binario directo,
2. OpenCV BSD: compatible,
3. `rawpy` es opcional y no bloquea el funcionamiento del pipeline principal.

Cumplimiento (resumen):

1. toda distribucion del software debe incluir acceso a la fuente correspondiente bajo AGPL,
2. en despliegues de red/aplicacion remota, se mantiene obligacion AGPL de ofrecer fuente al usuario remoto,
3. se conserva trazabilidad de herramientas externas y sus versiones en el contexto de ejecucion.
