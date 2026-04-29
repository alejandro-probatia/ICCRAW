_Spanish version: [CONTRIBUTING.es.md](CONTRIBUTING.es.md)_

# Contribution guide

Thank you for collaborating with ProbRAW. This project prioritizes reproducibility,
audit and traceability for scientific, forensic and heritage photography.

## Types of contributions welcome

- Code (CLI, GUI, tooling and technical documentation).
- Datasets of color charts with clear license and documentary traceability.
- Field colorimetric validations (DeltaE metrics and capture context).
- Translations and improvement of documentation for non-developer users.
- Documented use cases (scientific, forensic, heritage, teaching).
- Regulatory and legal review (metadata, chain of custody, licenses).

## Recommended flow

1. Get `fork` from the repository.
2. Create a descriptive branch (`feat/...`, `fix/...`, `docs/...`).
3. Implement the change with tests or reproducible evidence.
4. Run local checks.
5. Open a Pull Request towards `main`.
6. Attend technical and legal review before merge.

## Local environment and checks
```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
bash scripts/run_checks.sh
```
Expected checks for code contributions:

- `pytest` in green.
- Support for `black`, `ruff` and `mypy` in changed files.
- Consistency with `pyproject.toml` (Python version, extras and metadata).
- No silent changes in colorimetric output or traceability.

## Commit policy

Use semantic prefixes:

- `feat:` new capacity
- `fix:` bug fix
- `docs:` documentation
- `test:` tests
- `refactor:` refactor without functional change

Example: `docs: add colorimetric validation issue template`.

## How to add a new letter or reference

1. Document origin, license and version of the letter.
2. Add reference in `testdata/references/` or `src/iccraw/resources/references/`.
3. Includes illuminant, observer, source and version in the reference JSON.
4. Attach reproducible example (detection + sample + QA).
5. Update methodological documentation if the flow changes.

## Dataset policy

- Clear license required (`CC0`, `CC-BY` or compatible equivalent).
- Include SHA-256 checksums for each file.
- Declare origin, author, date and conditions of capture.
- Do not upload sensitive material or data with legal restrictions.

## AGPL Reminder

ProbRAW uses `AGPL-3.0-or-later`. If you run a derived version like
network service, you must publish the corresponding source code of the derivative.

## Community behavior

All participation is governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).