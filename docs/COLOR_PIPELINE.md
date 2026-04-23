# Color Pipeline

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

## Validez del perfil

El perfil depende de:

- cámara,
- óptica,
- iluminante,
- recipe,
- versión del software.

Cambiar esos factores puede degradar o invalidar la validez colorimétrica.
