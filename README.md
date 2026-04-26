<p align="center">
  <img src="assets/nexoraw-logo.svg" alt="Logo de NexoRAW" width="560">
</p>

# NexoRAW

Pipeline RAW reproducible y auditable para fotografia cientifica, forense y patrimonial, con perfilado ICC por sesion y trazabilidad abierta AGPL.

![Licencia AGPL-3.0-or-later](https://img.shields.io/badge/licencia-AGPL--3.0--or--later-blue) ![CI](https://img.shields.io/badge/CI-pendiente-lightgrey) ![Version](https://img.shields.io/badge/version-v0.2.0-brightgreen) ![Python](https://img.shields.io/badge/python-3.11%2B-blue) ![Plataformas](https://img.shields.io/badge/plataformas-Linux%20%7C%20macOS%20%7C%20Windows-informational)

![Captura de la GUI de NexoRAW en el flujo de calibrar y aplicar](docs/assets/screenshots/nexoraw-calibrar-aplicar.png)

## Quickstart en 60 segundos

```bash
git clone https://github.com/alejandro-probatia/NexoRAW.git && cd NexoRAW
python3 -m venv .venv && . .venv/bin/activate && pip install -e .
bash examples/demo_session/run_demo.sh
```

## Comparativa rapida

| Punto decisivo | NexoRAW | Alternativas creativas/comerciales |
| --- | --- | --- |
| Revelado reproducible + sidecars JSON con hashes | ✅ | ⚠️ parcial / ❌ |
| Doble pasada carta -> receta calibrada -> ICC | ✅ | ❌ |
| Validacion colorimetrica con holdout + estado operacional del perfil | ✅ | ⚠️ parcial / ❌ |
| Foco principal | Trazabilidad cientifica/forense por sesion | Revelado creativo, flujo comercial o colorimetria aislada |

Comparativa completa: [docs/COMPARISON.md](docs/COMPARISON.md)

## Documentacion completa

- [Manual de usuario](docs/MANUAL_USUARIO.md)
- [Arquitectura](docs/ARCHITECTURE.md)
- [Pipeline de color](docs/COLOR_PIPELINE.md)
- [Roadmap](docs/ROADMAP.md)

## Objetivo del proyecto

El objetivo principal es construir una herramienta comunitaria que permita
trabajar con imÃ¡genes RAW bajo criterios de reproducibilidad, control
colorimÃ©trico y trazabilidad. NexoRAW no busca ser un editor generalista ni una
alternativa creativa a Lightroom, Darktable o RawTherapee. Su foco es mÃ¡s
estrecho:

- revelar RAW con parÃ¡metros explÃ­citos y compatibles con auditorÃ­a,
- generar perfiles avanzados de ajuste a partir de capturas de carta bajo un
  iluminante concreto,
- generar una receta de revelado cientÃ­fica antes de construir el ICC,
- producir perfiles ICC especÃ­ficos para cÃ¡mara, Ã³ptica, iluminante y receta,
- aplicar ese paquete de sesiÃ³n a imÃ¡genes objetivo sin mezclar decisiones
  estÃ©ticas con decisiones de mediciÃ³n,
- documentar comandos, versiones, rutas, estados de QA y artefactos generados,
- mantener un uso verificable y compatible con las licencias de sus
  dependencias directas e indirectas.

El caso de uso natural es un entorno donde importa poder justificar cÃ³mo se
obtuvo una imagen: fotografÃ­a cientÃ­fica, conservaciÃ³n y patrimonio,
laboratorio, documentaciÃ³n tÃ©cnica, inspecciÃ³n, reproducciÃ³n de obra, anÃ¡lisis
forense o proyectos comunitarios que necesiten una cadena de procesado abierta.

## MetodologÃ­a aplicada

La metodologÃ­a de NexoRAW parte de una idea simple: un perfil ICC de cÃ¡mara no
debe esconder problemas bÃ¡sicos de captura o revelado. Antes de perfilar, el
sistema intenta fijar una base tÃ©cnica coherente: balance de blancos,
exposiciÃ³n/densidad y salida lineal. El perfil ICC queda reservado para describir
la respuesta colorimÃ©trica restante de la cÃ¡mara en esa sesiÃ³n.

El flujo metodolÃ³gico es:

1. **Contrato RAW explÃ­cito**: la receta declara motor RAW, demosaicing, balance
   de blancos, niveles, curva tonal y espacio de trabajo. Si un parÃ¡metro no se
   puede ejecutar con el backend activo, el proceso debe fallar en vez de
   sustituirlo silenciosamente.
2. **Captura de carta**: una o varias imÃ¡genes de carta de color documentan las
   condiciones reales de iluminaciÃ³n, cÃ¡mara, Ã³ptica y exposiciÃ³n de la sesiÃ³n.
3. **DetecciÃ³n y muestreo**: la carta se detecta geomÃ©tricamente y cada parche se
   mide con estrategias robustas, evitando saturaciÃ³n y reduciendo el impacto de
   ruido, bordes o muestras contaminadas.
4. **Perfil de revelado cientÃ­fico**: la fila neutra de la carta se usa para
   derivar correcciones de balance, densidad y exposiciÃ³n. Esta fase genera una
   receta calibrada que sigue siendo reproducible y legible.
5. **Segunda mediciÃ³n calibrada**: la carta se mide de nuevo con la receta ya
   calibrada, reutilizando la geometrÃ­a cuando corresponde para no depender de
   cambios de renderizado.
6. **Perfil ICC de sesiÃ³n**: ArgyllCMS genera el perfil ICC a partir de muestras
   medidas y referencias normalizadas. El perfil describe la sesiÃ³n; no es
   universal.
7. **ValidaciÃ³n colorimÃ©trica**: cuando hay muestras independientes, el ICC real
   se valida con CMM/ArgyllCMS y se informa DeltaE 76/2000, outliers y estado
   operacional (`draft`, `validated`, `rejected`, `expired`).
8. **AplicaciÃ³n controlada**: las imÃ¡genes objetivo se revelan con la receta
   calibrada y el modo de gestiÃ³n de color declarado: asignar perfil de entrada
   de cÃ¡mara o convertir a un espacio de salida mediante CMM.
9. **Trazabilidad**: cada ejecuciÃ³n produce artefactos revisables: JSON,
   manifiestos, reportes QA, rutas, versiones de herramientas externas y estado
   de perfil.

Principios de diseÃ±o:

- **Reproducibilidad antes que apariencia**: el modo cientÃ­fico evita curvas
  creativas, automatismos opacos y ajustes manuales no documentados.
- **SeparaciÃ³n de responsabilidades**: la receta corrige revelado base; el ICC
  describe color; el CMM convierte entre perfiles; la GUI solo orquesta esos
  mÃ³dulos.
- **Fallo temprano**: una receta incompatible, una carta no fiable o una
  herramienta externa ausente deben producir un error claro.
- **AuditorÃ­a continua**: los resultados no se consideran solo imÃ¡genes finales,
  sino tambiÃ©n evidencia tÃ©cnica que debe poder revisarse.
- **Validez contextual**: un perfil solo es vÃ¡lido para condiciones comparables
  de cÃ¡mara, Ã³ptica, iluminante, receta y versiÃ³n del software.

## Alcance y lÃ­mites

NexoRAW trabaja por sesiones. Una sesiÃ³n agrupa capturas de carta, RAW objetivo,
mochilas, recetas, perfiles, exportaciones, reportes y artefactos de trabajo. Esto evita
tratar el perfil ICC como una propiedad permanente de la cÃ¡mara: el perfil se
entiende como una descripciÃ³n operativa de una configuraciÃ³n concreta.

NexoRAW no pretende:

- mejorar fotografÃ­as con criterios estÃ©ticos,
- reemplazar un laboratorio de validaciÃ³n colorimÃ©trica,
- garantizar validez forense por sÃ­ solo,
- generar un perfil universal para cualquier luz o escena,
- ocultar dependencias crÃ­ticas como LibRaw/rawpy, ArgyllCMS o ExifTool.

La meta de la release 0.2 es ofrecer una base instalable y verificable para
pruebas controladas, discusiÃ³n tÃ©cnica y ampliaciÃ³n comunitaria.

Mantenimiento comunitario:

- Iniciativa de **Probatia Forensics SL**, mantenida como proyecto abierto,
  gratuito y colaborativo.
- Comunidad de la **Asociacion Espanola de Imagen Cientifica y Forense**.

## Estado actual (importante)

NexoRAW esta en fase activa de desarrollo. Aunque ya hay CLI, GUI e instalador
Linux operativos para pruebas, la aplicacion **todavia no esta validada para
produccion cientifica/forense**.

Usar por ahora como entorno de prototipado, evaluacion tecnica y pruebas controladas.

## Stack actual

- Lenguaje: **Python** (Ãºnica toolchain del proyecto).
- Revelado RAW: **LibRaw** mediante `rawpy`, con DCB por defecto y soporte
  AMaZE cuando el entorno use `rawpy-demosaic`/LibRaw con GPL3.
- Metadatos RAW enriquecidos: `rawpy` (LibRaw) + `exiftool`.
- DetecciÃ³n geomÃ©trica: `OpenCV`.
- ColorimetrÃ­a y DeltaE: `colour-science`.
- Export TIFF 16-bit: `tifffile`.
- Motor de perfil ICC: **ArgyllCMS (`colprof`)**.
- CMM ICC de salida y preview de perfil: **ArgyllCMS (`cctiff`/`xicclu`)**.
- GUI (opcional): **Qt for Python (`PySide6`)**.

## InstalaciÃ³n

Para usuarios finales, NexoRAW se distribuye mediante instaladores. El usuario
no debe instalar Python ni dependencias manualmente: el instalador deja la GUI,
CLI, icono, herramientas externas y backend RAW listos para uso.

Para desarrollo desde cÃ³digo:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
# Opcional (interfaz grafica Qt):
# pip install -e .[gui]
```

Opcional pero recomendado para perfilado con ArgyllCMS y conversion ICC real:

```bash
# Debian/Ubuntu
sudo apt-get install argyll exiftool
# macOS/Homebrew
brew install argyll-cms exiftool
bash scripts/check_tools.sh
nexoraw check-tools --out tools_report.json
```

## Paquete Debian

La release `0.2.0` puede construirse como paquete `.deb` instalable:

```bash
bash packaging/debian/build_deb.sh
sudo apt install ./dist/nexoraw_0.2.0_amd64.deb
```

El paquete instala la aplicacion en `/opt/nexoraw`, crea los lanzadores
`nexoraw`/`nexoraw-ui` y declara las dependencias externas del pipeline. Ver
[Paquete Debian](docs/DEBIAN_PACKAGE.md).

## CLI

El entry point nuevo es `nexoraw` (tambiÃ©n invocable como `python -m nexoraw`).
Los instaladores publicados solo exponen los lanzadores `nexoraw` y
`nexoraw-ui`; las rutas internas `iccraw` se conservan como compatibilidad de
cÃ³digo durante la transiciÃ³n del nombre del proyecto:

```bash
nexoraw raw-info input.raw

nexoraw metadata input.raw --out metadata.json

nexoraw develop input.raw --recipe recipe.yml --out output.tiff --audit-linear output_linear.tiff

nexoraw detect-chart chart.tiff --out detection.json --preview overlay.png --chart-type colorchecker24

# Si la deteccion automatica falla, marcar cuatro esquinas de la carta:
nexoraw detect-chart chart.tiff \
  --out detection.json \
  --preview overlay.png \
  --chart-type colorchecker24 \
  --manual-corners 2193,1717 3045,1686 3070,2256 2211,2288

nexoraw sample-chart chart.tiff --detection detection.json --reference target.json --out samples.json

# Referencia ColorChecker 24 operativa incluida:
# testdata/references/colorchecker24_colorchecker2005_d50.json

nexoraw build-develop-profile samples.json \
  --recipe recipe.yml \
  --out development_profile.json \
  --calibrated-recipe recipe_calibrated.yml

nexoraw export-cgats samples.json --out samples.ti3

nexoraw build-profile samples.json --recipe recipe_calibrated.yml --out camera_profile.icc --report report.json

nexoraw batch-develop ./raws \
  --recipe recipe_calibrated.yml \
  --profile camera_profile.icc \
  --out ./tiffs
```

Las salidas TIFF no se sobrescriben. Si `output.tiff` o
`./tiffs/captura.tiff` ya existen, NexoRAW conserva el archivo anterior y
escribe la nueva version como `output_v002.tiff`, `captura_v002.tiff`,
`captura_v003.tiff`, etc. En `batch-develop`, el TIFF de auditoria lineal en
`_linear_audit/` usa el mismo numero de version que el TIFF final.

```bash
# Firma autonoma NexoRAW Proof y C2PA
pip install -e .
pip install -e .[c2pa]

# Diagnostico de instalacion
nexoraw check-c2pa

# Exportacion: si no hay claves configuradas, NexoRAW crea identidad local.
nexoraw batch-develop ./raws \
  --recipe recipe_calibrated.yml \
  --profile camera_profile.icc \
  --out ./tiffs

# Opcional: credenciales externas si el laboratorio ya las tiene.
# set NEXORAW_C2PA_CERT=G:\ruta\chain.pem
# set NEXORAW_C2PA_KEY=G:\ruta\signing.key
```

NexoRAW Proof se genera automaticamente como firma autonoma del proyecto. C2PA
tambien se intenta incrustar automaticamente si `c2pa-python` esta disponible:
primero usa credenciales externas configuradas y, si no existen, crea una
identidad local autoemitida en `~/.nexoraw/c2pa`. Los lectores C2PA pueden
mostrar `signingCredential.untrusted` con esa identidad local; es una advertencia
de confianza CAI, no una ausencia del vinculo RAW-TIFF. El sidecar
`.nexoraw.proof.json` vincula TIFF y RAW mediante SHA-256 e incluye receta,
perfil ICC, ajustes de nitidez, correccion basica/curvas, gestion de color,
clave publica del firmante y contexto de exportacion.

```bash
nexoraw verify-proof ./tiffs/captura.tiff.nexoraw.proof.json --tiff ./tiffs/captura.tiff --raw ./raws/captura.NEF
nexoraw verify-c2pa ./tiffs/captura.tiff --raw ./raws/captura.NEF --manifest ./tiffs/batch_manifest.json

nexoraw validate-profile samples.json --profile camera_profile.icc --out validation.json

# Flujo completo automÃ¡tico de sesiÃ³n:
# 1) develop de capturas de carta
# 2) detecciÃ³n automÃ¡tica de carta
# 3) muestreo y agregaciÃ³n multi-captura
# 4) perfil de revelado: neutralidad + densidad/exposicion desde carta
# 5) segunda medicion con receta calibrada
# 6) build-profile ICC
# 7) aplicacion posterior a imagenes objetivo con receta calibrada + ICC
nexoraw auto-profile-batch \
  --charts ./charts_raw \
  --targets ./raws \
  --recipe recipe.yml \
  --reference target.json \
  --development-profile-out development_profile.json \
  --calibrated-recipe-out recipe_calibrated.yml \
  --profile-out camera_profile.icc \
  --profile-report profile_report.json \
  --validation-report qa_session_report.json \
  --validation-holdout-count 1 \
  --profile-validity-days 30 \
  --out ./tiffs \
  --workdir ./work_auto
```

```bash
nexoraw compare-qa-reports session_a/qa_session_report.json session_b/qa_session_report.json \
  --out qa_comparison.json

nexoraw check-tools --strict --out tools_report.json
```

## VerificaciÃ³n

```bash
bash scripts/run_checks.sh
nexoraw check-tools --strict --out tools_report.json
```

En Windows:

```powershell
.\scripts\run_checks.ps1
.\scripts\check_tools.ps1 -Strict
```

Medicion basica de rendimiento de preview/render:

```bash
python scripts/benchmark_pipeline.py input.tiff --recipe recipe.yml --repeat 3 --out benchmark.json
```

## Interfaz GrÃ¡fica Qt

La aplicaciÃ³n incluye una GUI basada en **Qt/PySide6** optimizada para flujo de revelado tÃ©cnico:

```bash
nexoraw-ui
```

O directamente:

```bash
bash scripts/run_ui.sh
```

DiseÃ±o de trabajo:

La interfaz principal se organiza en 3 pestaÃ±as:

- `1. SesiÃ³n`:
  - crear o abrir sesiÃ³n de trabajo,
  - guardar metadatos de iluminaciÃ³n y toma,
  - definir un directorio raÃ­z y crear automÃ¡ticamente estructura persistente:
    - `00_configuraciones/`, `01_ORG/`, `02_DRV/`,
  - persistir estado, perfiles, cache y cola en
    `00_configuraciones/session.json`.
- `2. Ajustar / Aplicar`:
  - explorador visual completo del sistema (unidades + Ã¡rbol + miniaturas),
  - selecciÃ³n de raÃ­z de proyecto con apertura automÃ¡tica de `01_ORG/` para
    navegar originales,
  - selecciÃ³n directa desde miniaturas: al elegir un RAW/TIFF compatible se
    carga automÃ¡ticamente en el visor,
  - tira horizontal de miniaturas con tamaÃ±o ajustable, JPEG embebido y fallback
    RAW rÃ¡pido cacheado,
  - preview RAW/DNG de alta fidelidad por defecto, con modo rapido opcional
    para navegacion (miniatura embebida / half-size),
  - gestion ICC de monitor opcional para convertir el preview sRGB al perfil
    de pantalla configurado antes de pintar en Qt,
  - visor con zoom, arrastre de reencuadre, rotaciÃ³n y comparaciÃ³n original/resultado,
  - panel lateral por secciones verticales: `Brillo y contraste`, `Color`,
    `Nitidez`, `GestiÃ³n de color y calibraciÃ³n` y `RAW Global`,
  - `Configuracion -> Configuracion global`: identidad NexoRAW Proof, C2PA
    opcional, modo de preview y gestion ICC del monitor,
  - `Generar perfil avanzado con carta`: selecciÃ³n de capturas de carta,
    ajuste de criterios RAW globales y generaciÃ³n conjunta de perfil de ajuste
    avanzado + ICC de entrada,
  - `Guardar perfil basico en imagen`: escritura de mochila para perfiles
    manuales sin carta,
  - `Copiar perfil de ajuste` / `Pegar perfil de ajuste`: reutilizaciÃ³n de
    ajustes entre miniaturas,
  - `CorrecciÃ³n bÃ¡sica`: iluminante final, temperatura, matiz, brillo, niveles,
    contraste y curva de medios,
  - `Nitidez`: ruido de luminancia, ruido cromÃ¡tico, nitidez y correcciÃ³n de
    aberraciÃ³n cromÃ¡tica lateral,
  - `Aplicar sesiÃ³n`: exportaciÃ³n de RAW seleccionados o carpetas con la receta calibrada y el ICC de sesiÃ³n.
- `3. Cola de Revelado`:
  - cola de imÃ¡genes para revelar (aÃ±adir/quitar/limpiar),
  - ejecuciÃ³n de cola con estado por archivo (pendiente/ok/error),
  - monitoreo de tareas y log tÃ©cnico centralizado del pipeline.

La cabecera muestra una barra de progreso global para cargas, generaciÃ³n de
perfil y revelado por lote, de modo que las tareas largas siempre dejan un
estado visible.

MenÃº superior:

- `Archivo`, `Configuracion`, `Perfil ICC`, `Vista`, `Ayuda`.
- Acceso rÃ¡pido a carga/guardado de receta, perfil activo y acciones de revelado.
- `Vista` incluye pantalla completa (`F11`) y restablecer distribuciÃ³n de paneles.

Compatibilidad prevista de GUI:

- Linux, macOS y Windows (Qt/PySide6, selector de raÃ­ces/unidades por plataforma).

La GUI usa los mismos mÃ³dulos de la CLI y escribe los mismos artefactos JSON/TIFF/ICC, manteniendo trazabilidad.
AdemÃ¡s, conserva tamaÃ±o/estado de ventana y splitters entre sesiones.
Las salidas de sesiÃ³n se normalizan dentro del directorio raÃ­z: perfiles en
`00_configuraciones/`, originales en `01_ORG/` y TIFF/preview/manifiestos en
`02_DRV/`.

Notas de preview y rendimiento:

- El visor mantiene internamente el preview en RGB lineal `float32` y genera
  una imagen sRGB para pantalla/PNG. La conversion al perfil ICC del monitor,
  si esta activada, se aplica solo al pintar en pantalla y no modifica
  artefactos, hashes ni manifests.
- El modo rapido RAW sirve para navegacion; para revision colorimetrica debe
  usarse el preview de alta fidelidad, que comparte el pipeline de revelado
  con la exportacion.
- Las previsualizaciones base se cachean con clave de archivo, receta y modo de
  preview, con limite de memoria. Las miniaturas se generan a tamano maximo y
  se reescalan desde cache al mover el control de tamano.
- Cuando el archivo pertenece a una sesiÃ³n, la cache persistente se guarda bajo
  `00_configuraciones/work/cache/` con rutas relativas para que una carpeta de
  proyecto pueda moverse o compartirse con otro usuario.

## Receta reproducible

Ver ejemplo en [testdata/recipes/scientific_recipe.yml](testdata/recipes/scientific_recipe.yml).

Campos clave:

- `demosaic_algorithm`
- `raw_developer` (`libraw`)
- `black_level_mode`
- `white_balance_mode`
- `wb_multipliers`
- `output_linear`
- `tone_curve`
- `profiling_mode`
- `profile_engine` (`argyll`, Ãºnico motor soportado)

Con el backend actual LibRaw/rawpy, `demosaic_algorithm` acepta valores como
`dcb`, `dht`, `ahd`, `vng`, `ppg`, `linear` y, si la build de LibRaw/rawpy lo
incluye, `amaze`. `dcb` es el valor por defecto instalable; AMaZE requiere
`rawpy.flags["DEMOSAIC_PACK_GPL3"] == True`, normalmente mediante
`rawpy-demosaic` o una build propia de LibRaw con el demosaic pack GPL3.
Las builds que deban incluir AMaZE deben instalar ese backend durante la
construccion, con `scripts/install_amaze_backend.py`, y fallar si
`nexoraw check-amaze` no confirma `DEMOSAIC_PACK_GPL3=True`.

## Reproducibilidad y lÃ­mites

- El perfil ICC **no es universal**.
- VÃ¡lido para condiciones comparables de cÃ¡mara + Ã³ptica + iluminante + recipe.
- Cambios de demosaicing/WB/tone mapping pueden invalidar la validez colorimÃ©trica.

## Licencia

- Licencia del proyecto: `AGPL-3.0-or-later`.
- Objetivo del proyecto: cientÃ­fico, forense y comunitario sin finalidad comercial.
- Nota legal importante: la AGPL es una licencia libre y **no** restringe el uso comercial por terceros; el objetivo no comercial se expresa como gobernanza del proyecto, no como clÃ¡usula restrictiva.
- Compromiso del proyecto: NexoRAW debe seguir siendo gratuito, abierto,
  auditable y respetuoso con las obligaciones legales de sus dependencias,
  incluidas librerÃ­as, herramientas externas y proyectos de terceros.
- Para despliegues y redistribuciÃ³n, seguir:
  - [Cumplimiento Legal y Licencias](docs/LEGAL_COMPLIANCE.md)
  - [Licencias de Terceros](docs/THIRD_PARTY_LICENSES.md)
  - [Soporte AMaZE GPL3](docs/AMAZE_GPL3.md)

## DocumentaciÃ³n

- [Architecture](docs/ARCHITECTURE.md)
- [Roadmap](docs/ROADMAP.md)
- [Color Pipeline](docs/COLOR_PIPELINE.md)
- [Revision operativa y plan de profesionalizacion](docs/OPERATIVE_REVIEW_PLAN.md)
- [Changelog](CHANGELOG.md)
- [Manual de Usuario](docs/MANUAL_USUARIO.md)
- [NexoRAW Proof](docs/NEXORAW_PROOF.md)
- [C2PA/CAI](docs/C2PA_CAI.md)
- [IntegraciÃ³n LibRaw + ArgyllCMS](docs/INTEGRACION_LIBRAW_ARGYLL.md)
- [Paquete Debian](docs/DEBIAN_PACKAGE.md)
- [Instalacion en macOS](docs/MACOS_INSTALL.md)
- [Instalador Windows](docs/WINDOWS_INSTALLER.md)
- [Cumplimiento Legal y Licencias](docs/LEGAL_COMPLIANCE.md)
- [Licencias de Terceros](docs/THIRD_PARTY_LICENSES.md)
- [Decisiones](docs/DECISIONS.md)
- [Backlog priorizado](docs/ISSUES.md)

