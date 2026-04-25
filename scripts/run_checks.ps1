param(
  [switch]$StrictExternalTools,
  [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"

function Invoke-Native {
  param(
    [string]$Label,
    [string]$FilePath,
    [string[]]$Arguments
  )

  Write-Host "==> $Label"
  & $FilePath @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "$Label fallo con codigo $LASTEXITCODE"
  }
}

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $Root ".venv\Scripts\python.exe"

Set-Location $Root

if (-not (Test-Path $Python)) {
  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($py) {
    Invoke-Native "Crear entorno virtual" $py.Source @("-3.12", "-m", "venv", ".venv")
  } else {
    Invoke-Native "Crear entorno virtual" "python" @("-m", "venv", ".venv")
  }
}

if (-not $SkipInstall) {
  Invoke-Native "Instalar dependencias de desarrollo" $Python @("-m", "pip", "install", "-e", ".[dev,gui,installer]")
}

Invoke-Native "Ejecutar tests" $Python @("-m", "pytest")

$toolArgs = @("-m", "iccraw", "check-tools")
if ($StrictExternalTools) {
  $toolArgs += "--strict"
}
Invoke-Native "Comprobar herramientas externas" $Python $toolArgs
