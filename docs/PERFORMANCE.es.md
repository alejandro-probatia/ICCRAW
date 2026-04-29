# Performance

Este documento recoge la politica practica de medicion de rendimiento en
NexoRAW. Las optimizaciones que afecten al flujo canonico deben conservar los
bytes del TIFF firmado salvo que se documenten como cambio de reproducibilidad.

## Herramientas

Perfil granular de comandos reales:

```powershell
python scripts/profile_pipeline.py --out-dir .\profile-out --top 80 -- batch-develop .\raws --recipe .\recipe.yml --profile .\camera.icc --out .\out --workers 1
```

El script escribe:

- `profile.txt`: salida de `cProfile` ordenada por tiempo acumulado.
- `profile.svg`: flamegraph de `py-spy` si esta instalado.

Para comparar batch serial contra paralelo, ejecutar el mismo comando cambiando
solo `--workers 1` por `--workers 0` o por un numero fijo.

Benchmark RAW reproducible en Windows, macOS y Linux:

```powershell
python scripts/benchmark_raw_pipeline.py .\ruta\a\captura.NEF --out .\tmp\raw_benchmark\results.json --cache-dir .\tmp\raw_benchmark\cache --algorithms linear,dcb,amaze --cache-algorithm dcb --process-jobs 4 --process-workers 1,2,4
```

El script mide tiempo de pared, CPU, shape/dtype, tamano del array y pico de
memoria residente del proceso cuando el sistema operativo lo expone.

Benchmark de fluidez GUI:

```powershell
$env:QT_QPA_PLATFORM="offscreen"
python scripts/benchmark_gui_interaction.py --raw .\ruta\a\captura.NEF --algorithm dcb --full-resolution --out .\tmp\gui_benchmark\d850_full_ui.json
```

Este test simula arrastres reales de slider y curva tonal. Mide:

- coste inmediato de `setValue`/emision de puntos de curva,
- p95/p99/max de huecos del event loop Qt,
- tiempo de la ultima preview interactiva,
- hilos pendientes al terminar.

## Politica de workers

`batch-develop` y la fase batch de `auto-profile-batch` aceptan `--workers`.

- Omitido o `0`: seleccion automatica segun CPU y RAM.
- `1`: ejecucion serial para depuracion y regresion.
- `N > 1`: paralelismo real por proceso, acotado por el numero de archivos.

La salida se mantiene estable porque el manifiesto conserva el orden planificado
de entrada, no el orden de finalizacion de los trabajadores.

Si se inyecta un cliente C2PA Python no serializable, el lote usa hilos como
fallback conservador. La ruta normal de CLI usa procesos.

Variables de control:

- `NEXORAW_BATCH_WORKERS`: workers por defecto.
- `NEXORAW_BATCH_MEMORY_RESERVE_MB`: RAM libre reservada antes de calcular
  workers automaticos.
- `NEXORAW_BATCH_WORKER_RAM_MB`: presupuesto estimado por worker.
  Por defecto son 2800 MiB, ajustado a partir de una D850 de 45,7 MP: el
  demosaico DCB consume ~1,52 GiB por proceso y el batch real necesita margen
  adicional para escribir TIFF lineal/final.

## Cache numerica de demosaico

La cache de demosaico es opt-in. Se activa en receta con:

```yaml
use_cache: true
```

Y puede ubicarse desde CLI con `develop`, `batch-develop` y
`auto-profile-batch`:

```powershell
python -m nexoraw batch-develop .\01_ORG --recipe .\recipe.yml --profile .\camera.icc --out .\02_DRV --cache-dir .\00_configuraciones\cache
```

Si no se indica `--cache-dir`, NexoRAW intenta usar
`00_configuraciones/cache/` de la sesion. Si no puede inferir una sesion, usa
`~/.nexoraw/cache/`.

La clave incluye SHA-256 completo del RAW, algoritmo de demosaico, balance de
blancos, modo de negro y firma del backend rawpy/LibRaw. No incluye ajustes de
render que se aplican despues de la escena lineal, como exposicion o curva.

La poda LRU se controla con `NEXORAW_DEMOSAIC_CACHE_MAX_GB` y por defecto
limita la cache a 5 GiB.

## Goldens canonicos

Los tests de `tests/regression/` validan SHA-256 canonicos de salida y TIFF
lineal de auditoria. La receta golden fuerza `use_cache: false` para que la
regresion mida bytes canonicos, no comportamiento de cache.

Regeneracion intencional:

```powershell
python scripts/regenerate_golden_hashes.py --confirm --note "motivo del cambio"
```

Una regeneracion debe ir acompanada de explicacion en changelog si cambia la
reproducibilidad.

## Benchmark local D850

Equipo usado: Windows 11, Python 3.12.4, 32 hilos logicos, RAW Nikon D850
8288x5520 de 51,5 MiB aportado localmente para benchmark. El RAW no forma
parte del repositorio.

| Caso | Tiempo |
| --- | ---: |
| Demosaico `linear` completo | 1,52 s |
| Demosaico `dcb` completo | 5,36 s |
| Demosaico `amaze` completo | 5,57 s |
| Cache populate `dcb` | 5,63 s |
| Cache hit `dcb` | 0,16 s |
| Preview half-size `dcb` | 0,85-0,88 s |
| CLI `develop` sin cache, audit + TIFF final | 7,24 s |
| CLI `develop` con cache hit, audit + TIFF final | 1,59 s |

Benchmark GUI con el mismo RAW, Qt `offscreen`, 80 pasos por control:

| Fuente | Control | p95 evento UI | p95 event loop | max event loop | Preview final |
| --- | --- | ---: | ---: | ---: | ---: |
| D850 half-size 2760x4144 | brillo | 0,063 ms | 16,84 ms | 55,32 ms | 272 ms |
| D850 half-size 2760x4144 | curva tonal | 0,128 ms | 16,87 ms | 49,41 ms | 434 ms |
| D850 completa 5520x8288 | brillo | 0,053 ms | 16,72 ms | 58,94 ms | 275 ms |
| D850 completa 5520x8288 | curva tonal | 0,094 ms | 16,78 ms | 49,51 ms | 443 ms |

Antes de encolar el refresco final pesado, el max del event loop al soltar
controles llegaba a ~0,6-1,0 s en half-size. Tras el cambio queda alrededor de
50-60 ms y el trabajo pesado aparece como preview final asincrona.

Escalado de demosaico `dcb` por procesos:

| Jobs | Workers | Tiempo total | Pico por worker |
| ---: | ---: | ---: | ---: |
| 4 | 1 | 21,31 s | ~1,52 GiB |
| 4 | 4 | 5,97 s | ~1,52 GiB |
| 8 | 8 | 7,17 s | ~1,52 GiB |

Conclusion operativa: el demosaico escala bien por procesos, pero la seleccion
automatica debe limitarse por RAM. En batch real cada worker necesita mas margen
que el demosaico aislado porque tambien genera TIFF lineal y final.

## Cambios aplicados

- Los histogramas y el panel de analisis de preview muestrean antes de convertir
  y recortar arrays grandes. Esto reduce copias temporales al trabajar con
  previews 1:1 sin tocar el render canonico.
- Las llamadas externas de diagnostico basico (`exiftool`, `git rev-parse`)
  tienen timeout para evitar bloqueos indefinidos.
- Las consultas `xicclu` de validacion y preview ICC ya operan en batch por
  `stdin`; no se detecto un bucle de una invocacion por parche.
- El batch de revelado ya no usa hilos para trabajo CPU-bound salvo fallback
  C2PA; cada imagen se procesa en un proceso independiente.
- El resultado numerico del demosaico puede persistirse como `.npy` para evitar
  repetir LibRaw cuando solo cambian ajustes posteriores.
- La escritura TIFF16 usa menos temporales intermedios que la expresion
  `round(clip(x) * 65535).astype(uint16)`.
