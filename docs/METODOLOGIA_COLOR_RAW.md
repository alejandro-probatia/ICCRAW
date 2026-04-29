_Versión en español: [METODOLOGIA_COLOR_RAW.es.md](METODOLOGIA_COLOR_RAW.es.md)_

# RAW Development Methodology and ICC Management

This document defines NexoRAW's methodological criteria for separating
parametric RAW development, development profiles, input ICC profiles, output ICC
profiles and monitor ICC profiles.

The current decision is to keep a scientific ICC-centered workflow. DCP
integration was evaluated as a possible future direction, but it is not active
scope for the 0.2 series because it adds complexity and can mix colorimetric
decisions with appearance decisions.

## References

- RawTherapee, `Sidecar Files - Processing Profiles`:
  https://rawpedia.rawtherapee.com/Sidecar_Files_-_Processing_Profiles
- RawTherapee, `Color Management`:
  https://rawpedia.rawtherapee.com/Color_Management
- RawTherapee, `ICC Profile Creator`:
  https://rawpedia.rawtherapee.com/ICC_Profile_Creator

## Conceptual Criterion

A RAW file is not a final RGB image. It is a capture of sensor data that must be
interpreted through a development recipe: demosaic, white balance, black level,
exposure compensation, tone curve, output space and other parameters.

In NexoRAW, the input ICC profile is not computed from the bare RAW file. It is
computed after developing a chart capture with a controlled recipe, because
measurements are made on RGB values produced by the developer. Once generated,
that ICC describes how to interpret the camera/session RGB produced by the same
recipe, camera and illuminant.

Therefore:

- the recipe corrects and documents base development;
- the development profile stores per-file parametric decisions;
- the input ICC describes the measured colorimetric response of the session;
- the output ICC describes the final space when there is no chart or when a
  converted derivative is produced;
- the monitor ICC corrects display only.

## Recommended Technical Flow

The methodological RAW contract is:

1. Open the RAW with LibRaw/rawpy.
2. Read camera model, CFA, black level, white level, as-shot white balance,
   camera matrix and embedded profile when available.
3. Normalize RAW data to linear `float32`.
4. Apply black subtraction and white normalization.
5. Apply white balance in camera space.
6. Run demosaic.
7. Produce linear camera/session RGB or develop directly to a standard space when
   there is no chart.
8. Apply documented parametric adjustments.
9. For display, convert the preview to the monitor ICC profile if enabled.
10. For export, embed the corresponding ICC and record the applied transform.

Current implementation:

- with a chart, NexoRAW preserves linear camera/session RGB and embeds the
  generated input ICC;
- without a chart, NexoRAW develops into `sRGB`, `Adobe RGB (1998)` or
  `ProPhoto RGB` and copies/embeds a real standard ICC;
- converted derivatives from a session ICC are processed through CMM/ArgyllCMS
  where applicable;
- the monitor profile never changes TIFFs, hashes, manifests or Proof data.

## Per-file Development Profile

NexoRAW 0.2 treats parametric development as a property assigned to each RAW file
through its backpack:

```text
capture.NEF
capture.NEF.nexoraw.json
```

A session can contain several development profiles. This avoids assuming that a
whole folder is homogeneous: one session may include changes in lighting, lens,
exposure or output criteria.

Types:

- **Advanced profile**: created from a color chart and optionally tied to a
  session input ICC.
- **Basic profile**: created from manual adjustments and associated with a
  standard ICC when no chart exists.

## Workflow With a Color Chart

When a valid chart capture exists:

1. Develop the chart with a base scientific recipe.
2. Detect and measure chart patches.
3. Build a development profile: white balance, density and exposure derived from
   the chart.
4. Measure the chart again with the calibrated recipe.
5. Generate the session input ICC with ArgyllCMS from measured RGB values and
   colorimetric references.
6. Save development profile, calibrated recipe, input ICC, QA reports and
   overlays separately.
7. Develop equivalent RAW files with that profile.
8. Create a master TIFF preserving camera/session RGB and embedding the input
   ICC.

The advanced profile can be copied to images captured under comparable camera,
lens, illuminant, base exposure and recipe conditions.

## Workflow Without a Color Chart

When no chart exists:

1. NexoRAW does not invent a session ICC.
2. The user saves a manual development profile.
3. The user chooses a real standard output space: `sRGB`, `Adobe RGB (1998)` or
   `ProPhoto RGB`.
4. NexoRAW develops the RAW in that space and embeds the standard ICC.
5. Traceability states that there is no measured input profile and that the
   embedded ICC is `generic_output_icc`.

This workflow is reproducible and functional, but it does not replace the
precision of a measured colorimetric reference.

## Master TIFF and Derivatives

NexoRAW distinguishes:

- **Chart-based master TIFF**: camera/session RGB, calibrated development
  profile, session input ICC, NexoRAW Proof and optional C2PA.
- **Converted derivative TIFF**: output transformed by CMM to a generic or device
  output profile.
- **Manual no-chart TIFF**: RAW developed into a real standard space, embedded
  standard ICC and per-file development backpack.

Existing outputs are not overwritten. NexoRAW creates `_v002`, `_v003`, etc.

## Backpacks and Audit

The backpack sidecar records:

- RAW identity and hash;
- applied development recipe;
- assigned development profile;
- associated ICC and hash when available;
- detail and render settings;
- latest generated TIFF outputs.

The backpack does not replace the RAW or the batch manifest. Its purpose is to
transport per-file parametric settings in an auditable and portable way.
