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
2. `develop`: revelado controlado lineal con `dcraw` para entradas RAW.
3. `detect-chart`: homografía + parches.
4. `sample-chart`: medición robusta por parche.
5. `build-profile`: ArgyllCMS (`colprof`) como motor único de perfil ICC.
6. `validate-profile`: DeltaE 76/2000.
7. `batch-develop`: mismo recipe + mismo perfil sobre lote RAW.

## Invariantes pendientes de implementacion estricta

1. La receta ejecutada debe coincidir con la receta declarada; no se permiten
   mapeos silenciosos de algoritmos o parametros.
2. El TIFF de auditoria lineal debe escribirse antes de cualquier curva tonal o
   conversion de salida.
3. La gestion ICC debe separar:
   - asignacion de perfil de entrada,
   - conversion mediante CMM a perfil de salida.
4. La validacion debe comprobar el ICC real generado, no solo artefactos
   numericos auxiliares.
5. El fallback de deteccion de carta no debe producir perfiles automaticamente
   sin confirmacion o modo explicito.

## Validez del perfil

El perfil depende de:

- cámara,
- óptica,
- iluminante,
- recipe,
- versión del software.

Cambiar esos factores puede degradar o invalidar la validez colorimétrica.
