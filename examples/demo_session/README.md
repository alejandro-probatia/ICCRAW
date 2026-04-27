_Spanish version: [README.es.md](README.es.md)_

# Playable session demo

This directory runs a full stream of `auto-profile-batch` in less than
5 minutes with artifacts included in the repository.

## What does it prove?

- Reproducible calibration pipeline per letter + session ICC profile.
- Generation of sidecars, QA report and batch manifest.
- Execution without external dataset or manual route configuration.

## Demo data source

Fixtures included in the repository are reused:

- `testdata/batch_images/session_001.tiff`
- `testdata/batch_images/session_002.tiff`
- `testdata/references/colorchecker24_colorchecker2005_d50.json`

`prepare_demo.sh` copies those files to `examples/demo_session/data/` and validates
SHA-256 vs. `data/MANIFEST.sha256`.

## Execution
```bash
bash examples/demo_session/run_demo.sh
```
## Generated artifacts

In `examples/demo_session/output/`:

- `camera_profile.icc`
- `development_profile.json`
- `recipe_calibrated.yml`
- `profile_report.json`
- `qa_session_report.json`
- `tiffs/batch_manifest.json`

`run_demo.sh` prints at the end:

- path of the generated ICC,
- DeltaE76 medium,
- DeltaE2000 medium,
- operational status of the profile,
- manifest route.

## Known limitations

- This demo uses TIFF images from the fixture, not RAW from the real camera.
- The project has yet to incorporate a licensed real RAW dataset
  explicit for regression (see `docs/ISSUES.md`, item P0.6).
- Placeholder for maintainer: `[PENDIENTE: dataset CC-BY propio de Probatia/AEICF para demo RAW real]`.