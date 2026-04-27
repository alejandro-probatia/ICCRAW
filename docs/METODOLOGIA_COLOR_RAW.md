_Spanish version: [METODOLOGIA_COLOR_RAW.es.md](METODOLOGIA_COLOR_RAW.es.md)_

# RAW development methodology and ICC management

This document establishes the methodological criteria of NexoRAW to separate revealed
parametric, session entry profile and exit profiles. The decision is
draws inspiration from established RAW developer streams like RawTherapee, tailored to
technical, scientific and forensic objective of the project.

## References consulted

- RawTherapee, `Sidecar Files - Processing Profiles`:
  https://rawpedia.rawtherapee.com/Sidecar_Files_-_Processing_Profiles
- RawTherapee, `Color Management`:
  https://rawpedia.rawtherapee.com/Color_Management
- RawTherapee, `How to create DCP color profiles`:
  https://rawpedia.rawtherapee.com/How_to_create_DCP_color_profiles
- RawTherapee, `ICC Profile Creator`:
  https://rawpedia.rawtherapee.com/ICC_Profile_Creator

## Conceptual criterion

A RAW is not a final RGB image. It is a capture of sensor data that must
be interpreted through a development recipe: demosaicing, balance of
whites, black level, exposure compensation, tone curve, workspace
and other parameters. In RawTherapee this persistent recipe is called
`processing profile` and is saved as a sidecar associated with the image.

The ICC or DCP camera profile is not calculated on the bare RAW. It is calculated
after revealing a card capture with a controlled recipe, because the
Measurements are made on RGB values already produced by the developer. Without
However, once generated, that profile describes how to interpret the RGB of
camera/session produced by that same recipe, camera and illuminant. Therefore,
in NexoRAW it is treated as **session entry profile**, not as a generic profile
exit.

RawTherapee separates three classes: input profile, screen profile and profile
exit. The output profile is used when saving a transformed image to
a target space such as sRGB, a wide space, or a printer profile. that
This step should not be confused with assigning the session's own profile to the RGB that
It is still in camera/session domain.

## Recommended technical color flow

The methodological contract for RAW is:
1. Open the RAW with LibRaw.
2. Read camera model, CFA, black level, white level, white balance as-shot,
   camera matrix and embedded profile when they exist.
3. Normalize RAW data to linear `float32`.
4. Apply black subtraction and white normalization.
5. Apply white balance in camera space.
6. Run demosaicing.
7. Convert Camera RGB to XYZ with the corresponding profile/matrix.
8. Apply chromatic adaptation if applicable.
9. Convert XYZ to linear workspace.
10. Perform the edition in a large linear space.
11. For screen, transform from preview RGB to monitor ICC using
    LittleCMS/ImageCms.
12. For export, transform to the output profile, embed the ICC and
    record the transformation applied.

Current implementation: steps 1 to 8 are delegated to LibRaw/rawpy when
choose a standard space without a letter (`sRGB`, `Adobe RGB (1998)` or
`ProPhoto RGB`). When session ICC exists, NexoRAW preserves the linear RGB of
camera/session and embed that ICC as an input profile; output conversion
It is then done using CMM/ArgyllCMS (`cctiff`) in derivatives. This distinction
is recorded in `render_settings.color_management.raw_color_pipeline` within
NexoRAW Proof/C2PA.

In NexoRAW 0.2, the parametric fit is considered a property assigned to a
RAW concrete using your `RAW.nexoraw.json` backpack. A session can have
Various adjustment profiles: some advanced, born from color chart, and others
basic, born from manual adjustments. The user can copy the profile from
a thumbnail and paste it on other images taken under comparable conditions.

This avoids a methodological problem: a session is not always homogeneous. can
contain multiple illuminations, objectives, exposures or exit criteria. The
single global profile is replaced by profiles per image, reusable and
traceable.

## Flow with color chart

When there is a valid letter capture:
1. Reveal the letter with a basic scientific recipe.
2. Detect and measure patches on the chart.
3. Generate a session development profile: white balance, density and
   reproducible parameters derived from the chart.
4. Re-reveal/measure the card with that calibrated recipe.
5. Generate the session input ICC with ArgyllCMS from those RGB
   calibrated and colorimetric references.
6. Save separately:
   - NexoRAW development profile,
   - calibrated recipe,
   - ICC session input,
   - QA and validation reports.
7. Develop the RAW of the session with the calibrated recipe.
8. Create the master TIFF keeping camera/session linear RGB and embedding
   the ICC of the session.

In the GUI, the RAW used as a card is marked in blue because it contains a
advanced profile. That profile can be copied and pasted into other thumbnails. The
validity of that copy depends on which camera, optics, illuminant, base exposure
and RAW criteria are comparable.

The TIFF master is not converted to sRGB, AdobeRGB, or ProPhoto when there is ICC of
session. Doing so at this stage would mix two different operations and could
introduce double conversions or unnecessary loss of information.

## Flow without color chart

When there is no letter:

1. A session ICC is not invented.
2. It is allowed to save a manual development profile with the defined parameters
   by the user.
3. User can choose a standard output RGB space: sRGB, Adobe RGB
   (1998) or ProPhoto RGB. NexoRAW reveals the RAW directly in that space with
   LibRaw and copy/embed a real standard ICC profile from the system or from ArgyllCMS.
4. Traceability must state that there is no measured input profile and that the
   Embedded ICC is a `generic_output_icc`.

In the GUI, the RAW is marked green because it contains a basic profile. that
Profile can also be copied and pasted into other images. It is an operational flow
and reproducible, but it does not have the same colorimetric strength as a profile
advanced with letter.

## TIFF master and derivatives

NexoRAW distinguishes two types of output:
- **Session master TIFF**: camera/session RGB, calibrated recipe, ICC
  Embedded session input, NexoRAW Proof and optional C2PA.
- **Interchange derived TIFF**: converted using CMM from the ICC of
  session to a generic or device output profile, with that output profile
  embedded output.
- **Manual TIFF without card**: parametric recipe defined by the user,
  NexoRAW backpack per file, RAW developed in real sRGB/Adobe RGB/ProPhoto RGB
  and embedded standard ICC. This flow is functional, but does not replace the
  precision of a colorimetric chart.

The current version implements the session master TIFF as the preferred output
when there is a letter. For sessions without a card it implements sRGB, Adobe RGB (1998) and
ProPhoto RGB as actual output standard profiles; when there is ICC of
session input, those outputs are treated as derivatives converted by CMM.

## Sidecars backpack

Each RAW can carry a NexoRAW sidecar next to the original file:
```text
captura.NEF
captura.NEF.nexoraw.json
```
The sidecar records:

- RAW identity and hash,
- developing recipe applied,
- assigned session development profile,
- ICC of associated session and hash,
- detail and render settings,
- last TIFF outputs generated.

This file does not replace the RAW or batch manifest. Its function is
transport the development parametric parameters per file, so
equivalent to the RawTherapee PP3 practical paper, but using a scheme
NexoRAW's own auditable JSON.

The backpack is also the contract that allows a session to be moved between teams. Yes
the relative structure is maintained, another person can open the folder,
recover thumbnails/cache and know what settings were assigned to each RAW without
depend on the internal state of the application.