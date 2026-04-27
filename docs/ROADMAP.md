_Spanish version: [ROADMAP.es.md](ROADMAP.es.md)_

# Roadmap

Governing document of the operational plan:

- [Operational review and professionalization plan] (OPERATIVE_REVIEW_PLAN.md)

## Phase 0 (completed)

- modular Python base,
- Functional MVP CLI,
- reproducible pipeline with recipe,
- initial tests,
- JSON traceability,
- Initial Qt GUI for technical preview and automatic flow.
- installable Linux package with name NexoRAW, icon and own launchers.

## Phase 1 - RAW Contract and traceability (P0)

Objective: ensure that what was executed exactly matches what was declared.

- strict validation of recipes,
- removal of silent demosaicing mappings,
- effective command log and external versions,
- correction of `audit_linear_tiff` to be truly linear,
- Minimum real RAW dataset for regression.

## Phase 2 - Interoperable ICC Management (P0)

Objective: separate colorimetric conversion profile assignment.

- explicit output modes:
  - RGB camera with input profile,
  - conversion to output space using CMM,
- real CMM integration,
- replacement of lateral matrix as main output,
- external validation of ICC profiles,
- batch manifest with color management mode.

## Phase 3 – Letter, Sampling and Capture QA (P1)

Objective: Prevent faulty detections or samples from generating profiles
apparently valid.

- default blocking card fallback,
- automatic detection by internal ColorChecker24 patch pattern,
- Assisted manual mode for chart corners in CLI and GUI,
- ColorChecker 2005 D50 reference for operational use,
- scientific development profile derived from neutral row: WB, density and EV,
- double pass letter -> calibrated recipe -> ICC,
- GUI flow per file: adjust/apply, generate advanced profile with chart,
  save basic profile, copy/paste settings between thumbnails,
- complete sampling parameters from recipe,
- saturation detection, low level and estimation of irregular lighting,
- outlier reports per patch in session QA,
- Integration of manual detections by capture in the automatic batch flow.

## Phase 4 - Colorimetric validation (P1)

Objective: validate the real ICC and the suitability of the profile for a session.- training/validation separation,
- validation with CMM/ArgyllCMS of the generated ICC profile,
- QA session report with status `validated`, `rejected` or `not_validated`,
- DeltaE thresholds by discipline or preset,
- profile operational states: `draft`, `validated`, `rejected`, `expired`,
- Comparable reports between sessions using CLI/GUI.

## Phase 5 - Reproducibility, CI and distribution (P2)

Objective: make the behavior sustainable by the community.

- CI with unit tests and integration with external tools,
- LibRaw/rawpy, ArgyllCMS and `exiftool` version checks using
  CLI/GUI,
- reproducible Debian package for local installation,
- reproducible container or environment,
- determinism and performance benchmarks,
- RAW browsing benchmarks, persistent thumbnail cache and cache
  optional full previews,
- license audit for AGPL releases.

## Phase 6 - Controlled expansion (P3)

Objective: expand capacities without compromising traceability.

- sidecars per image to separate global session settings and settings
  capture particulars, with own JSON backpacks and possible
  future interoperability with `.pp3`,
- full IT8 support,
- LUT profiles if the use case justifies it,
- automatic profile comparator between sessions/illuminants,
- C2PA/CAI for chain of custody,
- GUI internationalization (es/en) and technical presets by discipline.