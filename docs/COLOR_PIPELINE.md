# Color Pipeline

## Estado operativo

El diseño actual define correctamente la intencion del pipeline, pero la
implementacion todavia requiere cerrar los hallazgos criticos documentados en:

- [Revision operativa y plan de profesionalizacion](OPERATIVE_REVIEW_PLAN.md)

Hasta completar los P0, el pipeline debe considerarse apto para prototipado y
pruebas controladas, no para produccion cientifica/forense.

## Modo científico (profiling_mode)

Objetivo: neutralidad y reproducibilidad, no estética.

Reglas:

1. sin sharpen creativo,
2. sin denoise agresivo,
3. sin curvas tonales artísticas,
4. WB fijo o explícito,
5. salida lineal para perfilado.

## Fases

1. `raw-info`: metadatos técnicos.
2. `develop`: revelado base controlado lineal con LibRaw/rawpy para entradas RAW.
3. `detect-chart`: homografía + parches.
4. `sample-chart`: medición robusta por parche.
5. `build-develop-profile`: neutralidad y densidad desde fila neutra de carta.
6. receta calibrada: WB fijo, EV limitado por preservación de altas luces,
   salida lineal y sin procesos creativos.
7. segunda medición de carta con la misma geometría y receta calibrada.
8. `build-profile`: ArgyllCMS (`colprof`) como motor único de perfil ICC.
9. `validate-profile`: DeltaE 76/2000 del ICC real.
10. `batch-develop`: receta calibrada + ICC de entrada de sesion sobre lote RAW.

La metodologia completa queda descrita en
[Metodologia de revelado RAW y gestion ICC](METODOLOGIA_COLOR_RAW.md).

## Invariantes criticas

1. [x] La receta ejecutada debe coincidir con la receta declarada; no se permiten
   mapeos silenciosos de algoritmos o parametros.
2. [x] El TIFF de auditoria lineal debe escribirse antes de cualquier curva tonal o
   conversion de salida.
3. [x] La gestion ICC debe separar:
   - asignacion de perfil de entrada,
   - conversion mediante CMM a perfil de salida.
4. [x] La validacion debe comprobar el ICC real generado, no solo artefactos
   numericos auxiliares.
5. [x] El fallback de deteccion de carta no debe producir perfiles automaticamente
   sin confirmacion o modo explicito.
6. [x] La geometria de carta detectada en la pasada base se reutiliza en la
   pasada calibrada; no depende del renderizado ya corregido.
7. [x] El perfil ICC no debe compensar exposición/densidad básica si la carta
   permite construir antes una receta calibrada.
8. [x] Si hay carta y perfil ICC de sesion, el TIFF maestro conserva RGB lineal
   de camara/sesion e incrusta ese ICC. Los perfiles genericos de salida quedan
   para derivados o flujos sin carta; en el flujo sin carta se generan dentro
   de `00_configuraciones/profiles/generic/` y se declaran como `generic_output_icc`.
9. [x] La visualizacion en pantalla usa una conversion exclusiva de display:
   desde la preview sRGB de trabajo hacia el perfil ICC del monitor configurado
   en el sistema, con sRGB solo como fallback si no hay perfil detectable.

## Gestion de color de monitor

El perfil ICC de monitor no participa en el revelado, en el TIFF maestro ni en
la exportacion. Solo corrige la representacion visual de previews y miniaturas.

Politica de deteccion:

- Windows: perfil de salida asociado al contexto de pantalla mediante
  `GetICMProfileW`.
- macOS: espacio ColorSync del display principal mediante
  `CGDisplayCopyColorSpace` y datos ICC de `CGColorSpace`.
- Linux/BSD: perfil de display gestionado por `colord`/`colormgr`; si no esta
  disponible, fallback a `_ICC_PROFILE` de X11 cuando exista.

El usuario puede sustituir manualmente el ICC de monitor desde Configuracion
global > Preview / monitor. Si el perfil desaparece o no se puede abrir, NexoRAW
lo registra en el log y muestra la preview en sRGB para no bloquear el trabajo.

## Validez del perfil

El perfil depende de:

- cámara,
- óptica,
- iluminante,
- recipe,
- versión del software.

Cambiar esos factores puede degradar o invalidar la validez colorimétrica.
