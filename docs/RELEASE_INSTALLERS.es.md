# Publicacion de instaladores

La publicacion de instaladores de ProbRAW tiene una regla simple: ningun
artefacto se sube al repositorio ni a GitHub Releases sin pasar primero las
validaciones de paquete e instalacion.

## Linux `.deb`

Construir siempre con AMaZE exigido:

```bash
PROBRAW_BUILD_AMAZE=1 PROBRAW_REQUIRE_AMAZE=1 bash packaging/debian/build_deb.sh
```

Validar el paquete antes de instalar o subir:

```bash
packaging/debian/validate_deb.sh dist/probraw_<version>_amd64.deb
sha256sum dist/probraw_<version>_amd64.deb > dist/probraw_<version>_amd64.deb.sha256
```

Validar en una instalacion real:

```bash
sudo apt purge nexoraw iccraw probraw
sudo apt install ./dist/probraw_<version>_amd64.deb
scripts/validate_linux_install.sh
probraw --version
probraw check-tools --strict
probraw check-amaze
```

La validacion comprueba nombre `ProbRAW`, lanzadores `probraw`/`probraw-ui`,
ausencia de ejecutables heredados `nexoraw`/`iccraw`, icono hicolor completo, fallback
`/usr/share/pixmaps/probraw.png`, categoria de menu `Graphics;Photography`,
C2PA, herramientas externas y AMaZE.

Smoke GUI minimo antes de publicar:

- abrir ProbRAW desde el menu del sistema;
- confirmar que aparece en `Graficos/Fotografia` con icono ProbRAW;
- crear una sesion nueva y verificar carpetas `00_configuraciones/`, `01_ORG/`
  y `02_DRV/`;
- abrir la raiz del proyecto y confirmar que el navegador entra en `01_ORG/`;
- cambiar a otro proyecto y confirmar que no quedan miniaturas de la sesion
  anterior;
- seleccionar un RAW y comprobar que la miniatura muestra imagen, no solo icono
  generico;
- generar o guardar un perfil basico y confirmar mochila `RAW.probraw.json`;
- probar copiar/pegar perfil de ajuste entre dos miniaturas;
- revisar `Configuracion > Configuracion global` y confirmar deteccion o
  fallback del perfil ICC del monitor.

## Windows

El instalador Windows debe generarse desde `packaging/windows/build_installer.ps1`
con `-RequireAmaze` y una wheel trazada cuando PyPI no ofrezca una compatible:

```powershell
.\packaging\windows\build_installer.ps1 -RawpyDemosaicWheel $wheel -RequireAmaze
```

El build no debe generar `nexoraw.exe`, `nexoraw-ui.exe`, `iccraw.exe` ni
`iccraw-ui.exe`. Los accesos directos deben apuntar a `probraw-ui.exe` y usar el
icono `probraw-icon.ico`.

## Releases

1. Ejecutar tests del proyecto.
2. Ejecutar benchmarks de rendimiento/GUI cuando se hayan tocado preview,
   pipeline RAW, cache o paralelismo.
3. Actualizar `src/probraw/version.py`, `CHANGELOG.md`, README y documentacion
   de instaladores.
4. Construir instaladores desde scripts versionados, no manualmente.
5. Ejecutar las validaciones de cada plataforma.
6. Generar `.sha256` despues de validar.
7. Subir solo los artefactos validados.
8. Si un asset publicado resulta defectuoso y GitHub no permite reemplazarlo,
   crear una revision nueva de la release y marcar la anterior con un aviso.

## Release 0.3.5

La release 0.3.5 es una release de rendimiento y fiabilidad para flujos RAW de
tamaño profesional:

- el analisis MTF frio prepara una ROI a resolucion completa en un proceso
  externo y reutiliza una cache ROI persistente para recalculos posteriores,
- la barra superior de progreso es ahora el visor global unico para operaciones
  largas de preview, MTF y tareas de fondo, con tiempo transcurrido y ETA,
- la pestaña `Nitidez` ya no duplica una segunda barra local de progreso,
- el revelado de cola aplica la mochila de cada RAW cuando no hay id de perfil
  de ajuste registrado, de modo que nitidez, ruido, CA, color y contraste llegan
  al TIFF final,
- cambiar a una imagen sin configurar restablece controles de revelado y estado
  ICC activo a la politica neutra ProPhoto/balance-de-camara,
- los espacios genericos sin carta desactivan profiling mode/WB identidad para
  el render visible/final, y RGB de camara sin ICC de entrada se rechaza antes
  de escribir TIFF.

Artefactos esperados:

- `probraw_0.3.5_amd64.deb`
- `probraw_0.3.5_amd64.deb.sha256`
- `probraw-0.3.5.tar.gz`
- `probraw-0.3.5-py3-none-any.whl`
- `probraw_0.3.5_python_artifacts.sha256`

## Release 0.3.4

La release 0.3.4 publica el análisis MTF de nitidez persistente a resolución
completa:

- las curvas `ESF`, `LSF` y `MTF` de borde inclinado se guardan en la mochila
  sidecar de cada RAW,
- al reabrir una imagen se recuperan ROI y curvas sin seleccionar de nuevo el
  borde,
- el recálculo mapea la ROI del visor sobre la fuente real a resolución
  completa, evitando mediciones sobre miniaturas o previews reducidas,
- dos miniaturas seleccionadas con MTF guardada pueden compararse con curvas
  superpuestas y tabla numérica,
- actualizados el catálogo Qt en inglés y los manuales de usuario para las
  nuevas herramientas.

Artefactos esperados:

- `probraw_0.3.4_amd64.deb`
- `probraw_0.3.4_amd64.deb.sha256`
- `probraw-0.3.4.tar.gz`
- `probraw-0.3.4-py3-none-any.whl`
- `probraw_0.3.4_python_artifacts.sha256`

## Release 0.3.3

La release 0.3.3 consolida el flujo gráfico de sesión, ajustes y gestión de
color:

- estadísticas y sesiones recientes en `1. Sesión`,
- tercera columna organizada por flujo: color/calibración, ajustes
  personalizados y RAW/exportación,
- barra de herramientas horizontal del visor con iconos compactos y botón para
  enfocar/restaurar columnas laterales,
- histograma RGB colorimétrico fijo en `Ajustes personalizados`,
- curvas por canal y recuperación automática de datos de carta desde
  `profile_report.json`,
- manuales y capturas actualizados con la política de previsualización: ICC de
  entrada para interpretar la imagen, ICC del monitor solo como última capa de
  visualización.

Artefactos esperados:

- `probraw_0.3.3_amd64.deb`
- `probraw_0.3.3_amd64.deb.sha256`
- `probraw-0.3.3.tar.gz`
- `probraw-0.3.3-py3-none-any.whl`
- `probraw_0.3.3_python_artifacts.sha256`

## Release 0.3.2

La release 0.3.2 corrige el icono de la aplicacion en menus Linux:

- la entrada `.desktop` usa `Icon=/usr/share/pixmaps/probraw.png` como ruta
  absoluta para evitar fallos de cache/resolucion del tema hicolor,
- las validaciones del paquete y de instalacion comprueban ese icono real.

Artefactos esperados:

- `probraw_0.3.2_amd64.deb`
- `probraw_0.3.2_amd64.deb.sha256`
- `probraw-0.3.2.tar.gz`
- `probraw-0.3.2-py3-none-any.whl`
- `probraw_0.3.2_python_artifacts.sha256`

## Release 0.3.1

La release 0.3.1 actualiza la identidad visual de ProbRAW:

- nuevo logo e icono ProbRAW sin restos de la marca anterior,
- assets SVG, PNG e ICO regenerados para README, aplicacion e instaladores,
- artefactos de distribucion publicados con los nombres `probraw_*` /
  `probraw-*`.

Artefactos esperados:

- `probraw_0.3.1_amd64.deb`
- `probraw_0.3.1_amd64.deb.sha256`
- `probraw-0.3.1.tar.gz`
- `probraw-0.3.1-py3-none-any.whl`
- `probraw_0.3.1_python_artifacts.sha256`

## Release 0.3.0

La release 0.3.0 introduce:

- cambio completo de marca a ProbRAW en metadatos de paquete, identidad GUI,
  comandos, iconos, documentacion y nombres de artefactos de release,
- metadatos Debian de sustitucion/conflicto para paquetes beta anteriores
  `nexoraw` e `iccraw`,
- compatibilidad de migracion para `.nexoraw.json`, `.nexoraw.proof.json` y
  etiquetas beta C2PA/Proof,
- declaracion explicita del liderazgo de Probatia Forensics SL
  (https://probatia.com) en colaboracion con la Asociacion Espanola de Imagen
  Cientifica y Forense (https://imagencientifica.es).

## Release 0.2.6

La release 0.2.6 introduce:

- generación de perfiles avanzada en segundo plano para mantener la GUI
  responsiva,
- catálogo persistente de perfiles ICC de sesión con varias versiones activables,
- comparador `Gamut 3D` por pares para perfiles de sesión, monitor, perfiles
  estándar e ICC personalizados,
- gestión visual de referencias de carta, incluyendo importación, creación,
  validación y editor tabular Lab con muestras de color,
- artefactos de perfilado versionados en `00_configuraciones/profile_runs/`.

## Release 0.2.5

La release 0.2.5 introduce:

- estructura canonica del paquete Python bajo `src/probraw`,
- retirada del antiguo namespace interno de compatibilidad,
- division de la GUI en modulos mas pequenos por area de flujo,
- nombres de empaquetado Linux y Windows actualizados,
- etiquetas C2PA de asercion/accion generadas como `org.probatia.probraw.*`,
  manteniendo compatibilidad de verificacion con manifiestos beta anteriores,
- documentacion bilingüe actualizada y roadmap DCP+ICC archivado a favor del
  flujo activo centrado en ICC.

## Release 0.2.4

La release 0.2.4 introduce:

- selector de idioma de interfaz con autodeteccion del idioma del sistema,
- preferencia de idioma persistida mediante Qt settings,
- cambio de idioma mas seguro: se aplica al proximo arranque en lugar de
  reiniciar automaticamente la aplicacion.

## Release 0.2.3

La release 0.2.3 introduce:

- flujo sin carta con perfiles estandar reales en lugar de perfiles genericos
  generados por ProbRAW,
- seleccion preferente de `AdobeRGB1998.icc` cuando existe en el sistema,
- manifiestos ProbRAW Proof/C2PA con ajustes completos de receta, nitidez,
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
