param(
  [string]$Python = "",
  [string]$Wheel = "",
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
  Invoke-Native "Eliminar backend RAW base" $Python @("-m", "pip", "uninstall", "-y", "rawpy", "rawpy-demosaic")
  Invoke-Native "Instalar backend AMaZE GPL3" $Python @("-m", "pip", "install", "--force-reinstall", $Wheel)
} elseif ($TryPyPI) {
  Invoke-Native "Eliminar backend RAW base" $Python @("-m", "pip", "uninstall", "-y", "rawpy", "rawpy-demosaic")
  Invoke-Native "Instalar rawpy-demosaic desde PyPI" $Python @("-m", "pip", "install", "--force-reinstall", "rawpy-demosaic")
} else {
  throw "Indica -Wheel con una wheel rawpy_demosaic compatible o usa -TryPyPI."
}

Invoke-Native "Verificar soporte AMaZE" $Python @("scripts\check_amaze_support.py")
