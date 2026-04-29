_Spanish version: [REPRODUCIBILITY.es.md](REPRODUCIBILITY.es.md)_

# Reproducibility

ProbRAW separates three levels:

- Original RAW: never modified.
- Linear scene: numerical output after LibRaw/demosaic/WB/black.
- Final render: exposure, curve, color management, signature and tests.

## Tests golden

The canonical cases are in `testdata/regression/MANIFEST.json`.
Each case states:

- entrance,
- recipe,
- SHA-256 of the final TIFF,
- SHA-256 linear TIFF audit.

The `tests/regression/test_canonical_hashes.py` test reveals each case in a
temporary directory and compare hashes byte by byte.

## Regenerate hashes

This should only be done when an algorithm or dependency change modifies the
output intentionally:
```powershell
python scripts/regenerate_golden_hashes.py --confirm --note "descripcion breve"
```
The script disables `use_cache` before revealing, updates the manifest, and adds
an entry in `tests/regression/golden/REGENERATION_LOG.md`.

## Cache and reproducibility

The demo cache stores `.npy` linear scene arrays for performance.
It is opt-in and its key contains the complete SHA-256 of the RAW and the parameters that
affect LibRaw. Golden tests do not use cache to avoid false positives
of infrastructure.