# Publicacion de instaladores

La publicacion de instaladores de NexoRAW tiene una regla simple: ningun
artefacto se sube al repositorio ni a GitHub Releases sin pasar primero las
validaciones de paquete e instalacion.

## Linux `.deb`

Construir siempre con AMaZE exigido:

```bash
NEXORAW_BUILD_AMAZE=1 NEXORAW_REQUIRE_AMAZE=1 bash packaging/debian/build_deb.sh
```

Validar el paquete antes de instalar o subir:

```bash
packaging/debian/validate_deb.sh dist/nexoraw_0.1.0~beta5_amd64.deb
sha256sum dist/nexoraw_0.1.0~beta5_amd64.deb > dist/nexoraw_0.1.0~beta5_amd64.deb.sha256
```

Validar en una instalacion real:

```bash
sudo apt purge iccraw nexoraw
sudo apt install ./dist/nexoraw_0.1.0~beta5_amd64.deb
scripts/validate_linux_install.sh
```

La validacion comprueba nombre `NexoRAW`, lanzadores `nexoraw`/`nexoraw-ui`,
ausencia de ejecutables heredados `iccraw`, icono hicolor completo, fallback
`/usr/share/pixmaps/nexoraw.png`, categoria de menu `Graphics;Photography`,
C2PA, herramientas externas y AMaZE.

## Windows

El instalador Windows debe generarse desde `packaging/windows/build_installer.ps1`
con `-RequireAmaze` y una wheel trazada cuando PyPI no ofrezca una compatible:

```powershell
.\packaging\windows\build_installer.ps1 -RawpyDemosaicWheel $wheel -RequireAmaze
```

El build no debe generar `iccraw.exe` ni `iccraw-ui.exe`. Los accesos directos
deben apuntar a `nexoraw-ui.exe` y usar el icono `nexoraw-icon.ico`.

## Releases

1. Ejecutar tests del proyecto.
2. Construir instaladores desde scripts versionados, no manualmente.
3. Ejecutar las validaciones de cada plataforma.
4. Generar `.sha256` despues de validar.
5. Subir solo los artefactos validados.
6. Si un asset publicado resulta defectuoso y GitHub no permite reemplazarlo,
   crear una revision nueva de la release y marcar la anterior con un aviso.
