# Instalador Windows beta

Este documento deja preparado el flujo de construccion y pruebas para generar
un instalador Windows de ICCRAW.

## Alcance

El instalador Windows empaqueta la aplicacion Python con PyInstaller y genera un
`.exe` instalable con Inno Setup 6.

El instalador redistribuye la aplicacion Python y empaqueta las herramientas
externas criticas bajo `{app}\tools\...` para que el pipeline completo funcione
sin editar el `PATH` del sistema:

- ArgyllCMS: `colprof` y `xicclu`/`icclu`.
- ExifTool: `exiftool`.
- LittleCMS: `tificc`.

El diagnostico se comprueba con:

```powershell
iccraw check-tools --strict
```

## Preparacion del entorno de desarrollo

Desde la raiz del repositorio:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev,gui,installer]"
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

En equipos donde falta `tificc`, la suite Python puede pasar con una prueba
saltada, pero `-StrictExternalTools` debe fallar. Ese fallo es intencionado para
evitar publicar una beta sin CMM operativo.

## Build de aplicacion sin instalador

Genera `dist\windows\ICCRAW\` con `iccraw.exe` e `iccraw-ui.exe`:

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
dist\windows\installer\ICCRAW-0.1.0b3-Setup.exe
```

Para una preparacion de release, ejecutar con herramientas externas estrictas:

```powershell
.\packaging\windows\build_installer.ps1 -StrictExternalTools
```

## Build con AMaZE

AMaZE requiere un backend `rawpy` enlazado a LibRaw con
`DEMOSAIC_PACK_GPL3=True`. Los wheels estandar de `rawpy` no lo incluyen.

Si PyPI no ofrece una wheel compatible de `rawpy-demosaic` para el Python de
empaquetado, usar el workflow manual:

```text
Build rawpy-demosaic Windows wheel
```

El artefacto descargado se instala en el entorno local con:

```powershell
$wheel = (Get-ChildItem -Recurse .\tmp\wheels -Filter "rawpy_demosaic-*.whl" | Select-Object -First 1).FullName
.\scripts\install_amaze_backend.ps1 -Wheel $wheel
.\.venv\Scripts\python.exe -m iccraw check-amaze
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
2. Abrir `ICCRAW` desde el menu inicio.
3. Ejecutar `Diagnostico herramientas` desde el grupo de accesos directos.
4. Confirmar:
   - `iccraw --version`,
   - `iccraw check-tools --strict`,
   - `iccraw-ui` arranca,
   - una prueba de `detect-chart`/`sample-chart` con `testdata` funciona,
   - una conversion `output_space=srgb` solo se aprueba si `tificc` existe.

## Notas de mantenimiento

- La especificacion PyInstaller esta en `packaging/windows/iccraw.spec`.
- La plantilla Inno Setup esta en `packaging/windows/iccraw.iss`.
- El script `build_installer.ps1` instala los extras `dev`, `gui` e
  `installer` antes de empaquetar.
- El instalador copia ArgyllCMS (`colprof`/`xicclu`), ExifTool y LittleCMS
  (`tificc`) en `{app}\tools\...` y la aplicacion los resuelve desde ahi antes
  de consultar el `PATH` del sistema.
- Para LittleCMS, si `tificc` no esta en `PATH`, el script acepta `-LcmsBin` o
  la variable `ICCRAW_LCMS_BIN` apuntando al directorio que contiene
  `tificc.exe` y sus DLLs.
- Para publicar un instalador con AMaZE, usar `-RequireAmaze`; la build debe
  informar `rawpy.flags["DEMOSAIC_PACK_GPL3"] == True`.
- Los binarios generados quedan en `dist\windows\`; los temporales en
  `build\windows\`.
