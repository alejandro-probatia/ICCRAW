_Spanish version: [LEGAL_COMPLIANCE.es.md](LEGAL_COMPLIANCE.es.md)_

# Legal Compliance and Licenses

## Scope

This document defines the NexoRAW legal compliance framework for use
scientific and forensic.

## Project License

- NexoRAW is distributed under `AGPL-3.0-or-later`.
- Any redistribution (source code or binaries) must preserve:
  - copyright notice,
  - AGPL license,
  - access to the corresponding source.
- If the software is offered as a network service, access to the network must be maintained
  corresponding source for remote users (AGPL).
- The project has a scientific/community objective without commercial purpose,
  but the AGPL does not impose a general prohibition on commercial use by third parties.

## AMaZE and GPL demosaic packs

NexoRAW can use AMaZE if the installed `rawpy` module is linked to LibRaw
with `LIBRAW_DEMOSAIC_PACK_GPL3` enabled. This case requires GPL3+ for the
resulting product; `AGPL-3.0-or-later` meets that requirement.

Policy:

1. keep NexoRAW under `AGPL-3.0-or-later`,
2. prefer `rawpy-demosaic` for builds with AMaZE when wheel exists
   compatible or build your own wheel,
3. Do not advertise AMaZE as available unless
   `rawpy.flags["DEMOSAIC_PACK_GPL3"]` is `True`,
4. include GPL3/AGPL notices and corresponding source in any installer or
   container that redistributes AMaZE,
5. Document the exact backend in `run_context` and release reports.

## External flow tools

NexoRAW combines Python dependencies and external tools:

- `rawpy`/LibRaw or `rawpy-demosaic`/LibRaw for RAW development.
- `ArgyllCMS` (`colprof`, `xicclu`, `cctiff`) for construction, validation and
  conversion of ICC profiles.
- `exiftool` for metadata.
- `PySide6` (Qt for Python, optional) for GUI.

Relevant license notes:

1. ArgyllCMS publishes its main package under AGPL (according to official project documentation).
2. LibRaw declares LGPL/CDDL licenses for the kernel; its GPL demosaic packs
   They impose GPL2+ or GPL3+ depending on the pack used.
3. `rawpy` standard is MIT and does not include GPL packs in its wheels.
4. `rawpy-demosaic` is `GPL-3.0-or-later` and includes the GPL2/GPL3 packs.
5. Community PySide6 is distributed under LGPLv3/GPLv3; in NexoRAW it is used as an optional GUI dependency.

Integration policy:
1. no third party binaries are embedded within the repository,
2. the installation is carried out from official system packages, PyPI or official sources,
3. Dependency versions are recorded in `run_context` for auditing.

## Operational compliance rules

1. Do not remove or modify third-party license notices.
2. Keep this file and `LICENSE` synchronized with the current policy.
3. Document in `CHANGELOG.md` any license changes or critical dependency.
4. Before publishing builds or containers, verify that:
   - AGPL license of the project is attached,
   - external dependencies are documented,
   - there is a clear mechanism to obtain the corresponding source.
5. If a build is distributed that includes Qt GUI, include license notices for Qt/PySide6 and linked components.
6. If wheels/binaries are redistributed from `rawpy`, `rawpy-demosaic` or LibRaw,
   include your license notices.

## Community governance

The maintenance of the project falls on the community of:

- **Spanish Association of Scientific and Forensic Imaging**.

Periodic reviews of legal compliance and traceability are recommended to
expertise environments and digital chain of custody.

## Reference sources (accessed on 2026-04-25)

- ArgyllCMS Home: https://argyllcms.com/
- ArgyllCMS Licensing/Commercial Use: https://argyllcms.com/commercialuse.html
- Argyll Documentation (copyright/licensing): https://www.argyllcms.com/doc/ArgyllDoc.html
- Qt for Python LGPL overview: https://doc.qt.io/qtforpython-6/overviews/qtdoc-lgpl.html
- LibRaw demosaic packs: https://sources.debian.org/src/libraw/0.16.0-9%2Bdeb8u3/README.demosaic-packs
- LibRaw AMaZE/GPL3 note: https://www.libraw.org/news/libraw-0.12.html
- rawpy: https://github.com/letmaik/rawpy
- rawpy PyPI optional features: https://pypi.org/project/rawpy/
- rawpy-demosaic: https://pypi.org/project/rawpy-demosaic/

Operational summary by component:

- `docs/THIRD_PARTY_LICENSES.md`
- `docs/AMAZE_GPL3.md`