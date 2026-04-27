_Spanish version: [pr_body_block1.es.md](pr_body_block1.es.md)_

## Block 1 - Visibility and community recruitment

This PR does not touch pipeline code. Just add documentation, templates and demo.

### Changes

- [x] README rewritten (header): value proposition, badges, screenshot, quickstart, comparison
- [x] docs/COMPARISON.md: complete comparison table
- [x] CONTRIBUTING.md
- [x] CODE_OF_CONDUCT.md (Contributor Covenant 2.1)
- [x] CODE_OF_CONDUCT.es.md
- [x] SECURITY.md
- [x].github/ISSUE_TEMPLATE/{bug_report,feature_request,colorimetric_validation,config}
- [x].github/PULL_REQUEST_TEMPLATE.md
- [x] docs/_migration/github_issues_to_create.md
- [x]docs/_migration/github_topics.md
- [x] scripts/create_github_issues.sh (with --dry-run by default)
- [x] examples/demo_session/ complete

### Pending manual actions for maintainer

1. Run `gh repo edit ... --add-topic ...` (see `docs/_migration/github_topics.md`).
2. Review `docs/_migration/github_issues_to_create.md` and execute `bash scripts/create_github_issues.sh` when satisfied.
3. Fill in contact in CODE_OF_CONDUCT.md and SECURITY.md.
4. [If applicable] Provide your own CC-BY dataset for examples/demo_session/.

### Pending data detected

- `[contacto-pendiente@dominio]` in `CODE_OF_CONDUCT.md`, `CODE_OF_CONDUCT.es.md` and `SECURITY.md`.
- `[PENDIENTE: dataset CC-BY propio de Probatia/AEICF para demo RAW real]` in `examples/demo_session/README.md`.

### Verification

- `bash scripts/run_checks.sh` not affected (pipeline code was not touched).
- `nexoraw check-tools --strict` executed in local environment: OK.
- `bash scripts/create_github_issues.sh --dry-run`: OK (32 issues listed).
- `bash examples/demo_session/run_demo.sh`: OK (ICC + QA + manifest generated).
- YAML templates parsed locally with `PyYAML`: OK.