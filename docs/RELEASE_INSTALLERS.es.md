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
packaging/debian/validate_deb.sh dist/nexoraw_<version>_amd64.deb
sha256sum dist/nexoraw_<version>_amd64.deb > dist/nexoraw_<version>_amd64.deb.sha256
```

Validar en una instalacion real:

```bash
sudo apt purge iccraw nexoraw
sudo apt install ./dist/nexoraw_<version>_amd64.deb
scripts/validate_linux_install.sh
nexoraw --version
nexoraw check-tools --strict
nexoraw check-amaze
```

La validacion comprueba nombre `NexoRAW`, lanzadores `nexoraw`/`nexoraw-ui`,
ausencia de ejecutables heredados `iccraw`, icono hicolor completo, fallback
`/usr/share/pixmaps/nexoraw.png`, categoria de menu `Graphics;Photography`,
C2PA, herramientas externas y AMaZE.

Smoke GUI minimo antes de publicar:

- abrir NexoRAW desde el menu del sistema;
- confirmar que aparece en `Graficos/Fotografia` con icono NexoRAW;
- crear una sesion nueva y verificar carpetas `00_configuraciones/`, `01_ORG/`
  y `02_DRV/`;
- abrir la raiz del proyecto y confirmar que el navegador entra en `01_ORG/`;
- cambiar a otro proyecto y confirmar que no quedan miniaturas de la sesion
  anterior;
- seleccionar un RAW y comprobar que la miniatura muestra imagen, no solo icono
  generico;
- generar o guardar un perfil basico y confirmar mochila `RAW.nexoraw.json`;
- probar copiar/pegar perfil de ajuste entre dos miniaturas;
- revisar `Configuracion > Configuracion global` y confirmar deteccion o
  fallback del perfil ICC del monitor.

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
2. Ejecutar benchmarks de rendimiento/GUI cuando se hayan tocado preview,
   pipeline RAW, cache o paralelismo.
3. Actualizar `src/nexoraw/version.py`, `CHANGELOG.md`, README y documentacion
   de instaladores.
4. Construir instaladores desde scripts versionados, no manualmente.
5. Ejecutar las validaciones de cada plataforma.
6. Generar `.sha256` despues de validar.
7. Subir solo los artefactos validados.
8. Si un asset publicado resulta defectuoso y GitHub no permite reemplazarlo,
   crear una revision nueva de la release y marcar la anterior con un aviso.

## Release 0.2.3

La release 0.2.3 introduce:

- flujo sin carta con perfiles estandar reales en lugar de perfiles genericos
  generados por NexoRAW,
- seleccion preferente de `AdobeRGB1998.icc` cuando existe en el sistema,
- manifiestos NexoRAW Proof/C2PA con ajustes completos de receta, nitidez,
  contraste/render y gestion de color,
- visor de metadatos ampliado para mostrar esos ajustes reproducibles.

## Release 0.2.2

La release 0.2.2 introduce:

- multiprocessing real por proceso en `batch-develop`,
- cache numerica opt-in de demosaico,
- tests golden de hashes canonicos,
- benchmarks reproducibles de RAW y GUI,
- refresco final de preview en segundo plano para evitar lag al soltar
  sliders/curva,
- heuristica de RAM por worker ajustada con RAW Nikon D850 real.
