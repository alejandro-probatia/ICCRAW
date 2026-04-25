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

- LibRaw mediante `rawpy` como motor único de revelado RAW,
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

1. LibRaw se integra mediante `rawpy`; ArgyllCMS se usa como herramienta externa para perfilado, validacion y conversion ICC,
2. OpenCV BSD: compatible,
3. `rawpy` pasa a ser dependencia crítica del pipeline RAW.

Cumplimiento (resumen):

1. toda distribucion del software debe incluir acceso a la fuente correspondiente bajo AGPL,
2. en despliegues de red/aplicacion remota, se mantiene obligacion AGPL de ofrecer fuente al usuario remoto,
3. se conserva trazabilidad de herramientas externas y sus versiones en el contexto de ejecucion.

## DEC-0005: Stack de interfaz grafica

- Estado: aceptada
- Fecha: 2026-04-23

Decision:

- usar **Qt for Python (PySide6)** para la GUI.

Motivacion:

1. mayor mantenibilidad a medio plazo para interfaz tecnica compleja,
2. buen rendimiento en visualizacion de imagen y herramientas de analisis,
3. licencia comunitaria LGPLv3/GPLv3 con buen encaje en ecosistema AGPL del proyecto.

## DEC-0006: Objetivo no comercial y licencia libre

- Estado: aceptada
- Fecha: 2026-04-23

Decision:

- mantener `AGPL-3.0-or-later` como licencia del repositorio,
- declarar explicitamente que el objetivo de gobernanza del proyecto es cientifico/comunitario sin finalidad comercial.

Motivacion:

1. la AGPL protege la reciprocidad de mejoras y uso en red,
2. añadir clausulas "solo no comercial" romperia compatibilidad open source y reutilizacion cientifica,
3. se prioriza seguridad juridica y compatibilidad con dependencias libres.

## DEC-0007: AMaZE y demosaic packs GPL3

- Estado: aceptada
- Fecha: 2026-04-25

Decision:

- mantener `AGPL-3.0-or-later` como licencia del repositorio,
- permitir AMaZE cuando el backend `rawpy` este respaldado por LibRaw con
  `DEMOSAIC_PACK_GPL3=True`,
- documentar `rawpy-demosaic` como backend recomendado para builds GPL3,
- no activar ni anunciar AMaZE si la build instalada no incluye el pack GPL3.

Motivacion:

1. el demosaic pack GPL3 de LibRaw exige GPL3+ para el producto resultante,
2. la AGPL del proyecto es compatible con GPL3+ y mantiene reciprocidad comunitaria,
3. la trazabilidad forense requiere registrar el backend exacto y sus flags,
4. la GUI debe evitar bloqueos interactivos cuando una receta antigua pide AMaZE
   en un entorno sin soporte GPL3.
