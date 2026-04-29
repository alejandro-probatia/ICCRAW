_Spanish version: [PROBRAW_PROOF.es.md](PROBRAW_PROOF.es.md)_

# ProbRAW Proof

ProbRAW Proof is the self-contained signature layer of ProbRAW. Its objective is to avoid
that evidentiary validity depends exclusively on C2PA or a central list
of admitted authorities.

It does not implement its own cryptography. Use standard cryptography:

- SHA-256 to identify exact bytes.
- Ed25519 for asymmetric digital signature.
- Canonical JSON with ordered keys to calculate and verify the signature.

## Trust model

ProbRAW Proof does not decide who is an authority. Sign the manifest with the password
private of the expert, laboratory or institution. Trust is established
publishing and storing the public key:

- in an expert report;
- on an institutional website;
- in a public repository;
- by external record or record;
- through cross-signature by another entity.

A third party can verify that:

1. the sidecar was signed by the corresponding private key;
2. the public key matches the declared fingerprint;
3. the contributed RAW matches the signed SHA-256;
4. the final TIFF matches the signed SHA-256;
5. The recipe, ICC profile and declared settings are those contained in the proof.

## Relationship with C2PA

C2PA is still supported, but is not required for a ProbRAW TIFF.
have cryptographic traceability. The policy is like this:

- ProbRAW Proof: mandatory and automatically generated autonomous layer for final TIFF.
- C2PA: interoperable layer; use external certificate if it exists or local identity
  self-issued if it does not exist.
- `batch_manifest.json`: external batch manifest, maintained.
- Linear audit, hashes and ICC profiles: are maintained.

If C2PA can be embedded, ProbRAW writes it first. Then calculate the hash
from the TIFF already signed with C2PA and creates the ProbRAW Proof sidecar. This is how it is avoided
sign bytes that later change. If the C2PA reader reports
`signingCredential.untrusted` with the local identity, is interpreted as
external trust warning, not as loss of RAW-TIFF link.

## Local identity

In normal use it is not necessary to execute any command: if there are no variables
environment or configured routes, ProbRAW automatically creates the Proof identity in
`~/.probraw/proof`.

To manually generate or replace an identity:
```bash
probraw proof-keygen \
  --private-key ~/.probraw/proof/probraw-proof-private.pem \
  --public-key ~/.probraw/proof/probraw-proof-public.pem
```
To encrypt the private key:
```bash
probraw proof-keygen \
  --private-key ~/.probraw/proof/probraw-proof-private.pem \
  --public-key ~/.probraw/proof/probraw-proof-public.pem \
  --passphrase "frase larga y privada"
```
The private key should not be uploaded to the repository, sent by mail, or left
no access control. The public key can be distributed.

## Export TIFF with ProbRAW Proof
```bash
probraw batch-develop ./raws \
  --recipe recipe_calibrated.yml \
  --profile camera_profile.icc \
  --out ./tiffs
```
It can also be configured by environment:
```bash
export PROBRAW_PROOF_KEY=~/.probraw/proof/probraw-proof-private.pem
export PROBRAW_PROOF_PUBLIC_KEY=~/.probraw/proof/probraw-proof-public.pem
export PROBRAW_PROOF_SIGNER_NAME="Laboratorio / Perito"
```
Each final TIFF generates a sidecar:
```text
captura.tiff
captura.tiff.probraw.proof.json
```
## Verify
```bash
probraw verify-proof captura.tiff.probraw.proof.json \
  --tiff captura.tiff \
  --raw captura.NEF \
  --public-key probraw-proof-public.pem
```
The check returns `status=ok` only if signature, public key, RAW, TIFF and
Settings hash match. The settings hash is not the only record: it is used
as an integrity check on a complete `render_settings` block that remains
signed within the proof.

## Signed content

The sidecar includes and signs:

- SHA-256 and size of the original RAW.
- SHA-256 and final TIFF size.
- base name, extension, MIME and non-probative auxiliary route;
- available camera metadata;
- ProbRAW version;
- RAW backend and demosaicing algorithm;
- full recipe and recipe hash;
- used ICC profile and hash;
- color management mode;
- complete `render_settings` block: RAW recipe, detail/sharpness adjustments,
  contrast/render settings, color management, RAW/color flow and color criteria
  reproducibility;
- summary of settings for quick reading, keeping the block complete for
  experimental reproduction;
- C2PA status if embedded;
- public key and SHA-256 fingerprint of the signer.

The RAW or TIFF path is never the primary evidentiary identifier. The
evidentiary identifier are the hashes of the exact bytes.