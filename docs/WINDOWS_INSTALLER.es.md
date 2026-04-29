# Instalador Windows

Este documento deja preparado el flujo de construccion y pruebas para generar
un instalador Windows de ProbRAW.

## Alcance

El instalador Windows empaqueta la aplicacion Python con PyInstaller y genera un
`.exe` instalable con Inno Setup 6.

El instalador redistribuye la aplicacion Python y empaqueta las herramientas
externas criticas bajo `{app}\tools\...` para que el pipeline completo funcione
sin editar el `PATH` del sistema:

- ArgyllCMS: `colprof`, `xicclu`/`icclu` y `cctiff`.
- ExifTool: `exiftool`.
- `c2pa-python` y su libreria nativa `c2pa_c.dll` para leer e incrustar
  manifiestos C2PA cuando se exportan TIFFs finales.

Tambien copia en `{app}\docs\` el manual de usuario, la metodologia RAW/ICC, la
politica AMaZE, decisiones tecnicas, licencias y notas de release.

El diagnostico se comprueba con:

```powershell
probraw check-tools --strict
probraw check-c2pa
```

## Preparacion del entorno de desarrollo

Desde la raiz del repositorio:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev,gui,installer,c2pa]"
```

Instalar Inno Setup 6 para generar el instalador:

```powershell
winget install --id JRSoftware.InnoSetup -e
```

## Pruebas locales

Pruebas Python y diagnostico no estricto:

```powershell
.\scripts\run_checks.ps1
```

Pruebas con dependencias externas obligatorias:

```powershell
.\scripts\run_checks.ps1 -StrictExternalTools
```

En equipos donde falta `cctiff`, la suite Python puede pasar con una prueba
saltada, pero `-StrictExternalTools` debe fallar. Ese fallo es intencionado para
evitar publicar una release sin CMM operativo.

## Build de aplicacion sin instalador

Genera `dist\windows\ProbRAW\` con `probraw.exe` e `probraw-ui.exe`:

```powershell
.\packaging\windows\build_installer.ps1 -NoInstaller
```

## Build de instalador

Genera la aplicacion y despues el instalador:

```powershell
.\packaging\windows\build_installer.ps1
```

Artefacto esperado:

```text
dist\windows\installer\ProbRAW-<version>-Setup.exe
```

Para una preparacion de release, ejecutar con herramientas externas estrictas:

```powershell
.\packaging\windows\build_installer.ps1 -StrictExternalTools
```

La build de release exige AMaZE por defecto. Si `check-amaze` no informa
`DEMOSAIC_PACK_GPL3=True`, el script falla antes de generar el instalador.

## Build con AMaZE

AMaZE requiere un backend `rawpy` enlazado a LibRaw con
`DEMOSAIC_PACK_GPL3=True`. Los wheels estandar de `rawpy` no lo incluyen.

Si PyPI ofrece una wheel compatible de `rawpy-demosaic` para el Python de
empaquetado, la build la instala automaticamente:

```powershell
.\packaging\windows\build_installer.ps1 -Amaze -RequireAmaze
```

Si PyPI no ofrece una wheel compatible, usar el workflow manual:

```text
Build rawpy-demosaic Windows wheel
```

El artefacto descargado puede instalarse en el entorno local con:

```powershell
$wheel = (Get-ChildItem -Recurse .\tmp\wheels -Filter "rawpy_demosaic-*.whl" | Select-Object -First 1).FullName
.\scripts\install_amaze_backend.ps1 -Wheel $wheel
.\.venv\Scripts\python.exe -m probraw check-amaze
```

Para publicar un instalador que falle si AMaZE no queda activo:

```powershell
.\packaging\windows\build_installer.ps1 `
  -RawpyDemosaicWheel $wheel `
  -RequireAmaze
```

El instalador copia metadatos de build y avisos de `rawpy-demosaic` en
`{app}\docs\third_party\rawpy-demosaic\`.
El workflow de wheel usa por defecto el commit legacy `8b17075` de
`rawpy-demosaic`, con LibRaw 0.18.7 y `DEMOSAIC_PACK_GPL3=True`; conservar el
hash SHA256 de la wheel y los metadatos incluidos en el instalador forma parte
de la trazabilidad de release.

## Verificacion manual recomendada

En una maquina Windows limpia:

1. Instalar el `.exe`.
2. Abrir `ProbRAW` desde el menu inicio.
3. Ejecutar `Diagnostico herramientas` desde el grupo de accesos directos.
4. Confirmar:
   - `probraw --version`,
   - `probraw check-tools --strict`,
   - `probraw check-c2pa`,
   - `probraw check-amaze`,
   - `probraw-ui` arranca,
   - sliders y curva tonal responden sin bloquear la ventana durante el
     arrastre,
   - una prueba de `detect-chart`/`sample-chart` con `testdata` funciona,
   - una conversion `output_space=srgb` solo se aprueba si `cctiff` existe.

Benchmark GUI automatizado recomendado antes de publicar:

```powershell
$env:QT_QPA_PLATFORM="offscreen"
.\.venv\Scripts\python.exe scripts\benchmark_gui_interaction.py `
  --raw .\ruta\a\captura.NEF `
  --algorithm dcb `
  --full-resolution `
  --out .\tmp\gui_benchmark\release_ui.json
```

## Notas de mantenimiento

- La especificacion PyInstaller esta en `packaging/windows/probraw.spec`.
- La plantilla Inno Setup esta en `packaging/windows/probraw.iss`.
- El script `build_installer.ps1` instala los extras `dev`, `gui`,
  `installer` y `c2pa` antes de empaquetar.
- El instalador copia ArgyllCMS (`bin` y `ref`, incluyendo `sRGB.icm`) y ExifTool en
  `{app}\tools\...` y la aplicacion los resuelve desde ahi antes
  de consultar el `PATH` del sistema.
- Para publicar un instalador con AMaZE, usar `-RequireAmaze`; la build debe
  informar `rawpy.flags["DEMOSAIC_PACK_GPL3"] == True`.
- Si el usuario no configura un certificado C2PA externo, ProbRAW crea una
  identidad C2PA local y autoemitida bajo `%USERPROFILE%\.probraw\c2pa`.
  Los lectores C2PA pueden marcarla como `signingCredential.untrusted`; eso es
  esperado y significa que la firma no pertenece a una lista CAI central, no que
  falte el vinculo RAW-TIFF de ProbRAW.
- Los binarios generados quedan en `dist\windows\`; los temporales en
  `build\windows\`.
