param(
  [switch]$SkipTests,
  [switch]$SkipToolCheck,
  [switch]$StrictExternalTools,
  [switch]$NoInstaller,
  [string]$Version = "",
  [string]$Python = "",
  [string]$OutputRoot = "",
  [string]$ArgyllRoot = "",
  [string]$ExifToolRoot = "",
  [string]$LcmsBin = "",
  [string]$RawpyDemosaicWheel = "",
  [string]$RawpyDemosaicSource = "",
  [switch]$RequireAmaze
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

function Resolve-Iscc {
  $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
  if ($cmd) {
    return $cmd.Source
  }

  $candidates = @()
  if ($env:ProgramFiles) {
    $candidates += (Join-Path $env:ProgramFiles "Inno Setup 6\ISCC.exe")
  }
  $programFilesX86 = ${env:ProgramFiles(x86)}
  if ($programFilesX86) {
    $candidates += (Join-Path $programFilesX86 "Inno Setup 6\ISCC.exe")
  }
  if ($env:LOCALAPPDATA) {
    $candidates += (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe")
  }

  foreach ($candidate in $candidates) {
    if (Test-Path $candidate) {
      return $candidate
    }
  }

  return $null
}

function Remove-TreeUnderRoot {
  param(
    [string]$Root,
    [string]$Target
  )

  if (-not (Test-Path $Target)) {
    return
  }

  $rootPath = [System.IO.Path]::GetFullPath($Root).TrimEnd('\')
  $targetPath = [System.IO.Path]::GetFullPath($Target).TrimEnd('\')
  if (-not $targetPath.StartsWith($rootPath, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Ruta fuera del workspace, no se elimina: $targetPath"
  }

  Remove-Item -LiteralPath $targetPath -Recurse -Force
}

function Copy-DirectoryContents {
  param(
    [string]$Source,
    [string]$Destination
  )

  if (-not (Test-Path $Source)) {
    throw "No existe directorio requerido: $Source"
  }
  New-Item -ItemType Directory -Force -Path $Destination | Out-Null
  Copy-Item -Path (Join-Path $Source "*") -Destination $Destination -Recurse -Force
}

function Resolve-CommandDirectory {
  param([string]$Command)
  $cmd = Get-Command $Command -ErrorAction SilentlyContinue
  if (-not $cmd) {
    return $null
  }
  return Split-Path -Parent $cmd.Source
}

function Resolve-ArgyllBin {
  if (-not [string]::IsNullOrWhiteSpace($ArgyllRoot)) {
    $candidate = Join-Path $ArgyllRoot "bin"
    if (Test-Path $candidate) {
      return $candidate
    }
    return $ArgyllRoot
  }
  return Resolve-CommandDirectory "colprof"
}

function Resolve-ExifToolRoot {
  if (-not [string]::IsNullOrWhiteSpace($ExifToolRoot)) {
    return $ExifToolRoot
  }
  return Resolve-CommandDirectory "exiftool"
}

function Resolve-LcmsBin {
  if (-not [string]::IsNullOrWhiteSpace($LcmsBin)) {
    return $LcmsBin
  }
  if (-not [string]::IsNullOrWhiteSpace($env:ICCRAW_LCMS_BIN)) {
    return $env:ICCRAW_LCMS_BIN
  }
  $fromPath = Resolve-CommandDirectory "tificc"
  if ($fromPath) {
    return $fromPath
  }
  $condaCandidate = Join-Path $Root "tmp\lcms2-conda\Library\bin"
  if (Test-Path (Join-Path $condaCandidate "tificc.exe")) {
    return $condaCandidate
  }
  return $null
}

function Copy-ExternalTools {
  param([string]$AppBuildDir)

  $toolsRoot = Join-Path $AppBuildDir "tools"
  $docsRoot = Join-Path $AppBuildDir "docs\third_party"
  New-Item -ItemType Directory -Force -Path $toolsRoot | Out-Null
  New-Item -ItemType Directory -Force -Path $docsRoot | Out-Null

  $argyllBin = Resolve-ArgyllBin
  if (-not $argyllBin -or -not (Test-Path (Join-Path $argyllBin "colprof.exe"))) {
    throw "No se encontro ArgyllCMS completo para empaquetar (colprof.exe)."
  }
  Copy-DirectoryContents -Source $argyllBin -Destination (Join-Path $toolsRoot "argyll\bin")
  $argyllRoot = Split-Path -Parent $argyllBin
  foreach ($file in @("License.txt", "Readme.txt")) {
    $path = Join-Path $argyllRoot $file
    if (Test-Path $path) {
      Copy-Item -LiteralPath $path -Destination (Join-Path $docsRoot "ArgyllCMS-$file") -Force
    }
  }

  $exifRoot = Resolve-ExifToolRoot
  if (-not $exifRoot -or -not (Test-Path (Join-Path $exifRoot "exiftool.exe"))) {
    throw "No se encontro ExifTool completo para empaquetar (exiftool.exe)."
  }
  Copy-DirectoryContents -Source $exifRoot -Destination (Join-Path $toolsRoot "exiftool")

  $lcmsSource = Resolve-LcmsBin
  if (-not $lcmsSource -or -not (Test-Path (Join-Path $lcmsSource "tificc.exe"))) {
    throw "No se encontro LittleCMS/tificc para empaquetar. Define -LcmsBin o ICCRAW_LCMS_BIN."
  }
  Copy-DirectoryContents -Source $lcmsSource -Destination (Join-Path $toolsRoot "lcms\bin")
  $lcmsRoot = Split-Path -Parent (Split-Path -Parent $lcmsSource)
  $lcmsMeta = Join-Path $lcmsRoot "conda-meta"
  if (Test-Path $lcmsMeta) {
    Copy-DirectoryContents -Source $lcmsMeta -Destination (Join-Path $docsRoot "lcms-conda-meta")
  }
  $lcmsDocs = Join-Path $lcmsRoot "Library\share\doc"
  if (Test-Path $lcmsDocs) {
    Copy-DirectoryContents -Source $lcmsDocs -Destination (Join-Path $docsRoot "lcms-doc")
  }

  Write-Host "Herramientas externas empaquetadas en: $toolsRoot"
}

function Install-AmazeBackend {
  if ([string]::IsNullOrWhiteSpace($RawpyDemosaicWheel)) {
    return
  }

  if (-not (Test-Path $RawpyDemosaicWheel)) {
    throw "No existe la wheel rawpy-demosaic indicada: $RawpyDemosaicWheel"
  }

  $wheelPath = (Resolve-Path $RawpyDemosaicWheel).Path
  Invoke-Native "Desinstalar backend RAW base" $Python @("-m", "pip", "uninstall", "-y", "rawpy", "rawpy-demosaic")
  Invoke-Native "Instalar backend AMaZE GPL3" $Python @("-m", "pip", "install", "--force-reinstall", $wheelPath)
}

function Test-AmazeBackend {
  if (-not $RequireAmaze -and [string]::IsNullOrWhiteSpace($RawpyDemosaicWheel)) {
    return
  }

  Invoke-Native "Verificar soporte AMaZE" $Python @("scripts\check_amaze_support.py")
}

function Copy-RawpyDemosaicLegal {
  param([string]$AppBuildDir)

  if (-not $RequireAmaze -and [string]::IsNullOrWhiteSpace($RawpyDemosaicWheel)) {
    return
  }

  $dest = Join-Path $AppBuildDir "docs\third_party\rawpy-demosaic"
  New-Item -ItemType Directory -Force -Path $dest | Out-Null

  if (-not [string]::IsNullOrWhiteSpace($RawpyDemosaicWheel) -and (Test-Path $RawpyDemosaicWheel)) {
    $wheelPath = (Resolve-Path $RawpyDemosaicWheel).Path
    $wheelHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $wheelPath).Hash
  } else {
    $wheelPath = $null
    $wheelHash = $null
  }

  $sourcePath = $RawpyDemosaicSource
  if ([string]::IsNullOrWhiteSpace($sourcePath)) {
    $sourcePath = Join-Path $Root "tmp\rawpy-demosaic"
  }
  if (Test-Path $sourcePath) {
    $sourcePath = (Resolve-Path $sourcePath).Path
    foreach ($file in @("LICENSE", "LICENSE.LibRaw", "README.md", "README.rst", "WINDOWS_COMPILE")) {
      $path = Join-Path $sourcePath $file
      if (Test-Path $path) {
        Copy-Item -LiteralPath $path -Destination (Join-Path $dest $file) -Force
      }
    }
    $thirdPartySources = @{
      "LibRaw" = @("COPYRIGHT", "LICENSE.CDDL", "LICENSE.LGPL", "README.md")
      "LibRaw-demosaic-pack-GPL2" = @("COPYRIGHT", "LICENSE", "README")
      "LibRaw-demosaic-pack-GPL3" = @("COPYRIGHT", "LICENSE.txt", "README", "Changelog")
      "rawspeed" = @("COPYING", "COPYING.LESSER", "README.md")
    }
    foreach ($entry in $thirdPartySources.GetEnumerator()) {
      $subdir = Join-Path $sourcePath ("external\" + $entry.Key)
      if (-not (Test-Path $subdir)) {
        continue
      }
      $subdest = Join-Path $dest ("external\" + $entry.Key)
      New-Item -ItemType Directory -Force -Path $subdest | Out-Null
      foreach ($file in $entry.Value) {
        $path = Join-Path $subdir $file
        if (Test-Path $path) {
          Copy-Item -LiteralPath $path -Destination (Join-Path $subdest $file) -Force
        }
      }
    }
    $commit = (& git -C $sourcePath rev-parse HEAD 2>$null)
    $submodules = (& git -C $sourcePath submodule status 2>$null)
    if ($submodules) {
      $submodules | Out-File -FilePath (Join-Path $dest "submodules.txt") -Encoding utf8
    }
  } else {
    $sourcePath = $null
    $commit = $null
  }

  $checkJson = (& $Python "scripts\check_amaze_support.py")
  if ($LASTEXITCODE -ne 0) {
    throw "No se pudo registrar AMaZE porque check_amaze_support.py fallo."
  }
  $check = $checkJson | ConvertFrom-Json

  $metadata = [ordered]@{
    rawpy_demosaic_wheel = $(if ($wheelPath) { Split-Path -Leaf $wheelPath } else { $null })
    rawpy_demosaic_wheel_sha256 = $wheelHash
    rawpy_demosaic_source = $(if ($commit) { "https://github.com/exfab/rawpy-demosaic/tree/$commit" } else { $null })
    rawpy_demosaic_source_commit = $commit
    source_url = "https://github.com/exfab/rawpy-demosaic"
    runtime_check = $check
  }
  $metadata | ConvertTo-Json -Depth 8 | Out-File -FilePath (Join-Path $dest "build-metadata.json") -Encoding utf8
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path

Set-Location $Root

if ([string]::IsNullOrWhiteSpace($Python)) {
  $Python = Join-Path $Root ".venv\Scripts\python.exe"
}

if (-not (Test-Path $Python)) {
  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($py) {
    Invoke-Native "Crear entorno virtual" $py.Source @("-3.12", "-m", "venv", ".venv")
  } else {
    Invoke-Native "Crear entorno virtual" "python" @("-m", "venv", ".venv")
  }
  $Python = Join-Path $Root ".venv\Scripts\python.exe"
}

Invoke-Native "Instalar dependencias de empaquetado" $Python @("-m", "pip", "install", "-e", ".[dev,gui,installer]")
Install-AmazeBackend
Test-AmazeBackend

if (-not $SkipTests) {
  Invoke-Native "Ejecutar tests" $Python @("-m", "pytest")
}

if (-not $SkipToolCheck) {
  $toolArgs = @("-m", "iccraw", "check-tools")
  if ($StrictExternalTools) {
    $toolArgs += "--strict"
  }
  Invoke-Native "Comprobar herramientas externas" $Python $toolArgs
}

if ([string]::IsNullOrWhiteSpace($Version)) {
  $Version = (& $Python -c "from iccraw.version import __version__; print(__version__)").Trim()
  if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($Version)) {
    throw "No se pudo leer la version de iccraw"
  }
}

if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
  $OutputRoot = Join-Path $Root "dist\windows"
}

$BuildRoot = Join-Path $Root "build\windows"
$PyInstallerWork = Join-Path $BuildRoot "pyinstaller"
$SpecPath = Join-Path $Root "packaging\windows\iccraw.spec"
$AppBuildDir = Join-Path $OutputRoot "ICCRAW"
$InstallerDir = Join-Path $OutputRoot "installer"

New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null
New-Item -ItemType Directory -Force -Path $BuildRoot | Out-Null
Remove-TreeUnderRoot -Root $Root -Target $AppBuildDir

Invoke-Native "Construir aplicacion con PyInstaller" $Python @(
  "-m", "PyInstaller",
  "--noconfirm",
  "--clean",
  "--distpath", $OutputRoot,
  "--workpath", $PyInstallerWork,
  $SpecPath
)

Copy-ExternalTools -AppBuildDir $AppBuildDir
Copy-RawpyDemosaicLegal -AppBuildDir $AppBuildDir

Invoke-Native "Smoke CLI empaquetada" (Join-Path $AppBuildDir "iccraw.exe") @("--version")
Invoke-Native "Smoke ayuda CLI empaquetada" (Join-Path $AppBuildDir "iccraw.exe") @("--help")
Invoke-Native "Smoke herramientas empaquetadas" (Join-Path $AppBuildDir "iccraw.exe") @("check-tools", "--strict")
if ($RequireAmaze) {
  Invoke-Native "Smoke AMaZE empaquetado" (Join-Path $AppBuildDir "iccraw.exe") @("check-amaze")
}

if (-not $NoInstaller) {
  $Iscc = Resolve-Iscc
  if (-not $Iscc) {
    throw "No se encontro ISCC.exe. Instala Inno Setup 6: winget install --id JRSoftware.InnoSetup -e"
  }

  New-Item -ItemType Directory -Force -Path $InstallerDir | Out-Null
  $IssPath = Join-Path $Root "packaging\windows\iccraw.iss"
  Invoke-Native "Construir instalador Inno Setup" $Iscc @(
    "/Qp",
    "/DRootDir=`"$Root`"",
    "/DAppBuildDir=`"$AppBuildDir`"",
    "/DOutputDir=`"$InstallerDir`"",
    "/DAppVersion=`"$Version`"",
    $IssPath
  )

  Write-Host "Instalador generado en: $InstallerDir"
} else {
  Write-Host "Aplicacion empaquetada en: $AppBuildDir"
}
