#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_FILE="$ROOT_DIR/docs/_migration/github_issues_to_create.md"
MODE="dry-run"

usage() {
  cat <<'USAGE'
Uso:
  bash scripts/create_github_issues.sh            # dry-run (por defecto)
  bash scripts/create_github_issues.sh --dry-run
  bash scripts/create_github_issues.sh --apply
USAGE
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

if [[ "${1:-}" == "--apply" ]]; then
  MODE="apply"
elif [[ -n "${1:-}" && "${1:-}" != "--dry-run" ]]; then
  echo "Argumento no soportado: ${1}" >&2
  usage
  exit 1
fi

if [[ ! -f "$SOURCE_FILE" ]]; then
  echo "No existe archivo fuente: $SOURCE_FILE" >&2
  exit 1
fi

parse_issues() {
  python3 - "$SOURCE_FILE" <<'PY'
import base64
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
lines = path.read_text(encoding="utf-8").splitlines()

heading_re = re.compile(r"^### \[(?P<id>[^\]]+)\] (?P<title>.+)$")
labels_re = re.compile(r"^<!-- labels: (?P<labels>.+) -->$")
good_re = re.compile(r"^<!-- good_first_issue: (?P<good>yes|no) -->$")

records = []
i = 0
while i < len(lines):
    m = heading_re.match(lines[i])
    if not m:
        i += 1
        continue

    issue_id = m.group("id").strip()
    title = m.group("title").strip()
    labels = ""
    good = "no"
    body_lines = []

    j = i + 1
    while j < len(lines):
        line = lines[j]
        if heading_re.match(line):
            break
        lm = labels_re.match(line)
        if lm:
            labels = lm.group("labels").strip()
            j += 1
            continue
        gm = good_re.match(line)
        if gm:
            good = gm.group("good").strip()
            j += 1
            continue
        if line.strip() == "```issue-body":
            j += 1
            while j < len(lines) and lines[j].strip() != "```":
                body_lines.append(lines[j])
                j += 1
            if j < len(lines) and lines[j].strip() == "```":
                j += 1
            continue
        j += 1

    if not labels:
        raise SystemExit(f"Faltan labels para {issue_id}")
    body = "\n".join(body_lines).strip()
    if not body:
        raise SystemExit(f"Falta issue-body para {issue_id}")

    body += "\n\n---\nFuente canonica: `docs/ISSUES.md`\nDetalle de migracion: `docs/_migration/github_issues_to_create.md`"
    body_b64 = base64.b64encode(body.encode("utf-8")).decode("ascii")
    print("\t".join([issue_id, title, labels, good, body_b64]))
    i = j
PY
}

issue_exists() {
  local title="$1"
  gh issue list --state all --limit 500 --search "\"$title\" in:title" --json title --jq '.[].title' \
    | grep -Fxq "$title"
}

if [[ "$MODE" == "apply" ]]; then
  if ! command -v gh >/dev/null 2>&1; then
    echo "gh CLI no esta disponible en PATH." >&2
    exit 1
  fi
  if ! gh auth status >/dev/null 2>&1; then
    echo "gh auth no esta configurado. Ejecuta: gh auth login" >&2
    exit 1
  fi
fi

count=0
created=0
skipped=0

while IFS=$'\t' read -r issue_id title labels_csv good_first body_b64; do
  [[ -z "$issue_id" ]] && continue
  count=$((count + 1))

  IFS=',' read -r -a labels <<< "$labels_csv"
  if [[ "$good_first" == "yes" ]]; then
    labels+=("good-first-issue")
  fi

  label_flags=()
  for raw_label in "${labels[@]}"; do
    label="$(echo "$raw_label" | xargs)"
    [[ -z "$label" ]] && continue
    label_flags+=("--label" "$label")
  done

  body="$(python3 - <<'PY' "$body_b64"
import base64
import sys
print(base64.b64decode(sys.argv[1]).decode("utf-8"))
PY
)"

  if [[ "$MODE" == "dry-run" ]]; then
    echo "[DRY-RUN] ${issue_id}"
    echo "  Titulo: $title"
    echo "  Labels: ${labels_csv}${good_first:+$( [[ "$good_first" == "yes" ]] && echo ",good-first-issue" )}"
    echo
    continue
  fi

  if issue_exists "$title"; then
    echo "[SKIP] Ya existe issue con mismo titulo: $title"
    skipped=$((skipped + 1))
    continue
  fi

  tmp_body="$(mktemp)"
  printf '%s\n' "$body" > "$tmp_body"
  gh issue create --title "$title" "${label_flags[@]}" --body-file "$tmp_body"
  rm -f "$tmp_body"
  echo "[CREATE] $title"
  created=$((created + 1))
done < <(parse_issues)

echo "Total en catalogo: $count"
if [[ "$MODE" == "apply" ]]; then
  echo "Creados: $created"
  echo "Saltados por duplicado: $skipped"
else
  echo "Modo dry-run: no se creo ningun issue."
fi
