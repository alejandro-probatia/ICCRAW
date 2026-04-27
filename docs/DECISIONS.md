_Spanish version: [DECISIONS.es.md](DECISIONS.es.md)_

# Technical Decisions

## DEC-0001: Core Core Language

- Status: accepted
- Date: 2026-04-23

Decision:

- use **Python** as the main core language and CLI to maximize community maintainability and scientific iteration speed.

Motivation:

1. mature scientific ecosystem,
2. lower contribution barrier,
3. direct integration with vision/colorimetry tooling.

## DEC-0002: ICC Profile Engine

- Status: accepted
- Date: 2026-04-23

Decision:

- ICC profile build engine: **ArgyllCMS** (`colprof`) as the only supported backend.

Motivation:

1. ArgyllCMS is consolidated technical reference,
2. allows external validation/contrast,
3. avoids divergences between engines and improves reproducibility between environments.

## DEC-0003: Image and RAW dependencies

- Status: accepted
- Date: 2026-04-23

Decision:

- LibRaw using `rawpy` as the sole RAW development engine,
- `opencv-python-headless` for geometric detection,
- `tifffile` for export TIFF 16-bit,
- `colour-science` for metrics and colorimetric conversions.

## DEC-0004: Initial license

- Status: accepted
- Date: 2026-04-23

Decision:

- repository license: `AGPL-3.0-or-later`.
- governance and maintenance: community of the **Spanish Association of Scientific and Forensic Image**.

Compatibility (summary):

1. LibRaw is integrated using `rawpy`; ArgyllCMS is used as an external tool for ICC profiling, validation and conversion,
2. OpenCV BSD: supported,
3. `rawpy` becomes a critical dependency of the RAW pipeline.

Compliance (summary):

1. all distribution of the software must include access to the corresponding source under AGPL,
2. in remote network/application deployments, the AGPL obligation to offer source to the remote user is maintained,
3. Traceability of external tools and their versions is preserved in the execution context.

## DEC-0005: Graphical interface stack

- Status: accepted
- Date: 2026-04-23

Decision:

- use **Qt for Python (PySide6)** for the GUI.

Motivation:
1. greater medium-term maintainability for complex technical interface,
2. good performance in image visualization and analysis tools,
3. LGPLv3/GPLv3 community license with good fit into the project's AGPL ecosystem.

## DEC-0006: Non-commercial objective and free license

- Status: accepted
- Date: 2026-04-23

Decision:

- maintain `AGPL-3.0-or-later` as the repository license,
- Explicitly declare that the governance objective of the project is scientific/community without commercial purpose.

Motivation:

1. The AGPL protects the reciprocity of network improvements and use,
2. adding "non-commercial only" clauses would break open source compatibility and scientific reuse,
3. Legal security and compatibility with free dependencies are prioritized.

## DEC-0007: AMaZE and GPL3 demosaic packs

- Status: accepted
- Date: 2026-04-25

Decision:

- maintain `AGPL-3.0-or-later` as the repository license,
- allow AMaZE when the `rawpy` backend is supported by LibRaw with
  `DEMOSAIC_PACK_GPL3=True`,
- document `rawpy-demosaic` as recommended backend for GPL3 builds,
- do not activate or announce AMaZE if the installed build does not include the GPL3 pack.

Motivation:

1. LibRaw's GPL3 demosaic pack requires GPL3+ for the resulting product,
2. the project's AGPL is compatible with GPL3+ and maintains community reciprocity,
3. Forensic traceability requires recording the exact backend and its flags,
4. GUI should avoid interactive crashes when an old recipe asks for AMaZE
   in an environment without GPL3 support.

## DEC-0008: RAW browsing performance and preview cache

- Status: accepted
- Date: 2026-04-26

Decision:
- treat thumbnails, navigation preview and colorimetric development as three
  different levels of cost and fidelity,
- generate RAW thumbnails from the embedded JPEG whenever it exists,
- do not run massive RAW demosaic to populate the browser with thumbnails,
- save thumbnails and browsing previews to a persistent cache inside
  of the session when the file belongs to the project, with user cache
  as a backup when there is no active session,
- use keys relative to the session root so that an exported session can
  reuse cache on another route or device,
- limit initial work to small batches and preload more thumbnails only
  when the user approaches the end of the view,
- use quick RAW preview by default for interactive navigation,
- reserve full development for explicit loading or for flows where the
  colorimetric fidelity is necessary.

Motivation:

1. RawTherapee creates the initial thumbnails from the embedded JPEG and the
   reuses from cache on subsequent openings of a folder.
2. darktable separates primary cache in memory and secondary backend on disk, and
   allows you to extract embedded JPEGs to speed up the first contact with a
   collection.
3. In folders with many RAWs, the cost of LibRaw/rawpy should not block the
   selection or user movement.
4. Colorimetric precision must be maintained in review/development mode,
   but navigation needs a fast and honest representation about its
   limits.

References:

- RawTherapee File Browser: https://rawpedia.rawtherapee.com/File_Browser
- darktable thumbnails: https://docs.darktable.org/usermanual/4.6/en/lighttable/digital-asset-management/thumbnails/
- darktable lighttable preferences: https://docs.darktable.org/usermanual/4.8/en/preferences-settings/lighttable/

## DEC-0009: Session development profiles

- Status: accepted
- Date: 2026-04-26

Decision:
- separate the session development profile from the camera ICC profile,
- allow development profiles generated from color chart and profiles
  saved manuals from user-configured controls,
- save several development profiles within `00_configuraciones/development_profiles/`,
- register in the queue which development profile is applied to each image,
- apply an ICC profile only when the development profile has it associated with it and
  that ICC is activatable by the current QA rules,
- preserve relative paths within the session so that profiles, recipes,
  manifests and cache can move with the entire folder.

Motivation:

1. RAW developing programs like RawTherapee separate developing parameters
   reusable of the concrete image.
2. NexoRAW should work with both chart-based scientific flow and
   an operational flow without a letter, where the user manually sets criteria for
   revealed.
3. The same session may contain lighting conditions, objectives or
   different exit criteria; Therefore there should not be a single profile of
   mandatory global disclosure.

References:

- RawTherapee Sidecar Files - Processing Profiles:
  https://rawpedia.rawtherapee.com/Sidecar_Files_-_Processing_Profiles

## DEC-0010: Master TIFF with session input ICC

- Status: accepted
- Date: 2026-04-26

Decision:

- when a session generates its own ICC from a card, NexoRAW considers it
  login profile;
- the master TIFF preserves linear camera/session RGB and embeds that ICC;
- the master TIFF is not converted to sRGB, AdobeRGB or ProPhoto if ICC exists
  session;
- standard exit profiles are reserved for sessions without a letter or
  for derivatives explicitly converted using CMM;
- in non-chart sessions, the manual profile may reveal sRGB, Adobe RGB
  (1998) or real ProPhoto RGB and use their standard ICC as
  `generic_output_icc` embedded in TIFF;
- the calibrated recipe created from force card `tone_curve=linear`,
  `output_linear=true` and `output_space=scene_linear_camera_rgb` to maintain
  consistency with the generated ICC.

Motivation:
1. The session ICC is calculated after the card is revealed, but describes the
   Camera/session RGB produced by that controlled recipe.
2. Convert directly to a generic space in the TIFF mix master
   input profile assignment and output conversion.
3. Keeping the master in the session domain avoids double conversions and
   preserves a more faithful artifact for auditing and subsequent derivatives.

References:

- RawTherapee Color Management:
  https://rawpedia.rawtherapee.com/Color_Management
- RawTherapee How to create DCP color profiles:
  https://rawpedia.rawtherapee.com/How_to_create_DCP_color_profiles
- RawTherapee ICC Profile Creator:
  https://rawpedia.rawtherapee.com/ICC_Profile_Creator
- Internal methodology:
  [RAW development methodology and ICC management] (METODOLOGIA_COLOR_RAW.md)

## DEC-0011: Sidecars backpack by RAW

- Status: accepted
- Date: 2026-04-26

Decision:

- store a `nombre.RAW.nexoraw.json` sidecar next to each RAW;
- record recipe, assigned development profile, session ICC, settings
  detail/render, RAW identity and recent TIFF outputs;
- use JSON for consistency with existing auditable sidecars and manifests
  in NexoRAW;
- automatically load the backpack when selecting or reinserting a RAW in the
  queue when the development profile exists in the session.

Motivation:

1. Established RAW developing programs treat development as editing
   parametric and save settings on sidecars.
2. A session can move between teams or users without losing parameters
   per image.
3. The sidecar by RAW complements, does not replace, `session.json`, NexoRAW Proof or
   `batch_manifest.json`.

References:

- RawTherapee Sidecar Files - Processing Profiles:
  https://rawpedia.rawtherapee.com/Sidecar_Files_-_Processing_Profiles

## DEC-0012: Monitor ICC Profile from System

- Status: accepted
- Date: 2026-04-26

Decision:

- activate by default the ICC monitor management in the GUI;
- automatically detect the profile configured in the operating system;
- allow manual override per user;
- apply the monitor profile only to previews and thumbnails, never to TIFF
  master, session profiles or exports;
- use sRGB only as a fallback when the system does not expose any profile or the
  Detected profile cannot be opened.

Motivation:
1. Not all monitors are sRGB; assuming sRGB can give saturation and hue
   incorrect on wide-gamut or calibrated displays.
2. Operating systems already maintain the active ICC profile of the monitor, so
   so NexoRAW should consume that configuration before asking the user for a
   manual route.
3. The monitor profile is a display condition, not a performance parameter.
   revealed nor a property of the exported file.

References:

- Microsoft GetICMProfileW:
  https://learn.microsoft.com/en-us/windows/win32/api/wingdi/nf-wingdi-geticmprofilew
- Apple CGDisplayCopyColorSpace:
  https://developer.apple.com/documentation/coregraphics/cgdisplaycopycolorspace%28_%3A%29
- Apple CGColorSpace:
  https://developer.apple.com/documentation/CoreGraphics/CGColorSpace
- freedesktop.org colord ColorManager:
  https://www.freedesktop.org/software/colord/gtk-doc/ColorManager.html
- freedesktop.org colord Device:
  https://www.freedesktop.org/software/colord/gtk-doc/Device.html