_Versión en español: [COLOR_PIPELINE.es.md](COLOR_PIPELINE.es.md)_

# Color Pipeline

## Operational Status

ProbRAW 0.3.5 implements the main ICC workflow and the session-based GUI. The
application is suitable for controlled testing and release validation, but it
should not yet be presented as a certified scientific or forensic production
system.

The complete methodology is described in
[RAW development methodology and ICC management](METODOLOGIA_COLOR_RAW.md).

## Design Principle

The pipeline separates:

1. reproducible RAW development;
2. parametric development profile;
3. input ICC profile when a chart exists;
4. standard ICC profile when no chart exists;
5. CMM conversion for derivatives;
6. monitor ICC for display only;
7. audit through backpacks, manifests, Proof and optional C2PA.

DCP is not part of the active 0.3 pipeline.

## Scientific Mode (`profiling_mode`)

Objective: neutrality and reproducibility, not creative appearance.

Rules:

1. no creative sharpening during chart measurement;
2. no aggressive denoise during chart measurement;
3. no artistic tone curves;
4. fixed or explicit white balance;
5. linear output for profiling;
6. chart geometry reusable between passes.

## Phases

1. `raw-info`: read technical metadata.
2. `develop`: controlled base development with LibRaw/rawpy.
3. `detect-chart`: chart detection, homography and patches.
4. `sample-chart`: robust per-patch measurement.
5. `build-develop-profile`: neutrality, density and EV from the neutral row.
6. Calibrated recipe: fixed WB, EV limited by highlight preservation, linear
   output and no creative processing.
7. Second chart measurement with the same geometry and calibrated recipe.
8. `build-profile`: ArgyllCMS (`colprof`) generates the input ICC.
9. `validate-profile`: DeltaE 76/2000 validation of the real ICC.
10. `batch-develop`: batch rendering with assigned development profile and ICC.

Custom chart references are stored in `00_configuraciones/references/`. Each
advanced profiling run writes its artifacts under
`00_configuraciones/profile_runs/`, and resulting ICC files are registered as
activatable session profiles.

## Critical Invariants

1. The executed recipe must match the declared recipe.
2. The linear audit TIFF must be written before tone curves or output
   conversions.
3. ICC management separates input profile assignment from output profile
   conversion.
4. Validation checks the real generated ICC, not only auxiliary matrices.
5. Chart detection fallback must not generate profiles automatically without an
   explicit mode or review.
6. Chart geometry from the base pass can be reused in the calibrated pass.
7. The ICC must not compensate basic exposure/density if the chart allows a
   calibrated recipe to be built first.
8. With a chart, the master TIFF preserves linear camera/session RGB and embeds
   the input ICC.
9. Without a chart, the RAW is developed into real sRGB/Adobe RGB/ProPhoto RGB,
   a standard ICC is embedded and the output is declared `generic_output_icc`.
10. On-screen display uses a display-only conversion to the configured monitor
    ICC profile.
11. The GUI histogram and clipping overlay are computed from the colorimetric
    preview signal before applying the monitor ICC.
12. The 3D gamut diagnostic is a visual profile comparison; it does not modify
    recipes, pixels, active profiles or manifests.

## Monitor Color Management

The monitor ICC profile does not participate in development, master TIFF or
export. It only corrects the visual representation of previews and thumbnails.

Detection:

- Windows: WCS/ICM.
- macOS: ColorSync.
- Linux/BSD: `colord`, `colormgr` or `_ICC_PROFILE`.

If the profile disappears or cannot be opened, ProbRAW logs the problem and uses
sRGB as the visual fallback.

## Preview and Histogram

The GUI separates the analysis signal from the display signal:

1. The RAW is developed or previewed as normalized RGB in the image-selected
   space: linear camera RGB when a session ICC is active, or a real standard
   RGB space when using sRGB/Adobe RGB/ProPhoto RGB.
2. Parametric adjustments are applied before output conversion.
3. If a source ICC is active, pixels sent to the widget are converted directly
   from that source ICC to the configured monitor ICC.
4. The internal sRGB signal is limited to RGB histogram, clipping overlay,
   diagnostics and fallback when the CMM cannot open a profile.
5. The monitor ICC is never mixed into analysis data, recipes or exported TIFFs.

This prevents a narrow, defective or machine-specific monitor profile from
altering analysis data. At the same time, the user must calibrate the monitor
and configure the correct ICC in the operating system for the visual appearance
of the preview to be reliable.

## ICC Preview Performance Note

To avoid applying ICC profiles to embedded previews that do not represent the
developed RAW, views with a session ICC or generic profile avoid the embedded
thumbnail and use LibRaw development. Normal preview remains bounded by
`PREVIEW_AUTO_BASE_MAX_SIDE`; only 1:1 precision, compare and chart marking
force full resolution. Curve interactions use a cached reduced source and heavy
final preview runs in an asynchronous worker.

## Profile Validity

The profile depends on:

- camera;
- lens;
- illuminant;
- recipe;
- software version;
- relevant RAW pipeline configuration.

Changing those factors can degrade or invalidate colorimetric validity.
