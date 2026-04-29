_Spanish version: [PERFORMANCE.es.md](PERFORMANCE.es.md)_

# Performance

This document includes the practical policy of performance measurement in
NexoRAW. Optimizations that affect canonical flow must preserve the
bytes of the signed TIFF unless documented as a reproducibility change.

## Tools

Granular profile of actual commands:
```powershell
python scripts/profile_pipeline.py --out-dir .\profile-out --top 80 -- batch-develop .\raws --recipe .\recipe.yml --profile .\camera.icc --out .\out --workers 1
```
The script writes:

- `profile.txt`: output of `cProfile` ordered by accumulated time.
- `profile.svg`: flamegraph of `py-spy` if installed.

To compare serial versus parallel batch, run the same command changing
only `--workers 1` for `--workers 0` or for a fixed number.

RAW Benchmark playable on Windows, macOS and Linux:
```powershell
python scripts/benchmark_raw_pipeline.py .\ruta\a\captura.NEF --out .\tmp\raw_benchmark\results.json --cache-dir .\tmp\raw_benchmark\cache --algorithms linear,dcb,amaze --cache-algorithm dcb --process-jobs 4 --process-workers 1,2,4
```
The script measures wall time, CPU, shape/dtype, array size and peak
resident memory of the process when exposed by the operating system.

GUI Fluency Benchmark:
```powershell
$env:QT_QPA_PLATFORM="offscreen"
python scripts/benchmark_gui_interaction.py --raw .\ruta\a\captura.NEF --algorithm dcb --full-resolution --out .\tmp\gui_benchmark\d850_full_ui.json
```
This test simulates real slider drags and pitch curves. Measures:

- immediate cost of `setValue`/curve point emission,
- p95/p99/max of gaps of the Qt event loop,
- time of the last interactive preview,
- pending threads at the end.

## Workers policy

`batch-develop` and the batch phase of `auto-profile-batch` accept `--workers`.

- Omitted or `0`: automatic selection based on CPU and RAM.
- `1`: serial execution for debugging and regression.
- `N > 1`: real parallelism per process, limited by the number of files.

The output remains stable because the manifest maintains the planned order
of entry, not the order of completion of the workers.

If a non-serializable Python C2PA client is injected, the batch uses threads like
conservative fallback. The normal CLI route uses processes.

Control variables:

- `NEXORAW_BATCH_WORKERS`: default workers.
- `NEXORAW_BATCH_MEMORY_RESERVE_MB`: Free RAM reserved before calculating
  automatic workers.
- `NEXORAW_BATCH_WORKER_RAM_MB`: estimated budget per worker.
  By default it is 2800 MiB, adjusted from a 45.7 MP D850: the
  DCB demosaic consumes ~1.52 GiB per process and the real batch needs margin
  additional to write linear/final TIFF.

## Numerical demosaic cache

The demo cache is opt-in. It is activated in a recipe with:
```yaml
use_cache: true
```
And it can be located from CLI with `develop`, `batch-develop` and
`auto-profile-batch`:
```powershell
python -m nexoraw batch-develop .\01_ORG --recipe .\recipe.yml --profile .\camera.icc --out .\02_DRV --cache-dir .\00_configuraciones\cache
```
If `--cache-dir` is not indicated, NexoRAW attempts to use
`00_configuraciones/cache/` of the session. If it cannot infer a session, use
`~/.nexoraw/cache/`.

The key includes full RAW SHA-256, demosaic algorithm, balance
whites, black mode and rawpy/LibRaw backend signature. Does not include settings
render that are applied after the linear scene, such as exposure or curve.

LRU pruning is controlled with `NEXORAW_DEMOSAIC_CACHE_MAX_GB` and by default
limits the cache to 5 GiB.

## Canonical Goldens

`tests/regression/` tests validate output canonical SHA-256 and TIFF
audit line. The golden force recipe `use_cache: false` so that the
regression measures canonical bytes, not cache behavior.

Intentional regeneration:
```powershell
python scripts/regenerate_golden_hashes.py --confirm --note "motivo del cambio"
```
A regeneration must be accompanied by an explanation in the changelog if the
reproducibility.

## Local benchmark D850

Equipment used: Windows 11, Python 3.12.4, 32 logical threads, RAW Nikon D850
8288x5520 of 51.5 MiB contributed locally for benchmark. RAW does not form
part of the repository.

| Case | Weather |
| --- | ---: |
| Demosaic `linear` complete | 1.52s |
| Demosaic `dcb` complete | 5.36s |
| Demosaic `amaze` complete | 5.57s |
| Cache populate `dcb` | 5.63s |
| Cache hit `dcb` | 0.16s |
| Preview half-size `dcb` | 0.85-0.88s |
| CLI `develop` no cache, audit + final TIFF | 7.24s |
| CLI `develop` with cache hit, audit + final TIFF | 1.59s |

Benchmark GUI with the same RAW, Qt `offscreen`, 80 steps per control:

| Source | Control | p95 UI event | p95 event loop | max event loop | Final preview |
| --- | --- | ---: | ---: | ---: | ---: |
| D850 half-size 2760x4144 | glitter | 0.063ms | 16.84ms | 55.32ms | 272ms |
| D850 half-size 2760x4144 | tone curve | 0.128ms | 16.87ms | 49.41ms | 434ms |
| D850 full 5520x8288 | glitter | 0.053ms | 16.72ms | 58.94ms | 275ms |
| D850 full 5520x8288 | tone curve | 0.094ms | 16.78ms | 49.51ms | 443ms |

Before queuing the final heavy refresh, the max of the event loop on release
controls reached ~0.6-1.0 s in half-size. After the change there is around
50-60 ms and the heavy lifting appears as asynchronous final preview.

`dcb` demosaic scaling by processes:

| Jobs | Workers | Total time | Peak by worker |
| ---: | ---: | ---: | ---: |
| 4 | 1 | 21.31s | ~1.52 GiB |
| 4 | 4 | 5.97s | ~1.52 GiB |
| 8 | 8 | 7.17s | ~1.52 GiB |

Operational conclusion: the demosaic scales well by processes, but the selection
automatic should be limited by RAM. In real batch each worker needs more margin
than the isolated demosaic because it also generates linear and final TIFF.

## Changes applied- Preview histograms and analysis panel downsample before converting
  and trim large arrays. This reduces temporary copies when working with
  1:1 previews without touching the canonical render.
- Basic diagnostic external calls (`exiftool`, `git rev-parse`)
  They have timeout to avoid indefinite blockages.
- The `xicclu` ICC validation and preview queries already operate in batch mode
  `stdin`; A loop of a patch invocation was not detected.
- The development batch no longer uses threads for CPU-bound work except fallback
  C2PA; each image is processed in a separate process.
- The numerical result of the demosaic can be persisted as `.npy` to avoid
  repeat LibRaw when only later settings change.
- The TIFF16 script uses fewer temporary intermediates than the expression
  `round(clip(x) * 65535).astype(uint16)`.
