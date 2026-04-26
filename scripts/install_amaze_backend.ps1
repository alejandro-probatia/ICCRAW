param(
  [string]$Python = "",
  [string]$Wheel = "",
  [string]$Source = "",
  [switch]$TryPyPI
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

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = (Resolve-Path (Join-Path $ScriptDir "..")).Path
Set-Location $Root

if ([string]::IsNullOrWhiteSpace($Python)) {
  $Python = Join-Path $Root ".venv\Scripts\python.exe"
}

if (-not (Test-Path $Python)) {
  Invoke-Native "Crear entorno virtual" "python" @("-m", "venv", ".venv")
}

$Python = (Resolve-Path $Python).Path
Invoke-Native "Actualizar pip" $Python @("-m", "pip", "install", "--upgrade", "pip")

if (-not [string]::IsNullOrWhiteSpace($Wheel)) {
  if (-not (Test-Path $Wheel)) {
    throw "No existe la wheel indicada: $Wheel"
  }
  $Wheel = (Resolve-Path $Wheel).Path
  Invoke-Native "Instalar backend AMaZE GPL3" $Python @("scripts\install_amaze_backend.py", "--wheel", $Wheel)
} elseif ($TryPyPI) {
  Invoke-Native "Instalar rawpy-demosaic desde PyPI" $Python @("scripts\install_amaze_backend.py", "--pypi")
} elseif (-not [string]::IsNullOrWhiteSpace($Source)) {
  Invoke-Native "Instalar backend AMaZE GPL3 desde fuente" $Python @("scripts\install_amaze_backend.py", "--source", $Source)
} else {
  throw "Indica -Wheel, -Source con una fuente trazada o usa -TryPyPI si existe wheel compatible en el indice."
}
