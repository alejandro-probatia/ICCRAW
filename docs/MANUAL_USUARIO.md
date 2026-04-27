_Spanish version: [MANUAL_USUARIO.es.md](MANUAL_USUARIO.es.md)_

# NexoRAW User Manual

NexoRAW is a free and open application for RAW/TIFF development with
reproducible criteria, color management and traceability. It is intended for
technical-scientific, documentary, heritage and forensic photography: the RAW
original is never modified and each final TIFF is linked to its settings,
profiles, hashes and audit artifacts.

![NexoRAW calibration and development interface](assets/screenshots/nexoraw-calibrar-aplicar.png)

## 1. Installation and startup

NexoRAW is installed using the installers published for each platform.
The user should not install Python, dependencies or external tools to
hand. The installer makes available:

- the graphic application `NexoRAW`,
- the `nexoraw` and `nexoraw-ui` commands for advanced uses,
- the application icon,
- the components necessary to reveal, profile, sign and read metadata.

On Linux, macOS and Windows, open NexoRAW from the applications menu. On Linux
It should appear in the graphics/photography category.

The packaging and validation documentation for installers is left out of this
user manual and kept in:

- [Installer Publication](RELEASE_INSTALLERS.md)
- [Debian Package](DEBIAN_PACKAGE.md)
- [Windows Installer](WINDOWS_INSTALLER.md)

## 2. Basic concepts

### Session

A session is the entire work folder. Contains original RAW, adjustments,
menu readings, profiles, recipes, derivatives, cache and artifacts
audit.

Project structure:

- `00_configuraciones/`: session status, recipes, reports, profiles
  adjustment, ICC profiles, cache and intermediates. Also saves data or readings
  customized color charts when they exist.
- `01_ORG/`: RAW originals and card captures. It is the font directory.
- `02_DRV/`: exported derivatives, final TIFFs, previews and manifests.

### Development profile

An adjustment profile is a parametric recipe assigned to a specific RAW:
balance, exposure, temperature, tone, sharpness, noise and other criteria that
They can then be copied to one or more images.

It can be born in two ways:
- **Advanced profile**: born from an image with a color chart. NexoRAW calculates
  objective adjustments from the chart and also creates an input ICC of the
  session. The card RAW is marked in blue.
- **Basic profile**: born from the settings made by the user in the control panels.
  revealed. The RAW is marked in green.

### NexoRAW Backpack

The backpack is the `RAW.nexoraw.json` file that remains next to the RAW. Save the
settings assigned to that specific image, just like other people's sidecars
RAW developers.

The thumbnails indicate the type of profile assigned:

- blue band: RAW with advanced profile created from card;
- green band: RAW with basic profile created from manual settings.

### Working methodology in NexoRAW 0.2

NexoRAW no longer works with the idea of "calibrating an entire session" as a
global action that applies to everything without distinguishing files. The criterion of the
version 0.2 is more similar to that of the established RAW developers: each image
can have a setting profile assigned, and that profile is saved as an edit
parametric next to RAW.

The operating flow is:

1. Create or open a work session.
2. Browse the originals at `01_ORG/`.
3. Choose a representative image.
4. Adjust it from the right panels.
5. Save that setting as a profile assigned to the image.
6. Copy that profile from the thumbnail.
7. Paste the profile on other images taken under equivalent conditions.
8. Send those images to the queue and export them as TIFF in `02_DRV/`.

When a color chart exists, NexoRAW can automate some of that adjustment:
calculates an advanced profile from the chart, generates an input ICC of the
session and mark the card image in blue. When there is no letter, the user
manually adjust the image, save a basic profile and the thumbnail remains
marked in green.

The letter is the recommended option because it provides an objective reference
densitometry and colorimetry. It is not mandatory: the application also allows
work without a card with a basic profile and a generic ICC (`sRGB`, 'Adobe RGB
(1998)` o `ProPhoto RGB`), making it clear in the traceability that it has not been measured
your own input profile.Color rule:

- with card: the master TIFF uses camera/session RGB and embeds the ICC of
  input generated for that session;
- without letter: the TIFF uses the generic ICC chosen as the output profile
  declared;
- the monitor profile only affects the on-screen display and never
  modify TIFFs or manifests.

## 3. Create or open a session

![Session Management](assets/screenshots/nexoraw-sesion.png)

1. Open NexoRAW.
2. In `1. Sesion`, choose the root directory of the session.
3. Type a session name.
4. Add, if applicable, lighting conditions and shooting notes.
5. Press `Crear sesion` or `Abrir sesion`.
6. Place the working RAWs and card captures in `01_ORG/`.

This first tab only defines the workplace. Fit profiles
They are managed later, in `2. Ajustar / Aplicar`, when they are already being reviewed
images and settings.

If you open a project root from `Abrir carpeta...`, NexoRAW displays
directly `01_ORG/` to browse the images. If you are within `01_ORG/`
and press `Usar carpeta actual`, the application recognizes the root of the project
complete.

When changing projects, NexoRAW clears the previous selection, the visual queue and
the persisted routes that do not belong to the new root. The old sessions
that still have folders `raw/`, `charts/`, `exports/`, `profiles/`,
`config/` or `work/` are opened without destructive conversion; when possible, a
inherited path like `raw/captura.NEF` automatically resolves against
`01_ORG/captura.NEF`.

## 4. Recommended flow: with color chart

This is the preferred flow when seeking the greatest colorimetric objectivity.
The card allows you to create two related artifacts:

- an advanced adjustment profile, assigned to card RAWs;
- a project-specific input ICC profile.

![Flow with color chart](assets/screenshots/nexoraw-flujo-con-carta.png)

Steps:
1. Enter `2. Ajustar / Aplicar`.
2. Navigate to the folder where the letter captures are.
3. Select one or more letter captures.
4. Press `Usar seleccion como referencias colorimetricas`.
5. Check `Gestión de color y calibración` for the JSON reference, the type of
   letter and ICC format. Adjusts the demosaic and base RAW criteria according to
   `RAW Global` if necessary.
6. If automatic detection fails, use `Marcar en visor`, indicate the four
   corners and save the detection.
7. Press `Generar perfil avanzado con carta`.
8. Review the report, overlays and profile status.

Result:

- recipe calibrated in `00_configuraciones/`,
- advanced profile adjustment in `00_configuraciones/development_profiles/`,
- ICC project input in `00_configuraciones/profiles/`,
- profile/QA and cache reports in `00_configuraciones/`.
- `RAW.nexoraw.json` backpack on the card RAWs used to generate the profile.

When there is a card, the TIFF master preserves camera RGB and embeds the
Input ICC generated. Does not convert directly to sRGB, Adobe RGB or
ProPhoto in that master, to avoid double conversions and preserve a
more auditable artifact.

## 5. Alternative flow: no color chart

This flow is valid when there is no colorimetric reference. It's less
objective than the flow with a letter, but it allows working in a parametric way and
traceable.

![Flow without color chart](assets/screenshots/nexoraw-flujo-sin-carta.png)

Steps:

1. Select a representative image from the series.
2. Adjust `Brillo y contraste`, `Color`, `Nitidez` and the parameters of
   `RAW Global` required.
3. Open `Gestión de color y calibración`.
4. Enter a name for the profile.
5. In `Espacio estandar sin carta`, choose the output real estate:
   - `sRGB estandar`,
   - `Adobe RGB (1998) estandar`,
   - `ProPhoto RGB estandar`.
6. Press `Guardar perfil básico`.
7. Press `Guardar perfil basico en imagen` to write the backpack next to the RAW.

Result:

- manual profile in `00_configuraciones/development_profiles/`,
- Standard ICC copied from system or ArgyllCMS in `00_configuraciones/profiles/standard/`,
- backpack `RAW.nexoraw.json` with `generic_output_icc`,
- Final TIFF in `02_DRV/` revealed in that space and embedded standard ICC.

Use this flow when there is no card. If a letter is added later
valid for that same capture condition, it is advisable to generate an advanced profile
with letter and use it as the main reference.

## 6. Copy and paste adjustment profiles between images
NexoRAW treats RAW development as parametric editing. The practical way of
reusing settings is to copy the profile assigned to a thumbnail and paste it into
others. It can be an advanced letter profile or a basic manual profile.

![Backpacks and settings copy](assets/screenshots/nexoraw-mochila-ajustes.png)

Steps:

1. Select the image that contains the correct profile.
2. Press `Guardar perfil basico en imagen` if it is a manual setting that has not yet been
   He has a backpack.
3. Press `Copiar perfil de ajuste`.
4. Select one or more destination images.
5. Press `Pegar perfil de ajuste`.
6. Check that the target thumbnails retain the color of the profile type:
   blue for advanced, green for basic.

You can also use the thumbnail context menu to save, copy or
glue adjustment profiles.

## 7. Export final TIFF and development queue

The queue allows you to process a selection or a complete batch without losing which profile
development corresponds to each file.

![Development queue](assets/screenshots/nexoraw-cola-revelado.png)

Steps:

1. Select one or more images.
2. Press `Anadir seleccion a cola`.
3. If applicable, activate a development profile and press `Asignar perfil activo`.
4. Check the column `Perfil` in the table.
5. Press `Revelar cola`.
6. Check the execution monitor and the log.

Each final TIFF can generate:

- TIFF 16-bit final;
- Linear audit TIFF in `_linear_audit/`;
- sidecar `*.nexoraw.proof.json`;
- backpack `RAW.nexoraw.json`;
- `batch_manifest.json`;
- C2PA metadata if configured.

If the output TIFF already exists, NexoRAW creates a new version:
`captura.tiff`, `captura_v002.tiff`, `captura_v003.tiff`, etc.

## 8. Image settings

### Brightness and contrast

Includes Brightness, Levels, Contrast, Mid Curve and Advanced Tone Curve.

### Color

Includes final illuminant, temperature, tint and neutral dropper. The
dropper helps estimate a temperature/hue correction from a zone
neutral.

### Sharpness

Includes sharpening, radius, luminance/color noise reduction and image correction.
lateral chromatic aberration. These settings apply to the preview and render
end when `Aplicar ajustes basicos y de nitidez` is active.

### Color management and calibration
Groups adjustment profiles by file, advanced profile generation with
letter and the active ICC. In letter flow, the active ICC is the input ICC
generated for those RAW and must correspond to the same recipe, camera, optics and
lighting.

### Global RAW

Groups the basic parameters of RAW development: engine, demosaic, image balance
RAW whites, black levels, base exposure, RAW curve and workspaces.

## 9. Metadata, Proof and traceability

The `Metadatos` vertical tab allows you to review the selected file.

![Metadata Viewer](assets/screenshots/nexoraw-metadatos.png)

Sample:

- technical summary,
- EXIF and manufacturer data,
- GPS if it exists,
- C2PA information,
- NexoRAW Proof,
- Full JSON available.

NexoRAW Proof is the mandatory standalone signature for the project. Links RAW, TIFF,
recipe, profile, settings, hashes and public key of the signer. C2PA/CAI is a
optional interoperable layer.

## 10. Monitor Color Management

The global options are in `Configuracion > Configuracion global...`.

![Global Settings](assets/screenshots/nexoraw-configuracion-global.png)

In `Preview / monitor`, NexoRAW uses by default the ICC profile configured in the
operating system:

- ColorSync on macOS,
- `colord` or `_ICC_PROFILE` on Linux/BSD,
- WCS/ICM on Windows.

If the system does not expose any profiles, NexoRAW uses sRGB as a fallback. This
management only affects the screen display and thumbnails; does not modify
TIFFs, hashes, session profiles or manifests.

## 11. Performance and cache

NexoRAW separates navigation, work preview and final render:

- navigation uses a horizontal strip of thumbnails with adjustable size;
- RAW files first use their embedded thumbnail and, if it does not exist, a reveal
  fast caching to not show just a generic icon;
- critical review can be done with high quality preview;
- the final render is executed with the audited pipeline.

The session saves persistent cache in `00_configuraciones/cache/`. If
share the entire session folder with another user, that cache can
speed up the opening of the same file structure.

Good practices:
- use automatic preview to navigate; NexoRAW low resolution only during
  interaction when necessary to maintain fluency;
- activate compare/precision 1:1 when checking sharpness or color at real pixel;
- activate `use_cache: true` in work recipes if you are going to repeat settings on
  the same RAWs and you want to reuse the numerical demosaic;
- do not regenerate profiles if you only change final settings;
- save backpacks before copying settings to other images;
- works within the session structure so that relative paths, cache and
  sidecars remain transportable.

## 12. Common problems

### I don't see AMaZE available

AMaZE only appears if the installer includes the corresponding GPL3 backend. Yes
is not available, NexoRAW uses a supported algorithm like DCB and registers it in
the recipe.

### Card detection fails

Use a capture with the complete card, without reflections and with unsaturated patches.
If automatic detection fails, use `Marcar en visor` and save the four
corners manually.

### Profile produces dominant or clipping

Check that the letter, the JSON reference and the recipe correspond to the same
capture condition. Check that a derived TIFF has not been used as a letter and
that the profile is not rejected by QA.

### There is no color chart

Use cardless flow: manual profile + actual output standard RGB space. It is
functional and traceable, but does not replace the precision of a reference
real colorimetry.

### The image already had a TIFF exported

NexoRAW does not overwrite existing outputs. Create a new version with suffix
`_v002`, `_v003`, etc.

## 13. Related documentation

- [RAW development methodology and ICC management] (METODOLOGIA_COLOR_RAW.md)
- [NexoRAW Proof](NEXORAW_PROOF.md)
- [C2PA/CAI](C2PA_CAI.md)
- [LibRaw + ArgyllCMS Integration](INTEGRACION_LIBRAW_ARGYLL.md)
- [Installer Publication](RELEASE_INSTALLERS.md)
- [Third Party Licenses](THIRD_PARTY_LICENSES.md)
- [Changelog](../CHANGELOG.md)