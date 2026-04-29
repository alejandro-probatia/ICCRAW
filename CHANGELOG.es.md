# Changelog

Todos los cambios relevantes de ProbRAW se documentan en este archivo.

Este proyecto sigue:

- formato inspirado en Keep a Changelog,
- versionado SemVer,
- trazabilidad de cambios orientada a uso científico y forense.

## Política de actualización

Para mantener trazabilidad completa, cada cambio debe:

1. añadir una línea en `Unreleased` antes de merge/push,
2. mover entradas a una versión fechada en cada release,
3. referenciar, cuando aplique, impacto en reproducibilidad, legalidad o cadena de custodia.

## [Unreleased]

### Fixed

- El visor `Gamut 3D` reinicia camara y zoom cuando cambian los perfiles o la
  malla Lab, evitando que una vista anterior con elevacion extrema haga parecer
  el gamut estirado hasta reiniciar la aplicacion.

## [0.3.2] - 2026-04-29

### Fixed

- La entrada de escritorio Linux usa ahora el pixmap absoluto
  `/usr/share/pixmaps/probraw.png` para que Cinnamon y otros menus muestren el
  icono de ProbRAW aunque no refresquen correctamente el tema hicolor.
- Actualizadas las validaciones de instalacion y paquete para comprobar el icono
  real del menu.

## [0.3.1] - 2026-04-29

### Changed

- Sustituida la identidad grafica anterior por un nuevo logo e icono ProbRAW
  basados en una marca `P`, geometria RAW y parches de calibracion de color.
- Regenerados los assets SVG, PNG e ICO usados en README, aplicacion,
  instaladores Linux/Windows y paquete distribuible.

## [0.3.0] - 2026-04-29

### Changed

- Renombrado el proyecto y la identidad visible de la aplicacion a ProbRAW para
  evitar conflicto de marca con proyectos existentes.
- Renombrados paquete Python, lanzadores CLI, archivos desktop, iconos, capturas
  y artefactos de release al nombre canonico `probraw`.
- Actualizados metadatos de repositorio, instaladores y actualizaciones hacia
  `alejandro-probatia/ProbRAW`.
- Declarado el liderazgo del proyecto por Probatia Forensics SL
  (https://probatia.com) en colaboracion con la Asociacion Espanola de Imagen
  Cientifica y Forense (https://imagencientifica.es).

### Compatibility

- Los nuevos sidecars RAW se escriben como `RAW.probraw.json`, pero los
  `RAW.nexoraw.json` y `RAW.iccraw.json` existentes se siguen leyendo y se
  migran al guardar de nuevo la sesion.
- Los nuevos sidecars de prueba se escriben como `.probraw.proof.json`, pero
  `.nexoraw.proof.json` y `.iccraw.proof.json` siguen siendo legibles.
- La verificacion C2PA y Proof acepta etiquetas de asercion y variables de
  entorno de betas anteriores como fallback de migracion.
- Los paquetes Linux declaran `Replaces/Conflicts: nexoraw, iccraw` y no instalan
  lanzadores heredados.

## [0.2.6] - 2026-04-29

### Added

- Diagnóstico `Gamut 3D` en la pestaña de diagnóstico para comparar por pares el
  ICC de sesión, el perfil del monitor, perfiles estándar (`sRGB`, `Adobe RGB
  (1998)`, `ProPhoto RGB`) e ICC externos.
- Catálogo persistente de perfiles ICC por sesión con activación explícita,
  soporte para varias versiones generadas y recarga desde `session.json`.
- Gestión de referencias de carta desde la interfaz: catálogo de referencias
  incluidas, importación de JSON externos, referencias personalizadas de sesión y
  validación.
- Editor tabular de referencias Lab con muestras de color por parche para crear
  JSON de cartas personalizadas sin editar el archivo a mano.

### Changed

- La generación avanzada de perfiles registra artefactos versionados en
  `00_configuraciones/profile_runs/` y conserva los perfiles ICC generados en
  `00_configuraciones/profiles/`.
- La ejecución de perfilado se lanza en segundo plano desde la GUI para evitar
  que crear un perfil deje la aplicación bloqueada durante un buen rato.
- Los argumentos por defecto de ArgyllCMS incluyen `-u -R` para reducir gamuts
  ICC de cámara claramente irreales.
- Manual de usuario y capturas actualizados con el flujo de referencias, perfiles
  ICC de sesión y comparación Gamut 3D.

## [0.2.5] - 2026-04-29

### Changed

- Reorganizada la base de codigo alrededor del paquete canonico `probraw` y
  retirada la antigua implementacion interna bajo el namespace `iccraw`.
- Dividida la interfaz en modulos UI/window mas pequenos para facilitar el
  mantenimiento de sesiones, preview, perfiles y cola de revelado.
- Actualizados tests, scripts, instaladores y documentacion activa para usar de
  forma consistente el paquete y los lanzadores `probraw`.
- Las nuevas salidas C2PA usan etiquetas de asercion/accion
  `org.probatia.probraw.*`; la verificacion mantiene compatibilidad con
  manifiestos beta anteriores `org.probatia.iccraw.*`.

## [0.2.4] - 2026-04-28

### Added

- Selector de idioma de la interfaz en `Configuracion global -> General`, con
  opciones `Sistema (Auto: es/en)`, `Espanol` e `English`. Persiste en
  `QSettings` bajo `app/language`.
- Auto-deteccion del idioma del sistema operativo en instalaciones nuevas: si
  el SO esta en espanol arranca en espanol, en cualquier otro idioma arranca
  en ingles. No se migra a usuarios existentes con `app/language=es` ya
  guardado para respetar la eleccion previa.
- Helpers `probraw.i18n.detect_system_language` y `probraw.i18n.resolve_language`
  con tests unitarios en `tests/test_i18n.py`.

### Changed

- El cambio de idioma desde la configuracion no reinicia automaticamente la
  aplicacion: muestra un aviso y se aplica al proximo arranque, evitando
  perdida de estado de sesion no guardado.

## [0.2.3] - 2026-04-27

### Changed

- El flujo sin carta deja de generar perfiles `ProbRAW generic ...`: el RAW se
  revela en un espacio RGB estandar real (`sRGB`, `Adobe RGB (1998)` o
  `ProPhoto RGB`) con LibRaw y se incrusta un ICC estandar copiado del sistema o
  de ArgyllCMS.
- Los manifiestos de render registran `raw_color_pipeline`, indicando si la
  transformacion de color la resolvio LibRaw, el ICC de sesion o ArgyllCMS/CMM.
- ProbRAW Proof/C2PA declaran los ajustes completos aplicados (`recipe`,
  detalle/nitidez, contraste/render y gestion de color); el hash de ajustes
  queda como control de integridad, no como unico dato visible para auditoria.

### Added

- Tests de perfiles estandar reales para evitar que Adobe RGB caiga en un
  perfil compatible cuando existe `AdobeRGB1998.icc`.

## [0.2.2] - 2026-04-27

### Added

- `scripts/profile_pipeline.py` para perfilar comandos reales con `cProfile`
  y, si esta instalado, generar flamegraph con `py-spy`.
- `scripts/benchmark_raw_pipeline.py` para benchmark multiplataforma de
  demosaico, cache numerica y escalado por procesos con RAWs reales.
- `scripts/benchmark_gui_interaction.py` para medir fluidez de sliders y curva
  tonal en Qt con RAW real o fuente sintetica.
- Flags `--workers` en `batch-develop` y `auto-profile-batch` para fijar el
  paralelismo sin depender de variables de entorno.
- Flag `--cache-dir` en `develop`, `batch-develop` y `auto-profile-batch` para
  ubicar la cache numerica de demosaico cuando la receta active
  `use_cache: true`.
- Cache persistente de demosaico RAW en arrays `.npy`, opt-in por receta,
  con clave basada en SHA-256 completo del RAW y parametros LibRaw que afectan
  a la escena lineal.
- Tests golden de hashes canonicos en `tests/regression/` y script
  `scripts/regenerate_golden_hashes.py` para regenerarlos de forma explicita.

### Changed

- El analisis de preview e histogramas de GUI muestrea antes de convertir y
  recortar arrays grandes, reduciendo copias de memoria en imagenes 1:1.
- `batch-develop` usa multiprocessing real por proceso cuando `workers > 1`;
  conserva fallback a hilos solo si se inyecta un cliente C2PA no serializable.
- Los proyectos nuevos disponen de `00_configuraciones/cache/` como ubicacion
  persistente de cache por sesion.
- La estimacion automatica de RAM por worker de batch pasa a 2800 MiB para
  reflejar RAWs de alta resolucion y escritura TIFF real.
- `write_tiff16` reduce temporales de NumPy usando operaciones `out=`, bajando
  tiempo y pico de RAM durante la escritura TIFF16.
- El refresco final de preview tras arrastrar sliders/curva se encola en
  segundo plano para imagenes grandes cuando no hay preview ICC activo,
  evitando bloqueos perceptibles del hilo Qt.

### Fixed

- Las llamadas basicas a `exiftool` y `git rev-parse` usadas para metadatos y
  contexto de ejecucion tienen timeout para evitar bloqueos indefinidos.

## [0.2.1] - 2026-04-27

### Added

- GUI `Ayuda > Acerca de` ampliada con:
  - director del proyecto configurable (`PROBRAW_PROJECT_DIRECTOR`),
  - version en ejecucion,
  - estado operativo de AMaZE,
  - comprobacion de ultima version publicada en GitHub Releases,
  - actualizacion automatica que descarga y lanza el instalador de release.
- Nuevo modulo `probraw.update` para consulta de releases, comparacion de
  versiones, descarga de assets y ejecucion de instaladores por plataforma.
- Histograma RGB en la pestaña `Visor` con lectura de clipping en sombras y
  luces y testigos visuales.
- Overlay de clipping en la imagen de preview (azul sombras, rojo luces,
  magenta cuando coinciden), activable desde `Visor`.
- Tests unitarios para el sistema de actualizacion (`tests/test_update.py`).

### Changed

- El script Windows `packaging/windows/build_installer.ps1` exige AMaZE por
  defecto para builds de release (escape explicito: `-AllowNoAmaze` para builds
  de prueba).

## [0.2.0] - 2026-04-26

### Added

- Manual de usuario orientado a instaladores y flujos GUI, con capturas
  actualizadas para sesion, flujo con carta, flujo sin carta, mochilas,
  cola de revelado, metadatos y configuracion global.
- Flujo documentado para sesiones sin carta: perfil de revelado manual con ICC
  generico de salida (`sRGB`, `Adobe RGB (1998)` o `ProPhoto RGB`) y mochila
  `RAW.probraw.json` por imagen.
- Paquete Debian de release `0.2.0`, instalable como aplicacion ProbRAW con
  lanzadores `probraw`/`probraw-ui`, iconos hicolor y AMaZE validado en build.

### Changed

- El manual deja de explicar instalacion desde codigo y dependencias manuales;
  la instalacion de usuario se considera cubierta por instaladores
  multiplataforma.
- La GUI trata los perfiles como ajustes asignados a RAW: perfil avanzado desde
  carta marcado en azul y perfil basico/manual marcado en verde, ambos
  copiables y pegables desde miniaturas.
- La columna derecha de `2. Ajustar / Aplicar` abandona el modelo de
  "calibrar sesion" y agrupa los ajustes parametricos por archivo en
  `Brillo y contraste`, `Color`, `Nitidez`, `Gestión de color y calibración` y
  `RAW Global`.
- La tira de miniaturas funciona como scroll horizontal con tamaño ajustable y
  genera miniaturas visuales para RAW aunque no exista preview embebida,
  usando un revelado rápido cacheado.
- Se elimina la cabecera persistente con nombre/subtítulo de la aplicación para
  recuperar espacio vertical de trabajo.
- La elección de directorio de proyecto es más reactiva: el árbol vigila cambios
  del sistema, una raíz de proyecto abre `01_ORG/` para navegar RAW y
  `Usar carpeta actual` promueve `01_ORG/` a su raíz de proyecto.
- La estructura de proyectos nuevos se simplifica a `00_configuraciones/`,
  `01_ORG/` y `02_DRV/`; las sesiones heredadas con `config/session.json`
  siguen abriendose sin conversion destructiva.

### Fixed

- GUI: crear o abrir una sesion nueva ya no hereda rutas, miniaturas, cola ni
  perfiles de revelado de la sesion anterior; las rutas persistidas fuera de la
  raiz de proyecto se migran a la estructura propia de la sesion.
- GUI: las miniaturas y selecciones que aun apunten a rutas heredadas
  `raw/archivo` se resuelven automaticamente contra `01_ORG/archivo`, evitando
  tracebacks al abrir proyectos migrados.
- GUI: al generar un perfil desde carta, el perfil avanzado queda asignado a los
  RAW de carta mediante su mochila `RAW.probraw.json`.

## [0.1.0-beta.5] - 2026-04-25

### Changed

- El nombre visible del proyecto pasa a ser ProbRAW. Se añaden entry points
  `probraw`/`probraw-ui`, con alias heredados temporales para scripts beta
  existentes. Esos alias se retiran en 0.2.5.
- CMM unificado en ArgyllCMS: se sustituye LittleCMS (`tificc`) por
  `cctiff`/`xicclu` para conversion ICC de salida, validacion y preview de
  perfil. Desaparecen las dependencias `liblcms2-utils` y `Pillow.ImageCms` del
  flujo principal.
- `apply_profile_preview` reconstruye la previsualizacion ICC a partir de un
  LUT 17^3 calculado con `xicclu` e interpolacion trilineal cacheada por
  perfil; se elimina la dependencia del sidecar `.profile.json` para mostrar
  preview con perfil activo.
- `build_profile` reporta DeltaE 76/2000 a partir del ICC real generado por
  `colprof` (consultando `xicclu`). La matriz lateral
  `matrix_camera_to_xyz` se conserva solo como diagnostico
  (`diagnostic_matrix_*`).
- `auto_generate_profile_from_charts` aplica un guard cientifico estricto:
  rechaza recetas con `denoise`, `sharpen` o `tone_curve` activos, o con
  `output_linear=False` u `output_space` distinto de RGB de camara lineal.
- Las capturas de carta para perfilado se restringen a RAW/DNG/TIFF lineal;
  PNG/JPG ya no se aceptan ni en CLI ni en GUI.
- Refactor array-first del workflow de perfilado: `_collect_chart_samples` y
  `_collect_chart_geometries` usan `develop_image_array` y variantes
  `detect_chart_from_array` / `sample_chart_from_array` /
  `draw_detection_overlay_array`, evitando roundtrips a TIFF.
- El instalador Windows empaqueta `tools/argyll/ref/` (incluido `sRGB.icm`)
  para que la conversion ICC funcione sin perfiles externos. Se elimina la
  copia de binarios y metadata de LittleCMS.
- Paquete Debian: se elimina `liblcms2-utils` de las dependencias declaradas.
- `probraw check-tools` requiere `cctiff` (ArgyllCMS) en lugar de `tificc`.

### Fixed

- GUI: el histograma del editor de curvas tonales se recalcula solo cuando
  cambia la imagen base, evitando recomputos en cada movimiento de curva.
- GUI: el marcado manual de cuatro esquinas de carta sobrevive a recargas
  asincronas de la imagen seleccionada.
- GUI: la previsualizacion con perfil ICC ya no requiere `*.profile.json`
  asociado; un fallo de `xicclu` se registra como aviso y se cae a vista sin
  perfil sin bloquear el visor.

## [0.1.0-beta.4] - 2026-04-25

### Changed

- El instalador Windows AMaZE incluye metadata de distribucion
  `rawpy-demosaic` dentro del ejecutable PyInstaller para que
  `probraw check-amaze` informe el backend exacto.
- El empaquetado Windows copia avisos/licencias de `rawpy-demosaic`, LibRaw,
  los demosaic packs GPL2/GPL3 y RawSpeed, junto con hash de wheel y commit de
  fuente.

### Fixed

- Soporte operativo de AMaZE en Windows mediante wheel GPL3 de
  `rawpy-demosaic 0.10.1` enlazada a LibRaw 0.18.7 con
  `DEMOSAIC_PACK_GPL3=True`.

## [0.1.0-beta.3] - 2026-04-25

### Added

- Funcion `develop_image_array` para render RAW/TIFF array-first y benchmark
  basico de preview/render en `scripts/benchmark_pipeline.py`.
- Script `scripts/check_amaze_support.py` para auditar si el entorno LibRaw/rawpy
  incluye el demosaic pack GPL3 necesario para AMaZE.
- Preparado el flujo de empaquetado Windows con scripts PowerShell,
  PyInstaller, plantilla Inno Setup y documentacion de pruebas.

### Changed

- Preview de alta calidad, exportacion batch y rutas GUI de revelado evitan
  TIFF temporales cuando no son necesarios.
- La preview RAW en modo camera RGB/perfilado aplica una normalizacion visual
  solo para el visor, evitando dominantes verdes al marcar cartas sin alterar
  TIFFs auditados, muestreo ni exportacion.
- Las opciones de generacion ICC (`colprof`, calidad, formato y salida) y los
  criterios `RAW global` se muestran dentro de `Calibrar sesion`, antes de
  iniciar la calibracion.
- Politica AMaZE/GPL3 documentada: ProbRAW mantiene `AGPL-3.0-or-later`, registra
  flags de `rawpy` y solo habilita AMaZE cuando `DEMOSAIC_PACK_GPL3=True`.
- El instalador Windows empaqueta herramientas externas del flujo completo
  (`colprof`/`xicclu`, `exiftool` y `tificc`) bajo `tools/`.
- La GUI carga automáticamente la previsualización al seleccionar miniaturas y
  añade una barra superior de progreso para tareas largas.
- El visor permite zoom, reencuadre por arrastre y rotación de 90 grados.
- Nuevos paneles verticales de procesado: calibracion con criterios RAW,
  corrección básica, detalle, perfil activo y aplicación de sesión.
- Corrección básica de preview/lote: iluminante final, temperatura, matiz,
  brillo, niveles, contraste y curva de medios.
- Ajustes de detalle de preview/lote: reducción de ruido de luminancia/color,
  nitidez y corrección de aberración cromática lateral.

- El backend RAW pasa completamente de `dcraw` a LibRaw/rawpy, con DCB como
  demosaicing por defecto instalable y AMaZE disponible solo en builds de
  rawpy/LibRaw con demosaic pack GPL3.
- Se eliminan botones redundantes de carga manual en el visor; la selección de
  miniatura pasa a ser la acción principal.

### Fixed

- Compatibilidad con ArgyllCMS en Windows cuando `colprof` genera `.icm` en
  lugar de `.icc`.
- El backend RAW informa de forma explicita cuando una receta pide AMaZE sin
  demosaic pack GPL3; la GUI evita el bloqueo degradando a `dcb` con aviso.
- La generacion de perfil desde GUI reutiliza automaticamente las cuatro
  esquinas manuales pendientes, aunque aun no se haya guardado el JSON de
  deteccion manual.
- Las sesiones ya no restauran rutas temporales heredadas de ejecuciones de
  tests como rutas operativas de cartas, receta, perfiles o lote.
- La memoria persistente de la GUI recuerda ultima sesion/carpeta valida,
  ignora rutas obsoletas y usa la home del usuario como directorio inicial
  portable en Linux, macOS y Windows.

## [0.1.0-beta.2] - 2026-04-25

### Fixed

- La referencia ColorChecker 2005 D50 se empaqueta dentro de `probraw` y se usa
  como fallback cuando la GUI/CLI se ejecuta desde una instalacion `.deb` sin el
  arbol `testdata/` del repositorio.

## [0.1.0-beta.1] - 2026-04-24

### Changed

- La GUI migra rutas heredadas de `/tmp` a la estructura de la sesión:
  perfiles en `profiles/`, reportes/recetas en `config/`, trabajo en `work/`
  y TIFF/preview en `exports/`.
- `batch-develop` separa gestion ICC en modos explicitos:
  - RGB de camara con perfil ICC de entrada incrustado,
  - conversion a sRGB mediante LittleCMS (`tificc`) con perfil sRGB incrustado.
- La GUI reabre la ultima sesion usada y posiciona el explorador en el
  directorio operativo de la sesion en lugar de arrancar siempre en `$HOME`.
- `validate-profile` valida el perfil ICC real con ArgyllCMS (`xicclu`/`icclu`)
  en lugar de calcular DeltaE con la matriz lateral del sidecar.
- La deteccion de carta por fallback queda marcada como modo `fallback`, con
  confianza baja y bloqueo por defecto en flujos automaticos.
- El muestreo de carta aplica `sampling_trim_percent` y
  `sampling_reject_saturated` desde la receta.
- Las referencias de carta cargadas desde JSON se validan en modo estricto
  (fuente, D50, observador 2 grados, ids únicos y Lab completo).
- Nuevo comando `export-cgats` para exportar muestras a CGATS/CTI3 interoperable.
- La matriz `matrix_camera_to_xyz` queda como artefacto diagnostico/compatibilidad,
  no como sustituto de la conversion ICC en exportacion de lote ni de la
  validacion del perfil.
- Las recetas de ejemplo pasan de `demosaic_algorithm: rcd` a `ahd`, el modo
  soportado por `dcraw`.
- La GUI deja de ofrecer algoritmos de demosaicing que el backend `dcraw` no
  puede ejecutar.
- Reorganización estructural del proyecto para crecer como base Python única:
  - eliminada la capa Rust (`Cargo.toml`, `Cargo.lock`, `core/`, `cli/` Rust, `tests/` Rust) que ya no se usaba,
  - paquete renombrado `icc_entrada` → `iccraw` alineado con el nombre del repo y del proyecto,
  - código organizado en subpaquetes por dominio: `core/`, `raw/`, `chart/`, `profile/`,
  - `__version__` centralizado en `iccraw/version.py` y expuesto por `__init__.py`,
  - entry points CLI/GUI renombrados a `iccraw` y `iccraw-ui`,
  - `python -m iccraw` operativo vía `__main__.py`,
  - tests unificados en `tests/` (antes `tests_py/`) con imports actualizados,
  - docs duplicadas eliminadas de la raíz (canónicas en `docs/`), rutas absolutas Linux sustituidas por relativas en README.

### Added

- Paquete Debian beta `0.1.0~beta1` con instalacion en `/opt/iccraw`,
  lanzadores `/usr/bin/iccraw` y `/usr/bin/iccraw-ui`, y dependencias externas
  declaradas para `dcraw`, ArgyllCMS, LittleCMS y `exiftool`.
- Script reproducible `packaging/debian/build_deb.sh` para construir el `.deb`
  desde el arbol de trabajo.
- Validacion estricta de `demosaic_algorithm` para backend `dcraw`; una receta
  con algoritmo no soportado falla antes de procesar.
- Integracion de LittleCMS (`tificc`) como CMM externo para conversion ICC a
  sRGB.
- Metadatos de modo de gestion de color en manifiestos de lote.
- Tests P0 para demosaicing no soportado, `audit_linear_tiff` realmente lineal y
  exportacion ICC/CMM.
- Tests P0 que demuestran que `validate-profile` usa el ICC real aunque exista
  un sidecar con matriz incorrecta.
- Tests P1 para deteccion fallback de baja confianza y muestreo controlado por
  parametros de receta.
- Tests P1 para rechazo de referencias de carta incompletas/incompatibles.
- Tests P1 para exportacion CGATS/CTI3 de muestras.
- El reporte QA de sesion incluye peores parches y outliers DeltaE2000 por
  parche para diagnosticar desviaciones cromaticas localizadas.
- El QA de sesion incorpora diagnostico de captura por carta: luminancia de
  parches, bajo nivel, dispersion densitometrica de la fila neutra y gradiente
  estimado de iluminacion.
- Los perfiles de sesion declaran estado operacional `draft`, `validated`,
  `rejected` o `expired`, con vigencia opcional desde CLI.
- `auto-profile-batch` no aplica a lote perfiles de sesion `rejected` o
  `expired`.
- Nuevo comparador de reportes QA entre sesiones (`compare-qa-reports`) con
  resumen de estados, DeltaE, outliers, checks nuevos/resueltos y acceso desde
  la GUI.
- Nuevo diagnostico de herramientas externas (`check-tools`) con salida JSON y
  acceso desde GUI para comprobar `dcraw`, ArgyllCMS, LittleCMS y `exiftool`.
- Plantilla de mantenimiento continuo del changelog y política de actualización.
- Módulo `preview` para carga de imagen/RAW en previsualización, ajustes técnicos y análisis lineal.
- GUI nueva basada en Qt/PySide6 (`app-ui`, `app-ui-qt`) con:
  - previsualización técnica con perfil ICC,
  - ajustes de nitidez y reducción de ruido,
  - ejecución de flujo automático carta -> perfil -> lote.
- Dependencia opcional `gui` en `pyproject.toml`.
- Script `scripts/run_ui_qt.sh`.
- Navegador visual de directorios y miniaturas RAW/imagen integrado en GUI para selección de archivos clave.
- Acción GUI para revelar archivo seleccionado a TIFF 16-bit con perfil ICC opcional.
- Ajustes de ruido separados en luminancia y color.
- Menu superior en GUI con accesos a configuracion y operaciones (`Archivo`, `Configuracion`, `Perfil ICC`, `Vista`, `Ayuda`).
- Soporte de exploracion multiunidad en GUI para navegar el arbol completo del sistema de archivos.
- Panel de configuracion RAW ampliado (demosaic, WB, black/white level, tone curve, espacios, sampling, profiling mode).
- Panel de configuracion de perfil ICC ampliado (tipo `-a`, calidad `-q`, args extra `colprof`, formato `.icc/.icm`).
- Optimizacion de carga y previsualizacion RAW/DNG:
  - modo rapido con miniatura embebida o decodificacion `dcraw -h`,
  - downscale configurable de preview para reducir latencia en archivos grandes,
  - cache de previews por archivo+recipe para recargas inmediatas.
- Nueva función de backend `auto_generate_profile_from_charts` para generar perfil ICC sin ejecutar batch.
- Reorganización funcional en 3 pestañas principales:
  - Generación Perfil ICC,
  - Revelado RAW,
  - Monitoreo Flujo.
- Revelado por lotes integrado en pestaña de Revelado RAW (selección o directorio completo).
- Nuevo módulo `session` para gestión persistente de sesiones con creación de estructura de directorios:
  - `charts/`, `raw/`, `profiles/`, `exports/`, `config/`, `work/`.
- Nueva pestaña `1. Sesión` para crear/abrir/guardar sesión con metadatos de iluminación y toma.
- Nueva pestaña `3. Cola de Revelado` con cola de archivos, estado por imagen y ejecución de lote desde cola.
- Persistencia de estado por sesión en `config/session.json`:
  - rutas operativas,
  - configuración de revelado/perfil,
  - perfil activo,
  - cola de revelado.
- Test unitario `tests_py/test_session.py` para estructura, carga y normalización de sesión.

### Changed

- Se reemplaza completamente la GUI anterior (tkinter) por implementación Qt.
- `apply_profile_matrix` pasa a API pública en `icc_entrada.export` para reutilización en previsualización.
- Documentación y roadmap actualizados para reflejar GUI Qt y política legal AGPL + dependencias.
- Rediseño de GUI a layout de 3 paneles (explorador, visor principal, panel de control) priorizando espacio de imagen y flujo práctico de producción.
- Reorganizacion de GUI para flujo de trabajo tipo revelador RAW (navegacion, seleccion visual y maximo espacio para imagen).
- Renombrada pestaña de ajustes visuales de `Vista` a `Nitidez`.
- El flujo de perfilado y el flujo de revelado por lotes se separan explícitamente para mayor claridad operativa.
- La previsualización aplica perfil ICC desactivado por defecto para evitar dominantes cuando el perfil no corresponde al set cámara+iluminación+recipe activo.
- La ventana Qt guarda/restaura tamaño y distribución de paneles para mejorar trabajo en pantallas de distinto tamaño.
- Reorganización de pestañas principales para flujo centrado en sesión:
  - `Sesión`,
  - `Revelado y Perfil ICC`,
  - `Cola de Revelado`.
- La GUI de trabajo se reorganiza en dos fases operativas:
  - `1. Calibrar sesión`: capturas de carta -> perfil de revelado + ICC,
  - `2. Aplicar sesión`: RAW/TIFF objetivo -> TIFF con receta calibrada + ICC.
- El ajuste manual visible queda limitado a nitidez; exposición, densidad,
  balance de blancos y base colorimétrica proceden de la carta.
- El procesamiento por lote en GUI ahora tolera errores por archivo y devuelve resumen `OK/errores` sin abortar todo el lote.
- `auto_generate_profile_from_charts` acepta una lista explícita de capturas de
  carta para que la GUI pueda usar una selección de miniaturas en vez de todo
  un directorio.
- La pestaña de calibración de sesión oculta rutas internas de artefactos y
  botones redundantes; el perfil generado se activa automáticamente junto con
  su receta calibrada.
- `Generar perfil de sesión` infiere las cartas desde la selección de miniaturas
  o desde el archivo cargado antes de recurrir a la carpeta, evitando búsquedas
  accidentales en directorios genéricos como `$HOME`.
- Las detecciones manuales guardadas desde la GUI quedan asociadas al RAW de
  carta y se reutilizan durante la generación del perfil de sesión.
- `batch-develop` separa los TIFF lineales de auditoría en `_linear_audit/`
  para que no se confundan con los TIFF finales de inspección o entrega.
- El flujo automático puede reservar capturas de carta para validación hold-out,
  generar `qa_session_report.json` y clasificar la sesión como `validated`,
  `rejected` o `not_validated`.

### Docs

- README ampliado con objetivo del proyecto, alcance, límites y metodología
  aplicada al flujo RAW -> carta -> perfil de revelado -> ICC -> lote.
- Nuevo documento `docs/OPERATIVE_REVIEW_PLAN.md` con hallazgos tecnicos,
  criterios de aceptacion y plan profesional por fases para convertir el
  prototipo en pipeline operativo y auditable.
- `ROADMAP.md`, `ISSUES.md`, `COLOR_PIPELINE.md` y `README.md` enlazados al
  plan operativo y actualizados con prioridades P0-P3.
- Política legal ampliada para:
  - compatibilidad AGPL con objetivo comunitario no comercial,
  - notas de licencia de ArgyllCMS, dcraw y PySide6,
  - obligaciones de redistribución y trazabilidad.
- Nuevo documento `docs/THIRD_PARTY_LICENSES.md` con inventario operativo de licencias de terceros.
- Advertencia explícita en README y manual: el estado actual es de desarrollo y la aplicación aún no se considera plenamente funcional/validada para producción científica o forense.

### Fixed

- `audit_linear_tiff` se escribe antes de compensacion de exposicion y curvas de
  salida, conservando el estado lineal desarrollado.
- Corrección de previsualización RAW rápida:
  - salida de `dcraw` para preview en espacio sRGB (`-o 1`) en lugar de cámara nativa sin conversión,
  - normalización de miniatura embebida a lineal para evitar doble corrección gamma.
- Salvaguarda en preview con perfil ICC:
  - si falta sidecar `.profile.json` o se detecta clipping/dominante extrema, la vista cae a modo sin perfil con aviso en log.
- La receta calibrada generada se carga inmediatamente en la GUI; los revelados
  posteriores ya no pueden quedarse usando los controles base por accidente.
- La previsualización rápida basada en la matriz lateral adapta correctamente
  de D50 a sRGB/D65 para evitar dominantes amarillas o verdosas espurias.

## [0.1.0] - 2026-04-23

### Added

- Estructura inicial del proyecto modular (`core`, `src`, `cli`, `docs`, `tests`).
- CLI funcional para flujo técnico: `raw-info`, `develop`, `detect-chart`, `sample-chart`, `build-profile`, `validate-profile`, `batch-develop`.
- GUI ligera en `tkinter` para operar el flujo completo sin línea de comandos.
- Flujo automático extremo a extremo (`auto-profile-batch`) para carta -> perfil ICC -> lote TIFF 16-bit.
- Script de verificación de herramientas externas: `scripts/check_tools.sh`.
- Manual de usuario en español.
- Documento técnico de integración `dcraw + ArgyllCMS`.
- Documento de cumplimiento legal y política de licencias.

### Changed

- Interfaz gráfica traducida completamente al español.
- Motor de revelado RAW fijado a `dcraw` como backend único soportado.
- Motor de perfil ICC fijado a ArgyllCMS (`colprof`) como backend único soportado.
- Metadatos de licencia del proyecto actualizados a `AGPL-3.0-or-later`.
- Gobernanza declarada para mantenimiento comunitario por la Asociación Española de Imagen Científica y Forense.

### Fixed

- Formato `.ti3` para `colprof` ajustado (`DEVICE_CLASS`/`COLOR_REP` y orden de campos) para compatibilidad real con ArgyllCMS.
- Detección y registro de versión `dcraw` en contexto de ejecución mejorada.

### Docs

- Arquitectura, roadmap, decisiones y manual alineados con:
  - pipeline estricto `dcraw + ArgyllCMS`,
  - requisitos de reproducibilidad,
  - cumplimiento legal AGPL para distribución y uso en red.
