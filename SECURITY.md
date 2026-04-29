_Spanish version: [SECURITY.es.md](SECURITY.es.md)_

# Security policy

## Supported versions

| Version | State | Security Support |
| --- | --- | --- |
| 0.2.x (beta) | Active | Yes |
| 0.1.x (historical beta) | Minimum maintenance | No |
| < 0.1.0-beta.5 | Legacy | No |

## How to report a vulnerability

Do not open public issues for vulnerabilities.

Report privately to: `[contacto-pendiente@dominio]`.

Include, if possible:

- ProbRAW version and operating system.
- Attack vector and reproducible steps.
- Potential impact (confidentiality, integrity, availability).
- Minimum proof of concept.

## Expected response times

- Acknowledgment of receipt: up to 72 hours.
- Initial evaluation: up to 7 calendar days.
- Mitigation proposal or patch plan: up to 21 calendar days.

If the case requires coordination with third parties, the status will be reported by the
same private channel.

## Scope (in scope)

- Vulnerabilities in RAW parsing or images used in the pipeline.
- Risks in the execution of external subprocesses (`ExifTool`, `ArgyllCMS`).
- Malicious manipulation of sidecars, manifests or proof (`.probraw.proof.json`,
  `batch_manifest.json`, C2PA) that compromises traceability.

## Out of scope

- Cosmetic GUI errors without security impact.
- Upstream dependencies failures without own exploit in ProbRAW.
  In those cases, also report to the tracker of the affected supplier.
- Generic hardening requests without reproducible scenario.

## Responsible disclosure

Do not publish technical details of a vulnerability before a patch exists
or documented mitigation for users.