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

- motor preferente para build de perfil: **ArgyllCMS** (`colprof`) cuando está instalado.
- fallback operativo: perfil matrix/shaper interno reproducible para no bloquear ejecución en entornos sin Argyll.

Motivación:

1. ArgyllCMS es referencia técnica consolidada,
2. permite validación/contraste externo,
3. fallback interno mantiene continuidad de pipeline y testing.

## DEC-0003: Dependencias de imagen y RAW

- Estado: aceptada
- Fecha: 2026-04-23

Decisión:

- `rawpy` (LibRaw) para ingesta/revelado,
- `opencv-python-headless` para detección geométrica,
- `tifffile` para export TIFF 16-bit,
- `colour-science` para métricas y conversiones colorimétricas.

## DEC-0004: Licencia inicial

- Estado: aceptada (revisable si cambia estrategia de linking/distribución)
- Fecha: 2026-04-23

Decisión:

- licencia del repositorio: `GPL-3.0-or-later`.

Compatibilidad (resumen):

1. LibRaw (vía rawpy): compatible en este modelo de distribución,
2. OpenCV BSD: compatible,
3. ArgyllCMS usado como herramienta externa (subproceso), evitando acoplamiento binario directo.
