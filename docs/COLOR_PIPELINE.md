_Spanish version: [COLOR_PIPELINE.es.md](COLOR_PIPELINE.es.md)_

# Color Pipeline

## Operational status

The current design correctly defines the intent of the pipeline, but the
Implementation still requires closing the critical findings documented in:

- [Operational review and professionalization plan] (OPERATIVE_REVIEW_PLAN.md)

Until the P0 is completed, the pipeline must be considered suitable for prototyping and
controlled tests, not for scientific/forensic production.

## Scientific mode (profiling_mode)

Objective: neutrality and reproducibility, not aesthetics.

Rules:

1. no creative sharpen,
2. no aggressive denoise,
3. no artistic tonal curves,
4. Fixed or explicit WB,
5. linear output for profiling.

## Phases

1. `raw-info`: technical metadata.
2. `develop`: Linear controlled base development with LibRaw/rawpy for RAW inputs.
3. `detect-chart`: homography + patches.
4. `sample-chart`: Robust patch measurement.
5. `build-develop-profile`: neutrality and density from neutral card row.
6. Calibrated recipe: WB fixed, EV limited by highlight preservation,
   linear output and without creative processes.
7. Second chart measurement with the same geometry and calibrated recipe.
8. `build-profile`: ArgyllCMS (`colprof`) as a single ICC profile engine.
9. `validate-profile`: DeltaE 76/2000 of the real ICC.
10. `batch-develop`: calibrated recipe + session input ICC over RAW batch.

The complete methodology is described in
[RAW development methodology and ICC management] (METODOLOGIA_COLOR_RAW.md).

## Critical invariants1. [x] The executed recipe must match the declared recipe; are not allowed
   silent mappings of algorithms or parameters.
2. [x] The linear audit TIFF must be written before any tonal curve or
   output conversion.
3. [x] ICC management must separate:
   - input profile assignment,
   - conversion via CMM to output profile.
4. [x] Validation should check the actual generated ICC, not just artifacts
   auxiliary numbers.
5. [x] The card detection fallback should not automatically produce profiles
   without confirmation or explicit way.
6. [x] The chart geometry detected in the base pass is reused in the
   calibrated pass; it does not depend on the already corrected rendering.
7. [x] The ICC profile should not compensate exposure/base density if the chart
   allows you to build a calibrated recipe beforehand.
8. [x] If there is a session card and ICC profile, the master TIFF preserves linear RGB
   of camera/session and embeds that ICC. The standard output profiles remain
   for derivatives or non-charter flows; in the chartless flow the RAW is revealed in
   sRGB/Adobe RGB/ProPhoto RGB real, standard ICC is copied to
   `00_configuraciones/profiles/standard/` and is declared as `generic_output_icc`.
9. [x] Screen display uses a display-only conversion:
   from the working sRGB preview to the ICC profile of the configured monitor
   on the system, with sRGB only as a fallback if there is no detectable profile.

## Monitor color management

The monitor ICC profile does not participate in development, master TIFF, or
the export. It only corrects the visual representation of previews and thumbnails.

Detection policy:

- Windows: output profile associated with the screen context using
  `GetICMProfileW`.
- macOS: ColorSync space on the main display using
  `CGDisplayCopyColorSpace` and ICC data of `CGColorSpace`.
- Linux/BSD: display profile managed by `colord`/`colormgr`; if it is not
  available, fallback to `_ICC_PROFILE` from X11 when it exists.User can manually replace the monitor ICC from Settings
global > Preview / monitor. If the profile disappears or cannot be opened, NexoRAW
It records it in the log and shows the preview in sRGB so as not to block the work.

## Profile validity

The profile depends on:

- camera,
- optics,
- illuminant,
- recipe,
- software version.

Changing those factors can degrade or invalidate colorimetric validity.