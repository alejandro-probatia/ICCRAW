_Spanish version: [NEXORAW_PROOF.es.md](NEXORAW_PROOF.es.md)_

# NexoRAW Proof

NexoRAW Proof is the self-contained signature layer of NexoRAW. Its objective is to avoid
that evidentiary validity depends exclusively on C2PA or a central list
of admitted authorities.

It does not implement its own cryptography. Use standard cryptography:

- SHA-256 to identify exact bytes.
- Ed25519 for asymmetric digital signature.
- Canonical JSON with ordered keys to calculate and verify the signature.

## Trust model

NexoRAW Proof does not decide who is an authority. Sign the manifest with the password
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

C2PA is still supported, but is not required for a NexoRAW TIFF.
have cryptographic traceability. The policy is like this:

- NexoRAW Proof: mandatory and automatically generated autonomous layer for final TIFF.
- C2PA: interoperable layer; use external certificate if it exists or local identity
  self-issued if it does not exist.
- `batch_manifest.json`: external batch manifest, maintained.
- Linear audit, hashes and ICC profiles: are maintained.

If C2PA can be embedded, NexoRAW writes it first. Then calculate the hash
from the TIFF already signed with C2PA and creates the NexoRAW Proof sidecar. This is how it is avoided
sign bytes that later change. If the C2PA reader reports
`signingCredential.untrusted` with the local identity, is interpreted as
external trust warning, not as loss of RAW-TIFF link.

## Local identity

In normal use it is not necessary to execute any command: if there are no variables
environment or configured routes, NexoRAW automatically creates the Proof identity in
`~/.nexoraw/proof`.

To manually generate or replace an identity:
```bash
nexoraw proof-keygen \
  --private-key ~/.nexoraw/proof/nexoraw-proof-private.pem \
  --public-key ~/.nexoraw/proof/nexoraw-proof-public.pem
```
To encrypt the private key:
```bash
nexoraw proof-keygen \
  --private-key ~/.nexoraw/proof/nexoraw-proof-private.pem \
  --public-key ~/.nexoraw/proof/nexoraw-proof-public.pem \
  --passphrase "frase larga y privada"
```
The private key should not be uploaded to the repository, sent by mail, or left
no access control. The public key can be distributed.

## Export TIFF with NexoRAW Proof
```bash
nexoraw batch-develop ./raws \
  --recipe recipe_calibrated.yml \
  --profile camera_profile.icc \
  --out ./tiffs
```
It can also be configured by environment:
```bash
export NEXORAW_PROOF_KEY=~/.nexoraw/proof/nexoraw-proof-private.pem
export NEXORAW_PROOF_PUBLIC_KEY=~/.nexoraw/proof/nexoraw-proof-public.pem
export NEXORAW_PROOF_SIGNER_NAME="Laboratorio / Perito"
```
Each final TIFF generates a sidecar:
```text
captura.tiff
captura.tiff.nexoraw.proof.json
```
## Verify
```bash
nexoraw verify-proof captura.tiff.nexoraw.proof.json \
  --tiff captura.tiff \
  --raw captura.NEF \
  --public-key nexoraw-proof-public.pem
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
- NexoRAW version;
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