param(
  [string]$Repository = "alejandro-probatia/ProbRAW",
  [string]$WikiDir = "tmp\probraw-wiki",
  [switch]$NoPush
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

function Convert-WikiPageName {
  param([string]$Name)
  $value = $Name.Trim()
  $value = $value -replace "\.es$", ""
  $value = $value -replace "_", "-"
  $value = $value.ToLowerInvariant()
  $textInfo = [System.Globalization.CultureInfo]::InvariantCulture.TextInfo
  $parts = $value -split "-"
  $title = ($parts | ForEach-Object {
    if ([string]::IsNullOrWhiteSpace($_)) {
      $_
    } elseif ($_ -match "^\d") {
      $_
    } else {
      $textInfo.ToTitleCase($_)
    }
  }) -join "-"
  return $title
}

function Convert-DocLinks {
  param(
    [string]$Content,
    [hashtable]$LinkMap,
    [string]$Repository
  )

  $repoUrl = "https://github.com/$Repository"
  return [regex]::Replace(
    $Content,
    "\]\(([^)\s]+)(#[^)]+)?\)",
    {
      param($match)
      $target = [System.Uri]::UnescapeDataString($match.Groups[1].Value)
      $anchor = $match.Groups[2].Value
      if ($target -match "^[a-zA-Z][a-zA-Z0-9+.-]*:") {
        return $match.Value
      }
      $normalized = ($target -replace "\\", "/").TrimStart("./")
      if ($LinkMap.ContainsKey($normalized)) {
        return "](" + $LinkMap[$normalized] + $anchor + ")"
      }
      if ($normalized.StartsWith("docs/assets/") -or $normalized.StartsWith("assets/")) {
        return "]($repoUrl/blob/main/$normalized$anchor)"
      }
      return $match.Value
    }
  )
}

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$wikiPath = Join-Path $root $WikiDir
$remoteUrl = "https://github.com/$Repository.wiki.git"

Set-Location $root

if (-not (Test-Path -LiteralPath $wikiPath)) {
  $parent = Split-Path -Parent $wikiPath
  New-Item -ItemType Directory -Force -Path $parent | Out-Null
  $previousErrorActionPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  $cloneOutput = & git clone $remoteUrl $wikiPath 2>&1
  $ErrorActionPreference = $previousErrorActionPreference
  if ($LASTEXITCODE -ne 0) {
    $message = ($cloneOutput | Out-String).Trim()
    if ($message -match "Repository not found") {
      throw @"
No se pudo clonar $remoteUrl.

GitHub informa que la wiki esta activada, pero el repositorio Git de la wiki
todavia no existe. Crea una primera pagina vacia en:

https://github.com/$Repository/wiki/_new

Despues vuelve a ejecutar:

.\scripts\sync_wiki.ps1
"@
    }
    throw $message
  }
} else {
  Invoke-Native "Actualizar repo wiki" "git" @("-C", $wikiPath, "pull", "--ff-only")
}

$pages = [ordered]@{
  "docs/MANUAL_USUARIO.es.md" = "Manual-de-usuario.md"
  "docs/METODOLOGIA_COLOR_RAW.es.md" = "Metodologia-RAW-e-ICC.md"
  "docs/COLOR_PIPELINE.es.md" = "Pipeline-de-color.md"
  "docs/ARCHITECTURE.es.md" = "Arquitectura.md"
  "docs/PERFORMANCE.es.md" = "Rendimiento.md"
  "docs/REPRODUCIBILITY.es.md" = "Reproducibilidad.md"
  "docs/PROBRAW_PROOF.es.md" = "ProbRAW-Proof.md"
  "docs/C2PA_CAI.es.md" = "C2PA-CAI.md"
  "docs/INTEGRACION_LIBRAW_ARGYLL.es.md" = "Integracion-LibRaw-ArgyllCMS.md"
  "docs/WINDOWS_INSTALLER.es.md" = "Instalador-Windows.md"
  "docs/MACOS_INSTALL.es.md" = "Instalacion-macOS.md"
  "docs/DEBIAN_PACKAGE.es.md" = "Paquete-Debian.md"
  "docs/RELEASE_INSTALLERS.es.md" = "Publicacion-de-instaladores.md"
  "docs/LEGAL_COMPLIANCE.es.md" = "Cumplimiento-legal.md"
  "docs/THIRD_PARTY_LICENSES.es.md" = "Licencias-de-terceros.md"
  "docs/AMAZE_GPL3.es.md" = "AMaZE-GPL3.md"
  "docs/DECISIONS.es.md" = "Decisiones.md"
  "docs/ROADMAP.es.md" = "Roadmap.md"
  "docs/COMPARISON.es.md" = "Comparacion.md"
  "docs/ISSUES.es.md" = "Incidencias.md"
  "docs/OPERATIVE_REVIEW_PLAN.es.md" = "Revision-operativa.md"
}

$linkMap = @{}
foreach ($entry in $pages.GetEnumerator()) {
  $linkMap[$entry.Key] = $entry.Value
  $linkMap[(Split-Path -Leaf $entry.Key)] = $entry.Value
}
$linkMap["README.es.md"] = "Home.md"
$linkMap["README.md"] = "Home.md"
$linkMap["CHANGELOG.es.md"] = "Changelog.md"
$linkMap["CHANGELOG.md"] = "Changelog.md"

$releasePages = @()
Get-ChildItem -Path (Join-Path $root "docs\releases") -Filter "*.es.md" | Sort-Object Name | ForEach-Object {
  $version = $_.BaseName -replace "\.es$", ""
  $page = "Release-$version.md"
  $relative = "docs/releases/$($_.Name)"
  $pages[$relative] = $page
  $linkMap[$relative] = $page
  $linkMap[$_.Name] = $page
  $releasePages += @{ Version = $version; Page = $page }
}

$homeContent = @"
# ProbRAW Wiki

Documentacion publica de ProbRAW generada desde los archivos versionados del
repositorio. La fuente canonica sigue estando en `docs/`; esta wiki facilita la
lectura y navegacion.

## Uso y metodologia

- [Manual de usuario](Manual-de-usuario)
- [Metodologia RAW e ICC](Metodologia-RAW-e-ICC)
- [Pipeline de color](Pipeline-de-color)
- [Rendimiento](Rendimiento)
- [Reproducibilidad](Reproducibilidad)

## Instalacion y releases

- [Instalador Windows](Instalador-Windows)
- [Instalacion macOS](Instalacion-macOS)
- [Paquete Debian](Paquete-Debian)
- [Publicacion de instaladores](Publicacion-de-instaladores)
- [Releases](Releases)
- [Changelog](Changelog)

## Trazabilidad y cumplimiento

- [ProbRAW Proof](ProbRAW-Proof)
- [C2PA / CAI](C2PA-CAI)
- [Cumplimiento legal](Cumplimiento-legal)
- [Licencias de terceros](Licencias-de-terceros)
- [AMaZE GPL3](AMaZE-GPL3)

## Desarrollo

- [Arquitectura](Arquitectura)
- [Integracion LibRaw + ArgyllCMS](Integracion-LibRaw-ArgyllCMS)
- [Decisiones](Decisiones)
- [Roadmap](Roadmap)
- [Comparacion](Comparacion)
- [Incidencias](Incidencias)
- [Revision operativa](Revision-operativa)
"@
$homeContent | Set-Content -LiteralPath (Join-Path $wikiPath "Home.md") -Encoding utf8

$changelog = Get-Content -Raw -LiteralPath (Join-Path $root "CHANGELOG.es.md")
$changelog = Convert-DocLinks -Content $changelog -LinkMap $linkMap -Repository $Repository
$changelog | Set-Content -LiteralPath (Join-Path $wikiPath "Changelog.md") -Encoding utf8

$releaseIndex = @("# Releases", "")
foreach ($release in ($releasePages | Sort-Object Version -Descending)) {
  $releaseIndex += "- [$($release.Version)]($([System.IO.Path]::GetFileNameWithoutExtension($release.Page)))"
}
$releaseIndex | Set-Content -LiteralPath (Join-Path $wikiPath "Releases.md") -Encoding utf8

foreach ($entry in $pages.GetEnumerator()) {
  $source = Join-Path $root ($entry.Key -replace "/", "\")
  if (-not (Test-Path -LiteralPath $source)) {
    Write-Warning "No existe documentacion fuente: $($entry.Key)"
    continue
  }
  $content = Get-Content -Raw -LiteralPath $source
  $content = Convert-DocLinks -Content $content -LinkMap $linkMap -Repository $Repository
  $content | Set-Content -LiteralPath (Join-Path $wikiPath $entry.Value) -Encoding utf8
}

Invoke-Native "Estado wiki" "git" @("-C", $wikiPath, "status", "--short")
& git -C $wikiPath diff --quiet
if ($LASTEXITCODE -eq 0) {
  Write-Host "Wiki sin cambios."
  return
}

Invoke-Native "Stage wiki" "git" @("-C", $wikiPath, "add", ".")
Invoke-Native "Commit wiki" "git" @("-C", $wikiPath, "commit", "-m", "Sincroniza documentacion ProbRAW")
if (-not $NoPush) {
  Invoke-Native "Push wiki" "git" @("-C", $wikiPath, "push", "origin", "master")
}
