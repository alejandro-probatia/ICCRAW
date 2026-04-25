# Instalador Windows beta

Este documento deja preparado el flujo de construccion y pruebas para generar
un instalador Windows de ICCRAW.

## Alcance

El instalador Windows empaqueta la aplicacion Python con PyInstaller y genera un
`.exe` instalable con Inno Setup 6.

El instalador no redistribuye herramientas externas criticas. Para ejecutar el
pipeline completo en una maquina instalada, esas herramientas deben estar en
`PATH`:

- ArgyllCMS: `colprof` y `xicclu`/`icclu`.
- ExifTool: `exiftool`.
- LittleCMS: `tificc`.

Esto mantiene separada la aplicacion de binarios externos con licencias y ciclos
de actualizacion propios. El diagnostico se comprueba con:

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
- Para publicar un instalador con AMaZE, la wheel incluida debe informar
  `rawpy.flags["DEMOSAIC_PACK_GPL3"] == True`. Si se usa `rawpy-demosaic` o una
  wheel propia de LibRaw GPL3, incluir tambien los avisos GPL3/AGPL y la ruta
  de codigo fuente correspondiente descrita en `docs/AMAZE_GPL3.md`.
- Los binarios generados quedan en `dist\windows\`; los temporales en
  `build\windows\`.
