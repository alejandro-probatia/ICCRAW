_Spanish version: [THIRD_PARTY_LICENSES.es.md](THIRD_PARTY_LICENSES.es.md)_

# Third party licenses (operational summary)

This file summarizes licenses for key components and how they are integrated into ProbRAW.

Review date: 2026-04-25.

## 1) ProbRAW (main repository)

- License: `AGPL-3.0-or-later`.
- Project led by Probatia Forensics SL (https://probatia.com) in collaboration
  with the Spanish Association of Scientific and Forensic Imaging
  (https://imagencientifica.es).

## 2) ArgyllCMS (`colprof`, `xicclu`, `cctiff`)

- Use in ProbRAW: external tool per thread to generate ICC profiles,
  validate the actual ICC and convert final TIFFs to output profiles.
- ArgyllCMS declared license: AGPL for the main package.
- ProbRAW Policy:
  - no binaries are redistributed within the repository,
  - installation from official source or system package is required,
  - Version and context are recorded in traceability.

## 3) LibRaw/rawpy/rawpy-demosaic

- Use in ProbRAW: unique RAW development engine using the Python module
  `rawpy`, linked to LibRaw.
- Installable base dependency: `rawpy`, linked to LibRaw.
- GPL3 backend for AMaZE: `rawpy-demosaic`, GPL3 fork of `rawpy` including
  the demosaic packs GPL2/GPL3 from LibRaw and exports the same module `rawpy`.
- Declared licenses:
  - LibRaw: LGPL/CDDL according to upstream.
  - `rawpy`: MIT, without GPL demosaic packs on standard wheels.
  - `rawpy-demosaic`: `GPL-3.0-or-later`.
  - LibRaw demosaic pack GPL3: GPL3+, includes AMaZE.
- ProbRAW Policy:
  - ProbRAW remains under `AGPL-3.0-or-later`, GPL3+ compliant,
  - version of `rawpy`, installed distribution (`rawpy` or
    `rawpy-demosaic`), LibRaw and `rawpy.flags` in execution context,
  - AMaZE is only advertised as available when `DEMOSAIC_PACK_GPL3=True`,
  - License notices are included when publishing builds that redistribute wheels.

## 4) Py
Side6/Qt (GUI optional)

- Use in ProbRAW: optional graphical interface.
- Qt for Python Community License: LGPLv3/GPLv3 (according to official Qt documentation).
- ProbRAW Policy:
  - optional dependency (`pip install -e .[gui]`),
  - keep license notices when redistributing builds with GUI.

## 5) c2pa-python (C2PA/CAI for final signed TIFF)- Use in ProbRAW: signing and reading C2PA manifests embedded in final TIFF.
- License declared by `contentauth/c2pa-python`: Apache-2.0 or MIT.
- ProbRAW Policy:
  - dependency installed via extra (`pip install -e .[c2pa]`),
  - mandatory to generate final ProbRAW TIFFs,
  - does not replace `batch_manifest.json`, SHA-256 hashes or linear auditing,
  - the private key is passed via file path and is not recorded in logs,
  - review certificates, TSA and trust policy before trial use.

## 6) Relevant Python dependencies

- `opencv-python-headless`: BSD-3-Clause (OpenCV).
- `tifffile`: BSD.
- `imagecodecs`: BSD-3-Clause; TIFF codecs for LZW, JPEG and ZSTD compression.
- `numpy`: BSD-3-Clause.
- `scipy`: BSD-3-Clause.
- `PyYAML`: MIT.
- `colour-science`: BSD-3-Clause.
- `Pillow`: HPND-like (PIL Software License). ProbRAW uses `ImageCms` only
  for ICC conversion of monitor in the viewfinder; the scientific/export pipeline
  continues to use ArgyllCMS for profiling, validation and final ICC conversions.
- `rawpy`: MIT; Standard wheels without GPL demosaic packs.
- `rawpy-demosaic`: GPL-3.0-or-later; enables demosaic packs GPL2/GPL3.
- `c2pa-python`: Apache-2.0 or MIT; required to sign final TIFFs.

## 8) Packaging Tools

- `PyInstaller`: build tool to create Windows executables and local macOS
  bundles.
- `Inno Setup`: external tool to generate the `.exe` installer.
- ProbRAW Policy:
  - are used as construction tools,
  - binaries generated in the repository are not versioned,
  - review licenses and notices before publishing a redistributable release.

## 9) Project distribution rule

Before publishing release/binaries/container:

1. include `LICENSE` (AGPL) of the project,
2. include this file or updated equivalent,
3. include instructions to obtain corresponding source code,
4. verify licenses of packaged system binaries (if packaged),
5. if AMaZE is distributed, include GPL3 notices from `rawpy-demosaic`, LibRaw and
   demosaic packs, along with the corresponding source code or public URL.

## 10) Contributor Covenant 2.1 (code of conduct)- Use in ProbRAW: texts `CODE_OF_CONDUCT.md` and `CODE_OF_CONDUCT.es.md`.
- Source: `https://www.contributor-covenant.org/version/2/1/code_of_conduct/`.
- License declared by the Contributor Covenant project: CC-BY-4.0.
- ProbRAW Policy:
  - the attribution to the original text is preserved,
  - Only the contact method is replaced by that of the project maintainer.
