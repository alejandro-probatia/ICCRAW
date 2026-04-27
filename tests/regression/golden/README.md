_Spanish version: [README.es.md](README.es.md)_

# Golden hashes

These cases set SHA-256 hashes of the canonical TIFF and the linear TIFF of
audit to detect accidental changes in reproducible output.

The current inputs use synthetic TIFFs versioned in `testdata/` so that
The test is lightweight and does not depend on heavy proprietary RAW. The recipes have
`use_cache: false` to always validate the calculation path, not an artifact
searched

To regenerate hashes after an intentional change of number engine:
```powershell
python scripts/regenerate_golden_hashes.py --confirm
```
