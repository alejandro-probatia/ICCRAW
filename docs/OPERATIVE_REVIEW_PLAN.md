_Spanish version: [OPERATIVE_REVIEW_PLAN.es.md](OPERATIVE_REVIEW_PLAN.es.md)_

# Operational review and professionalization plan

Revision date: 2026-04-24.

Status: Governing document to convert the current prototype into a tool
operational, auditable and suitable for scientific validation.

Status Note 0.2: Several P0/P1 findings from this patch are now mitigated
or implemented in the current branch. This document is kept as a record
methodological and contrast plan; summary operating status lives in
`docs/ISSUES.md`, `docs/COLOR_PIPELINE.md` and `CHANGELOG.md`.

## 1. Scope

This document includes the technical findings detected in the review of the
ProbRAW project and defines a structured work plan to implement the
professional corrections.

The goal is not to turn the project into a generalist photo editor.
The goal is a controlled pipeline for capture, RAW development, ICC profiling,
batch application, colorimetric validation and traceability for scientific use,
documentary and forensic.

## 2. Executive summary

ProbRAW already has a reasonable foundation:

- modular Python architecture,
- Functional CLI,
- initial GUI,
- reproducible recipes,
- integration with LibRaw/rawpy, `exiftool` and ArgyllCMS,
- JSON sidecars and batch manifests,
- initial unit tests.

But the project should not yet be considered operational in scientific production.
The main blockages are in:

1. insufficiently strict RAW development contract,
2. ICC color management not aligned with a standard CMM flow,
3. validation that does not actually check the generated ICC profile,
4. detection of too permissive card,
5. recipes that declare parameters that the code does not apply,
6. absence of real RAW dataset for regression.

The priority is to close these points before extending GUIs, automations or
advanced features.

## 3. Technical references and standards

The development must align, at a minimum, with these references:
- ISO 17321-1:2012: color characterization of digital cameras.
  https://www.iso.org/standard/56537.html
- ISO 12234-4:2026: Digital Negative (DNG), open/normalized RAW format.
  https://www.iso.org/standard/86123.html
- ICC v4.4 / ISO 15076: architecture and format of ICC profiles.
  https://color.org/index.xalter
- ISO/CIE 11664-4:2019: CIE 1976 L*a*b*.
  https://www.iso.org/standard/74166.html
- CIE 199:2011: CIELAB/CIEDE2000 recommendation for color differences.
  https://www.cie.co.at/publications/methods-evaluating-colour-differences-images
- ISO 15739:2023: noise and dynamic range in digital cameras.
  https://www.iso.org/standard/82233.html
- ISO 17957:2015: shading measurement in digital cameras.
  https://www.iso.org/standard/31974.html
- EMVA 1288 Release 4.0: objective characterization of cameras/sensors.
  https://www.emva.org/news/new-release-4-0-of-emva-1288-standard-for-camera-characterization-in-effect/
- ArgyllCMS `colprof`: generation of profiles from card values.
  https://argyllcms.com/doc/colprof.html

## 4. Technical findings

### H-001 Non-standard ICC management in batch output

Criticality: criticism.

Implementation status:

- mitigation implemented: batch export now separates RGB from camera
  with embedded input profile and conversion to sRGB using ArgyllCMS
  (`cctiff`).
- pending: broader external cross-validation of real ICC profiles.

Situation detected in the initial review:

- `batch_develop` reveals to linear TIFF, applies own matrix
  `camera_to_xyz -> sRGB` and then embeds the generated ICC.
- This mixes two different concepts:
  - assign an input profile to camera RGB data,
  - convert data to an output space using a CMM.

Local evidence:

- `src/probraw/profile/export.py`: `batch_develop` and `apply_profile_matrix`.
- `src/probraw/profile/builder.py`: calculation of `matrix_camera_to_xyz` and sidecar
  `.profile.json`.

Risk:

- double conversion,
- uncontrolled clipping,
- TIFF that declares a profile that does not actually describe its pixels,
- different results depending on external application.

Technical address:

1. Define two explicit modes:
   - `assign-input-profile`: TIFF in RGB camera + embedded input ICC profile.
   - `convert-to-output-profile`: transformation with real CMM to sRGB/AdobeRGB/XYZ/Lab.
2. Integrate a real CMM for ICC conversions:
   - ArgyllCMS (`cctiff`/`xicclu`) to maintain a single external CMM provider.
3. Eliminate the silent application of the side array as the main output.
4. Keep the matrix only as a diagnostic artifact, not as a substitute for the ICC.

Acceptance criteria:
- a TIFF converted to sRGB declares sRGB profile, not camera profile,
- a TIFF in RGB camera declares camera profile and has not been transformed,
- tests compare ICC transformation with external reference tool,
- the manifest declares the color management mode used.

### H-002 RAW Recipe declares algorithms not supported by the backend

Criticality: criticism.

Implementation status:

- mitigated: the project uses LibRaw/rawpy as the only RAW backend, recipes
  example with `demosaic_algorithm: dcb` and strict validation.

Situation detected in the initial review:

- The example recipe used `demosaic_algorithm: rcd`.
- The code silently mapped unsupported names to another algorithm.

Local evidence:

- `testdata/recipes/scientific_recipe.yml`: scientific recipe.
- `src/probraw/raw/pipeline.py`: `LIBRAW_DEMOSAIC_MAP` validation.

Risk:

- Traceability says that RCD was used, but AHD was actually used,
- a demosaicing change invalidates colorimetric comparisons,
- there is no early failure when the recipe is not executable.

Technical address:

1. Replace silent mappings with strict validation.
2. Enter `effective_recipe` or `execution_contract` in sidecars.
3. Keep LibRaw/rawpy as a single backend and extend only supported algorithms
   for that engine.

Acceptance criteria:

- recipe with unsupported algorithm fails before processing,
- sidecar records real command and effective parameters,
- tests cover valid and invalid recipes per backend.

### H-003 `audit_linear_tiff` may not be linear

Criticality: high.

Implementation status:

- mitigated: `audit_linear_tiff` is written before exposure compensation and
  exit curves.

Situation detected in the initial review:

- The audit TIFF is written after applying exposure compensation and
  possible tonal curve.

Local evidence:

- `src/probraw/raw/pipeline.py`: `develop_controlled`.

Risk:

- the artifact called "linear" does not guarantee scene/sensor linearity,
- does not serve as reliable intermediate evidence.

Technical address:
1. Separate internal states:
   - `developed_scene_linear`,
   - `rendered_output`,
   - `profiled_output`.
2. Write `audit_linear_tiff` immediately after linear development and before
   of curves, OETF or output conversion.
3. Record in metadata if WB, black/white level, demosaicing and
   normalization.

Acceptance criteria:

- test with `tone_curve: srgb` shows that `audit_linear_tiff` does not change,
- filename and sidecar clearly describe each state,
- there is no tonal curve in `profiling_mode` mode.

### H-004 Validation based on lateral matrix, not on real ICC profile

Criticality: high.

Implementation status:

- mitigated: `validate-profile` queries actual ICC with ArgyllCMS (`xicclu` or
  `icclu`) and no longer depends on the sidecar matrix `.profile.json`.
- pending: formally separate training and validation samples when
  There is sufficient real capture dataset.

Situation detected in the initial review:

- `validate-profile` loads `.profile.json` and applies the own matrix.
- Does not validate the ICC transformation generated by `colprof`.
- It does not require separating training and validation samples.

Local evidence:

- `src/probraw/profile/builder.py`: `validate_profile`.
- `src/probraw/profile/builder.py`: `_build_profile_with_argyll`.

Risk:

- optimistic or non-representative DeltaE metrics,
- the ICC may be invalid even if the lateral matrix appears acceptable,
- there is no generalization control between captures.

Technical address:

1. Validate the actual ICC with CMM/ArgyllCMS, not just the lateral matrix.
2. Separate:
   - `fit_report`: errors on samples used to build profile,
   - `validation_report`: errors about independent captures.
3. Register DeltaE76 and DeltaE2000, in addition to outliers per patch.
4. Define thresholds by use case and letter type.

Acceptance criteria:

- validation fails if the ICC is missing even if there is a sidecar,
- cross validation uses captures not included in construction,
- report includes mean, median, p95, maximum and patches out of tolerance.

### H-005 Too permissive card detection

Criticality: high.

Implementation status:
- mitigated: fallback detection is marked as `detection_mode=fallback`,
  It has maximum confidence 0.05 and `valid_patch_ratio=0.0`.
- mitigated: `auto-profile-batch` and automatic profile generation reject
  default fallback; It is only accepted with explicit opt-in.
- mitigated: automatic detection incorporates adjustment by internal pattern of
  ColorChecker24 patches, validated with two real Pixel 6a DNGs.
- mitigated: `detect-chart --manual-corners` allows marking four corners and
  generate `detection.json` reviewable with overlay.
- mitigated: GUI allows marking four points in the viewer and saving one
  manual detection with overlay.
- pending: link saved manual detections with each capture within the
  Automatic batch flow.

Situation detected in the initial review:

- If no contour is detected, a fallback bbox is used.
- That fallback can return high confidence if the apparent geometry fits.

Local evidence:

- `src/probraw/chart/detection.py`: `detect_chart` and `_confidence_score`.
- Observed in smoke test: fallback warning with `confidence_score: 1.0`.

Risk:

- sampling of incorrect areas,
- profile built with wrong samples,
- apparently valid but scientifically invalid results.

Technical address:

1. Geometric fallback must have low confidence or require manual confirmation.
2. `auto-profile-batch` should not accept fallback without explicit opt-in.
3. Detection must incorporate orientation, patch layout and coherence checks
   chromaticity/luminance.
4. Add manual assisted mode for letter corners.
5. Add patch pattern detector for Passport cards or scenes with
   ambiguous outer contour.

Acceptance criteria:

- fallback does not exceed `min_confidence` by default,
- report brand `detection_mode: automatic|manual|fallback`,
- overlay and JSON include blocking warnings where appropriate.
- two real DNGs with ColorChecker Passport detect the bottom card
  Automatic with high confidence.

### H-005b Scientific development profile prior to the ICC

Criticality: high.

Implementation status:
- mitigated: `build-develop-profile` calculates fixed WB and EV compensation from the
  neutral row of the card.
- mitigated: EV compensation is limited by preserving highlights of the
  letter to avoid clipping.
- mitigated: `auto-profile-batch` executes double pass:
  base recipe -> development profile -> calibrated recipe -> ICC.
- mitigated: the detected geometry is reused in the calibrated pass so that
  sampling does not depend on rendering.

Risk:

- if the ICC absorbs exposure, density or neutrality errors, the profile
  It stops describing only the chromatic response of camera + illuminant.

Technical address:

1. Separate development profile and ICC profile as different artifacts.
2. Use card to normalize neutrality and density before outlining.
3. Keep local sharpness/contrast as a measurable QA, not a creative adjustment.

### H-006 Recipe parameters ignored by sampling

Criticality: medium.

Implementation status:

- mitigated: `sampling_trim_percent` and `sampling_reject_saturated` are loaded from
  YAML/JSON recipes and are applied in sampling.
- pending: configurable patch margin and advanced exclusion criteria.

Situation detected in the initial review:

- The recipe declares `trim_percent` and `reject_saturated`.
- The code normalizes `sampling_strategy` to a string and uses fixed `0.1`.

Local evidence:

- `testdata/recipes/scientific_recipe.yml`: `sampling_strategy` block.
- `src/probraw/core/recipe.py`: `_normalize_recipe_payload`.
- `src/probraw/chart/sampling.py`: `_sample_patch`.

Risk:

- the operator believes he controls the sampling, but the code does not obey,
- Reproducibility and auditability are reduced.

Technical address:

1. Model `sampling_strategy` as a structure, not just a string.
2. Apply `trim_percent`, `reject_saturated`, patch margin and criteria
   exclusion from prescription.
3. Record effective parameters per patch.

Acceptance criteria:

- tests show that changing `trim_percent` changes the result,
- sample sidecar includes effective parameters,
- invalid recipe fails with clear message.

### H-007 Insufficiently typed chart and observer references

Criticality: medium.

Implementation status:
- mitigated: `ReferenceCatalog.from_path()` validates required metadata,
  illuminant D50, observer 2 degrees, reference source, patch ids and
  Lab values.
- pending: support documented chromatic adaptation for non-D50 references
  if you decide to expand the pipeline.

Situation detected in the initial review:

- The catalog reads `observer`, but the profiling internally sets D50.
- It is not validated that `reference_lab` corresponds to the expected illuminant/observer.

Local evidence:

- `src/probraw/chart/sampling.py`: `ReferenceCatalog`.
- `src/probraw/profile/builder.py`: `D50_XYZ`.

Risk:

- unintentional mixing of references D50/D65 or observer 2/10 degrees,
- DeltaE not comparable between sessions.

Technical address:

1. Type reference catalog with illuminant, observer, source and version.
2. Validate compatibility between reference, recipe and session lighting.
3. Support documented chromatic adaptation if non-D50 references are accepted.

Acceptance criteria:

- reference without illuminant/observer fails in strict mode,
- report includes reference source/version,
- tests cover D50 compatible and reference incompatible.

### H-008 Real RAW dataset missing for regression

Criticality: critical for production, high for development.

Situation:

- The current files `testdata/raw/*.nef` and `*.cr3` are text markers.
- The tests do not exercise real RAW development.

Local evidence:

- `testdata/raw/mock_capture.nef`.
- `testdata/raw/batch/session_001.nef`.
- `testdata/raw/batch/session_002.cr3`.
- `tests/test_pipeline_libraw.py` covers LibRaw parameter contract; missing
  Real RAW dataset for integration.

Risk:

- Green IC without covering the most important point of the project,
- incompatibilities with real cameras detected late,
- determinism cannot be measured between versions.

Technical address:

1. Create minimum dataset with real DNG/NEF/CR2/ARW, clear license and size
   controlled.
2. Keep small subset in repo or download it to CI with checksum.
3. Separate unit tests, smoke and heavy integration.

Acceptance criteria:

- at least one test reveals a real RAW/DNG with external tools,
- output checksums are stable under defined tolerance,
- CI distinguishes tests that require real RAW/`colprof`.

## 5. Professional work plan

### Phase 0 - Closing of technical contract
Objective:

- convert implicit decisions into verifiable execution contracts.

Deliverables:

1. Pipeline contract document:
   - image states,
   - color spaces,
   - use of ICC,
   - intermediate artifacts,
   - scientific invariants.
2. ADRs for:
   - primary RAW backend,
   - CMM motor,
   - ICC profile policy,
   - DeltaE validation policy.
3. Recipe compatibility table per backend.

Exit criteria:

- no critical function accepts parameters that it cannot execute faithfully.

### Phase 1 - P0 RAW and traceability

Objective:

- ensure that the development carried out coincides exactly with what was declared.

Tasks:

1. Strict recipe validation.
2. Registration of effective LibRaw parameters and external versions.
3. Separation of `audit_linear_tiff` and rendered output.
4. Valid/invalid recipe tests.
5. Minimum real RAW dataset.

Exit criteria:

- the pipeline fails early due to unsupported configuration and generates sidecars
  enough to repeat the execution.

### Phase 2 - P0 ICC management and batch output

Objective:

- align the output with an interoperable ICC stream.

Tasks:

1. Define output modes:
   - `camera_rgb_with_input_icc`,
   - `converted_srgb`,
   - `converted_xyz_or_lab` if scientifically justified.
2. Integrate real CMM.
3. Replace matrix application with validated ICC transformation.
4. Validate profiles with external tools (`iccdump`, ArgyllCMS).
5. Document final TIFF behavior.

Exit criteria:

- any exported TIFF can be opened in color-managed software and its profile
  correctly describes the pixels.

### Phase 3 - P1 letter, sampling and capture QA

Objective:

- prevent a bad detection or sample from producing an apparently valid profile.

Tasks:

1. Reduce fallback confidence and make it blocking by default.
2. Add manual assisted mode for letter corners.
3. Apply real sampling parameters from recipe.
4. Detect saturation, low level, non-uniformity and irregular lighting.
5. Report outliers by patch and reason for exclusion.

Exit criteria:

- a poor capture produces a clear diagnosis and does not generate a profile without
  explicit confirmation.### Phase 4 - P1 colorimetric validation

Objective:

- separate construction, validation and usability of the profile.

Tasks:

1. Split samples: training/validation.
2. Validation of the real ICC using CMM.
3. DeltaE thresholds by discipline or preset.
4. Comparable reports between sessions.
5. Stability tests between repeated runs.

Exit criteria:

- a profile has status `draft`, `validated`, `rejected` or `expired`, with
  auditable reasons.

### Phase 5 - P2 reproducibility, CI and distribution

Objective:

- make the behavior sustainable by the community.

Tasks:

1. CI with arrays:
   -unit,
   - integration-with-tools,
   - optional-gui-smoke.
2. Version checks of external tools.
3. Container or reproducible environment for validation.
4. Determinism and performance benchmark.
5. License audit before releases.

Exit criteria:

- a release can be rebuilt, tested and audited with clear instructions.

### Phase 6 - P3 controlled expansion

Objective:

- expand capacities without compromising traceability.

Tasks:

1. Full IT8 support.
2. LUT profiles if the use case warrants it.
3. Profile comparator between sessions/illuminants.
4. C2PA/CAI for chain of custody.
5. Internationalization and presets by discipline.

Exit criteria:

- advanced functions inherit the same validation and auditing contract.

## 6. Definition of "fact"

A critical task is considered completed only if it meets:

1. code implemented with unit tests,
2. smoke test CLI documented,
3. updated sidecars/manifests,
4. updated user or technical documentation,
5. entry in `CHANGELOG.md`,
6. impact on reproducibility evaluated,
7. does not introduce silent changes in colorimetric output.

## 7. Minimum operational criteria

The project could be considered "operational for controlled scientific tests"
when you meet:
1. Real RAW development tested with minimal dataset,
2. strict recipes without silent mappings,
3. truly linear TIFF audit,
4. Interoperable ICC output,
5. validation of the real ICC,
6. default blocking card fallback,
7. DeltaE reports with thresholds and outliers,
8. Batch manifest with hashes, versions, profile and color mode.

It should not be considered "validated for forensic production" until it also has
with:

1. approved capture protocol,
2. multi-chamber regression dataset,
3. independent validation by laboratory or technical community,
4. documented chain of custody,
5. Version control of profiles and recipes per session.

## 8. Recommended order of implementation

1. Strict recipe validation and elimination of silent mappings.
2. Correction of `audit_linear_tiff`.
3. Separation of ICC modes in batch.
4. Real CMM integration.
5. Validation of the real ICC.
6. Card fallback blocking.
7. Complete sampling parameters.
8. Real RAW Dataset and Integration CI.
9. Quality reports per session.
10. C2PA/CAI and reproducible packaging.

## 9. Main risks

1. RAW Compatibility:
   - LibRaw/rawpy covers more modern formats, but may vary between versions.
   - Mitigation: register LibRaw/rawpy version and use RAW regression dataset.
2. ICC Interoperability:
   - Not all consumers interpret entry profiles in the same way.
   - Mitigation: validate with ArgyllCMS and reference TIFFs.
3. Reference data:
   - Charts age, references change and metrology may not be drawn.
   - Mitigation: version references and register source/spectrophotometer.
4. Forensic use:
   - A technical tool is not enough without a capture and custody protocol.
   - Mitigation: document procedure and separate technical result from opinion.

## 10. State of testing observed in this review

Local environment:

- `rawpy`/LibRaw: available in development environment.
- `colprof 3.1.0`: available.
- `exiftool 12.76`: available.
- Python tests in `.venv`: `21 passed`.

Smoke test with synthetic TIFF:
- detection, sampling, build-profile, validate-profile and batch-develop run,
- the ICC profile is generated with ArgyllCMS,
- the final TIFF embeds ICC,
- It is observed that the lateral matrix can produce clipping and that the fallback of
  detection can return confidence too high.

Important limitation:

- it has not been validated with real RAW because the RAWs of `testdata/raw` are files
  placeholder text.