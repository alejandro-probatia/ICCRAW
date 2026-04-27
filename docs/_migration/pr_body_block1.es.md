## Bloque 1 - Visibilidad y captacion de comunidad

Este PR no toca codigo del pipeline. Solo anade documentacion, plantillas y demo.

### Cambios

- [x] README reescrito (cabecera): propuesta de valor, badges, screenshot, quickstart, comparativa
- [x] docs/COMPARISON.md: tabla comparativa completa
- [x] CONTRIBUTING.md
- [x] CODE_OF_CONDUCT.md (Contributor Covenant 2.1)
- [x] CODE_OF_CONDUCT.es.md
- [x] SECURITY.md
- [x] .github/ISSUE_TEMPLATE/{bug_report,feature_request,colorimetric_validation,config}
- [x] .github/PULL_REQUEST_TEMPLATE.md
- [x] docs/_migration/github_issues_to_create.md
- [x] docs/_migration/github_topics.md
- [x] scripts/create_github_issues.sh (con --dry-run por defecto)
- [x] examples/demo_session/ completo

### Acciones manuales pendientes para el mantenedor

1. Ejecutar `gh repo edit ... --add-topic ...` (ver `docs/_migration/github_topics.md`).
2. Revisar `docs/_migration/github_issues_to_create.md` y ejecutar `bash scripts/create_github_issues.sh` cuando este conforme.
3. Rellenar contacto en CODE_OF_CONDUCT.md y SECURITY.md.
4. [Si aplica] Aportar dataset CC-BY propio para examples/demo_session/.

### Datos pendientes detectados

- `[contacto-pendiente@dominio]` en `CODE_OF_CONDUCT.md`, `CODE_OF_CONDUCT.es.md` y `SECURITY.md`.
- `[PENDIENTE: dataset CC-BY propio de Probatia/AEICF para demo RAW real]` en `examples/demo_session/README.md`.

### Verificacion

- `bash scripts/run_checks.sh` no afectado (no se toco codigo del pipeline).
- `nexoraw check-tools --strict` ejecutado en entorno local: OK.
- `bash scripts/create_github_issues.sh --dry-run`: OK (32 issues listados).
- `bash examples/demo_session/run_demo.sh`: OK (ICC + QA + manifiesto generados).
- Plantillas YAML parseadas localmente con `PyYAML`: OK.
