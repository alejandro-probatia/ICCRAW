_Spanish version: [C2PA_CAI.es.md](C2PA_CAI.es.md)_

# C2PA/CAI in ProbRAW

ProbRAW incorporates C2PA as an interoperable layer on top of the final TIFFs,
without requiring the user to belong to a CAI central authority. Does not replace
the existing mechanisms nor the autonomous layer
`ProbRAW Proof`: `batch_manifest.json`, SHA-256 hashes, linear auditing,
ICC profiles, QA reports and sidecars are still part of the main flow.

The required signature of the ProbRAW flow is `ProbRAW Proof`, documented in
[ProbRAW Proof](PROBRAW_PROOF.md). C2PA is embedded with external certificate if
exists; if not, ProbRAW creates a self-issued local identity and uses it as a signature
Lab C2PA.

## Implementation principles

1. The original RAW is never modified.
2. ProbRAW does not embed C2PA in original proprietary RAW (`CR2`, `CR3`,
   `NEF`, `ARW`, `RAF`, `RW2`, `ORF`, `PEF`).
3. For proprietary RAWs, the evidentiary link is declared in the final TIFF with
   a signed C2PA assertion: `org.probatia.probraw.raw-link.v1`.
4. The evidentiary identifier of the RAW is the SHA-256 of its exact bytes.
   Filename and path are just auxiliary metadata.
5. The SHA-256 of the signed TIFF is calculated after embedding C2PA and saved
   in the ProbRAW external manifest. Not included in the C2PA manifesto
   embedded to avoid a circular reference.
6. If the source is DNG, ProbRAW tries to pass it to the C2PA SDK as an ingredient
   `parentOf`, so that pre-existing C2PA credentials can
   preserved if the SDK allows it.
7. Signature, validation or missing dependency errors are not silenced.
8. The private key is not recorded in logs or stored in manifests.
9. ProbRAW does not depend on a central C2PA trust list for testing
   autonomous If the C2PA SDK is missing, the TIFF is exported with ProbRAW Proof sidecar.
   If C2PA was configured explicitly by the user and fails, the export
   It is aborted so as not to hide a requested signature error.

## C2PA installation
```bash
pip install -e .[c2pa]
```
The signature dependency is `c2pa-python>=0.32`.

In the official Windows installer this dependency is already packaged. In that
In this case, you do not have to install `pip`, Python or any DLL manually.

## Local C2PA identity

In order not to depend on certificates issued by a CAI authority, ProbRAW generates
automatically a local identity in:
```text
~/.probraw/c2pa/
```
On Windows it is normally equivalent to:
```text
%USERPROFILE%\.probraw\c2pa\
```
The identity contains:

- a local RSA private key;
- a self-issued PEM string compatible with the C2PA SDK;
- a local root certificate to document the identity used.

External C2PA readers may display `signingCredential.untrusted`. In the
ProbRAW model this is an external trust warning: the signature is not
in a central CAI list. It does not mean that the RAW-TIFF manifest is missing or that the
declared RAW hash is invalid. For evidentiary use, trust is based on the
custody or publication of the local key/certificate of the laboratory, together with
`ProbRAW Proof` and `batch_manifest.json`.

## Sign final TIFFs with C2PA
```bash
probraw batch-develop ./raws \
  --recipe recipe_calibrated.yml \
  --profile camera_profile.icc \
  --out ./tiffs \
  --proof-key ~/.probraw/proof/probraw-proof-private.pem \
  --proof-public-key ~/.probraw/proof/probraw-proof-public.pem \
  --c2pa-sign \
  --c2pa-cert chain.pem \
  --c2pa-key signing.key \
  --c2pa-alg ps256 \
  --c2pa-timestamp-url http://timestamp.digicert.com \
  --session-id sesion-2026-04-25
```
If `--c2pa-cert` and `--c2pa-key` are not passed, ProbRAW tries to use first
environment variables and then the self-issued local identity. If they pass,
`--c2pa-cert` must point to the PEM public chain and `--c2pa-key` to the key
private PEM. If no other TSA is indicated, ProbRAW uses
`http://timestamp.digicert.com`, which is the value used in the documentation
reference `c2pa-python`. In production or laboratory environments
recommends migrating the signature to KMS/HSM and defining your own or institutional TSA,
although the local CLI is useful for testing and controlled deployments.

The GUI uses environment variables if routes are not passed via CLI:
```bat
set PROBRAW_C2PA_CERT=G:\ruta\chain.pem
set PROBRAW_C2PA_KEY=G:\ruta\signing.key
```
The signature is applied to an already rendered temporary TIFF. Only if C2PA signs
ends correctly, the flow continues. The signed TIFF is then moved to
final name and the ProbRAW Proof sidecar is signed with the exact hash of that TIFF.
`batch_manifest.json` saves the final TIFF hash and the proof hash.

## RAW assertion -> TIFF

The assertion `org.probatia.probraw.raw-link.v1` records:

- SHA-256, size, base name, extension and estimated MIME of the RAW.
- RAW route as a non-probative auxiliary locator.
- Camera metadata available.
- ProbRAW recipe hash.
- Hash of the ICC profile used, if it exists.
- Hash of block `render_settings` as an integrity check, not as a unique
  settings register.
- ProbRAW version.
- RAW backend, demosaicing, output space and color management mode.
- Complete recipe applied to development/render.
- Sharpness settings applied in the GUI: denoise, sharpness and aberration
  lateral chromatic
- Basic correction/render settings: illuminant, temperature, hue,
  brightness, black/white levels, contrast, mids and advanced tone curve.
- Output color management: ICC mode, profile, workspace, color space
  output and linear/non-linear output.
- Reproducible summary of settings within the `probraw` block, duplicating the
  critical points for readers who do not display the complete JSON of
  `render_settings`.
- External technical manifest hash if provided and already exists.
- Optional session identifier.
- UTC generation date/time.

ProbRAW 0.2.5 and later generate the `org.probatia.probraw.*` assertion labels.
The verifier still accepts legacy `org.probatia.iccraw.*` labels from earlier
beta outputs so old TIFFs remain auditable.

## Verification
```bash
probraw verify-c2pa ./tiffs/captura.tiff \
  --raw ./raws/captura.NEF \
  --manifest ./tiffs/batch_manifest.json
```
The verification checks:

- that the TIFF contains a readable C2PA manifesto;
- that the RAW provided matches the declared SHA-256;
- that the signed TIFF matches `output_sha256` of the external manifest;
- that the C2PA SDK does not return technical validation errors.

If `--manifest` is missing, the C2PA and RAW verification is still executed, but the
global status will not be `ok` because the external manifest could not be checked.

## Reading metadata

The GUI includes a metadata viewer in the `Metadatos` vertical tab of the
left column. For CLI use:
```bash
probraw metadata ./tiffs/captura.tiff --out metadata.json
```
This read combines EXIF/GPS using `exiftool`, ProbRAW Proof using
sidecar `.probraw.proof.json` and C2PA manifests using `c2pa-python` if the
Optional extra is installed.

## Operational notes

- The `technical_manifest_sha256` field is only included if the indicated file
  by `--c2pa-technical-manifest` exists before signing.
- `batch_manifest.json` is written at the end of the batch, so it cannot be
  within the C2PA of the same lot without introducing circularity.
- Self-signed certificates can produce trust notices even if the
  manifest is technically readable. For actual evidentiary use, define a
  certificate policy, key custody and verifiable TSA.
