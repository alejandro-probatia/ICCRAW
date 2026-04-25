param(
  [switch]$Strict
)

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
  throw "No existe .venv. Ejecuta: python -m venv .venv; .\.venv\Scripts\python -m pip install -e `".[dev,gui]`""
}

$argsList = @("-m", "nexoraw", "check-tools")
if ($Strict) {
  $argsList += "--strict"
}

& $Python @argsList
exit $LASTEXITCODE
