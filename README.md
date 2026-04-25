<p align="center">
  <img src="assets/nexoraw-logo.svg" alt="NexoRAW" width="560">
</p>

# NexoRAW

NexoRAW es una aplicación gratuita y de código abierto para fotografía
técnico-científica, documental y forense. Es una iniciativa de **Probatia
Forensics SL** puesta a disposición de la comunidad como software libre:
NexoRAW será siempre gratuito y de código abierto, con código fuente público,
auditable y redistribuible conforme a su licencia AGPL-3.0-or-later.

Su objetivo es transformar una captura RAW en un flujo reproducible y
auditable, donde cada decisión técnica queda declarada, registrada y puede
repetirse con las mismas condiciones.

El objetivo del proyecto es ofrecer una herramienta que respete de forma
estricta los requisitos legales y de licencia de las librerías, herramientas y
proyectos en los que se basa. La trazabilidad del código, las dependencias y los
artefactos generados debe permitir auditoría técnica independiente, manteniendo
el acceso gratuito para la comunidad científica y forense.

El proyecto nace para cubrir un espacio que los reveladores fotográficos
convencionales no suelen priorizar: separar el ajuste creativo de la medición
colorimétrica, controlar el revelado RAW, generar perfiles de cámara por sesión
y conservar evidencia técnica suficiente para revisar el proceso después.

En términos prácticos, NexoRAW implementa:

1. revelado RAW controlado y reproducible,
2. detección automática de carta de color,
3. muestreo robusto por parche,
4. generación de perfil de revelado científico + perfil ICC específico de sesión,
5. aplicación de ese paquete de sesión a RAW/TIFF seleccionados,
6. trazabilidad y auditoría (JSON sidecars + hashes + manifiestos).

## Objetivo del proyecto

El objetivo principal es construir una herramienta comunitaria que permita
trabajar con imágenes RAW bajo criterios de reproducibilidad, control
colorimétrico y trazabilidad. NexoRAW no busca ser un editor generalista ni una
alternativa creativa a Lightroom, Darktable o RawTherapee. Su foco es más
estrecho:

- revelar RAW con parámetros explícitos y compatibles con auditoría,
- calibrar una sesión a partir de capturas de carta bajo un iluminante concreto,
- generar una receta de revelado científica antes de construir el ICC,
- producir perfiles ICC específicos para cámara, óptica, iluminante y receta,
- aplicar ese paquete de sesión a imágenes objetivo sin mezclar decisiones
  estéticas con decisiones de medición,
- documentar comandos, versiones, rutas, estados de QA y artefactos generados,
- mantener un uso verificable y compatible con las licencias de sus
  dependencias directas e indirectas.

El caso de uso natural es un entorno donde importa poder justificar cómo se
obtuvo una imagen: fotografía científica, conservación y patrimonio,
laboratorio, documentación técnica, inspección, reproducción de obra, análisis
forense o proyectos comunitarios que necesiten una cadena de procesado abierta.

## Metodología aplicada

La metodología de NexoRAW parte de una idea simple: un perfil ICC de cámara no
debe esconder problemas básicos de captura o revelado. Antes de perfilar, el
sistema intenta fijar una base técnica coherente: balance de blancos,
exposición/densidad y salida lineal. El perfil ICC queda reservado para describir
la respuesta colorimétrica restante de la cámara en esa sesión.

El flujo metodológico es:

1. **Contrato RAW explícito**: la receta declara motor RAW, demosaicing, balance
   de blancos, niveles, curva tonal y espacio de trabajo. Si un parámetro no se
   puede ejecutar con el backend activo, el proceso debe fallar en vez de
   sustituirlo silenciosamente.
2. **Captura de carta**: una o varias imágenes de carta de color documentan las
   condiciones reales de iluminación, cámara, óptica y exposición de la sesión.
3. **Detección y muestreo**: la carta se detecta geométricamente y cada parche se
   mide con estrategias robustas, evitando saturación y reduciendo el impacto de
   ruido, bordes o muestras contaminadas.
4. **Perfil de revelado científico**: la fila neutra de la carta se usa para
   derivar correcciones de balance, densidad y exposición. Esta fase genera una
   receta calibrada que sigue siendo reproducible y legible.
5. **Segunda medición calibrada**: la carta se mide de nuevo con la receta ya
   calibrada, reutilizando la geometría cuando corresponde para no depender de
   cambios de renderizado.
6. **Perfil ICC de sesión**: ArgyllCMS genera el perfil ICC a partir de muestras
   medidas y referencias normalizadas. El perfil describe la sesión; no es
   universal.
7. **Validación colorimétrica**: cuando hay muestras independientes, el ICC real
   se valida con CMM/ArgyllCMS y se informa DeltaE 76/2000, outliers y estado
   operacional (`draft`, `validated`, `rejected`, `expired`).
8. **Aplicación controlada**: las imágenes objetivo se revelan con la receta
   calibrada y el modo de gestión de color declarado: asignar perfil de entrada
   de cámara o convertir a un espacio de salida mediante CMM.
9. **Trazabilidad**: cada ejecución produce artefactos revisables: JSON,
   manifiestos, reportes QA, rutas, versiones de herramientas externas y estado
   de perfil.

Principios de diseño:

- **Reproducibilidad antes que apariencia**: el modo científico evita curvas
  creativas, automatismos opacos y ajustes manuales no documentados.
- **Separación de responsabilidades**: la receta corrige revelado base; el ICC
  describe color; el CMM convierte entre perfiles; la GUI solo orquesta esos
  módulos.
- **Fallo temprano**: una receta incompatible, una carta no fiable o una
  herramienta externa ausente deben producir un error claro.
- **Auditoría continua**: los resultados no se consideran solo imágenes finales,
  sino también evidencia técnica que debe poder revisarse.
- **Validez contextual**: un perfil solo es válido para condiciones comparables
  de cámara, óptica, iluminante, receta y versión del software.

## Alcance y límites

NexoRAW trabaja por sesiones. Una sesión agrupa capturas de carta, RAW objetivo,
recetas, perfiles, exportaciones, reportes y artefactos de trabajo. Esto evita
tratar el perfil ICC como una propiedad permanente de la cámara: el perfil se
entiende como una descripción operativa de una configuración concreta.

NexoRAW no pretende:

- mejorar fotografías con criterios estéticos,
- reemplazar un laboratorio de validación colorimétrica,
- garantizar validez forense por sí solo,
- generar un perfil universal para cualquier luz o escena,
- ocultar dependencias críticas como LibRaw/rawpy, ArgyllCMS o ExifTool.

La meta de la beta es ofrecer una base instalable y verificable para pruebas
controladas, discusión técnica y ampliación comunitaria.

Mantenimiento comunitario:

- Iniciativa de **Probatia Forensics SL**, mantenida como proyecto abierto,
  gratuito y colaborativo.
- Comunidad de la **Asociacion Espanola de Imagen Cientifica y Forense**.

## Estado actual (importante)

NexoRAW esta en fase activa de desarrollo. Aunque ya hay CLI y GUI operativas para pruebas, la aplicacion **todavia no es plenamente funcional ni esta validada para produccion cientifica/forense**.

Usar por ahora como entorno de prototipado, evaluacion tecnica y pruebas controladas.

## Stack actual

- Lenguaje: **Python** (única toolchain del proyecto).
- Revelado RAW: **LibRaw** mediante `rawpy`, con DCB por defecto y soporte
  AMaZE cuando el entorno use `rawpy-demosaic`/LibRaw con GPL3.
- Metadatos RAW enriquecidos: `rawpy` (LibRaw) + `exiftool`.
- Detección geométrica: `OpenCV`.
- Colorimetría y DeltaE: `colour-science`.
- Export TIFF 16-bit: `tifffile`.
- Motor de perfil ICC: **ArgyllCMS (`colprof`)**.
- CMM ICC de salida y preview de perfil: **ArgyllCMS (`cctiff`/`xicclu`)**.
- GUI (opcional): **Qt for Python (`PySide6`)**.

## Instalación

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
bash scripts/check_tools.sh
nexoraw check-tools --out tools_report.json
```

## Paquete Debian beta

La beta `0.1` puede construirse como paquete `.deb` instalable:

```bash
bash packaging/debian/build_deb.sh
sudo apt install ./dist/nexoraw_0.1.0~beta4_amd64.deb
```

El paquete instala la aplicacion en `/opt/nexoraw`, crea los lanzadores
`nexoraw`/`nexoraw-ui` y declara las dependencias externas del pipeline. Ver
[Paquete Debian beta](docs/DEBIAN_PACKAGE.md).

## CLI

El entry point nuevo es `nexoraw` (también invocable como `python -m nexoraw`).
Los comandos heredados `iccraw` e `iccraw-ui` se mantienen como alias durante la
transicion del proyecto:

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

nexoraw batch-develop ./raws --recipe recipe_calibrated.yml --profile camera_profile.icc --out ./tiffs

# Opcional: firmar TIFFs finales con C2PA/CAI
pip install -e .[c2pa]
nexoraw batch-develop ./raws \
  --recipe recipe_calibrated.yml \
  --profile camera_profile.icc \
  --out ./tiffs \
  --c2pa-sign \
  --c2pa-cert chain.pem \
  --c2pa-key signing.key

nexoraw verify-c2pa ./tiffs/captura.tiff --raw ./raws/captura.NEF --manifest ./tiffs/batch_manifest.json

nexoraw validate-profile samples.json --profile camera_profile.icc --out validation.json

# Flujo completo automático de sesión:
# 1) develop de capturas de carta
# 2) detección automática de carta
# 3) muestreo y agregación multi-captura
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

## Verificación

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

## Interfaz Gráfica Qt

La aplicación incluye una GUI basada en **Qt/PySide6** optimizada para flujo de revelado técnico:

```bash
nexoraw-ui
```

O directamente:

```bash
bash scripts/run_ui.sh
```

Diseño de trabajo:

La interfaz principal se organiza en 3 pestañas:

- `1. Sesión`:
  - crear o abrir sesión de trabajo,
  - guardar metadatos de iluminación y toma,
  - definir un directorio raíz y crear automáticamente estructura persistente:
    - `charts/`, `raw/`, `profiles/`, `exports/`, `config/`, `work/`,
  - persistir estado de la sesión (`config/session.json`) con configuración y cola.
- `2. Calibrar / Aplicar`:
  - explorador visual completo del sistema (unidades + árbol + miniaturas),
  - selección directa desde miniaturas: al elegir un RAW/TIFF compatible se
    carga automáticamente en el visor,
  - preview rápido RAW/DNG (miniatura embebida / half-size) y resolución configurable,
  - visor con zoom, arrastre de reencuadre, rotación y comparación original/resultado,
  - panel lateral por secciones verticales: calibración con criterios RAW,
    corrección básica, detalle, perfil activo y aplicación de sesión,
  - `Calibrar sesión`: selección de una o varias capturas de carta, ajuste de
    criterios RAW globales y generación conjunta de perfil de revelado + ICC,
  - `Corrección básica`: iluminante final, temperatura, matiz, brillo, niveles,
    contraste y curva de medios,
  - `Detalle`: ruido de luminancia, ruido cromático, nitidez y corrección de
    aberración cromática lateral,
  - `Aplicar sesión`: exportación de RAW seleccionados o carpetas con la receta calibrada y el ICC de sesión.
- `3. Cola de Revelado`:
  - cola de imágenes para revelar (añadir/quitar/limpiar),
  - ejecución de cola con estado por archivo (pendiente/ok/error),
  - monitoreo de tareas y log técnico centralizado del pipeline.

La cabecera muestra una barra de progreso global para cargas, generación de
perfil y revelado por lote, de modo que las tareas largas siempre dejan un
estado visible.

Menú superior:

- `Archivo`, `Configuracion`, `Perfil ICC`, `Vista`, `Ayuda`.
- Acceso rápido a carga/guardado de receta, perfil activo y acciones de revelado.
- `Vista` incluye pantalla completa (`F11`) y restablecer distribución de paneles.

Compatibilidad prevista de GUI:

- Linux, macOS y Windows (Qt/PySide6, selector de raíces/unidades por plataforma).

La GUI usa los mismos módulos de la CLI y escribe los mismos artefactos JSON/TIFF/ICC, manteniendo trazabilidad.
Además, conserva tamaño/estado de ventana y splitters entre sesiones.
Las salidas de sesión se normalizan dentro del directorio raíz: perfiles en
`profiles/`, recetas/reportes en `config/`, artefactos de trabajo en `work/` y
TIFF/preview en `exports/`.

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
- `profile_engine` (`argyll`, único motor soportado)

Con el backend actual LibRaw/rawpy, `demosaic_algorithm` acepta valores como
`dcb`, `dht`, `ahd`, `vng`, `ppg`, `linear` y, si la build de LibRaw/rawpy lo
incluye, `amaze`. `dcb` es el valor por defecto instalable; AMaZE requiere
`rawpy.flags["DEMOSAIC_PACK_GPL3"] == True`, normalmente mediante
`rawpy-demosaic` o una build propia de LibRaw con el demosaic pack GPL3.

## Reproducibilidad y límites

- El perfil ICC **no es universal**.
- Válido para condiciones comparables de cámara + óptica + iluminante + recipe.
- Cambios de demosaicing/WB/tone mapping pueden invalidar la validez colorimétrica.

## Licencia

- Licencia del proyecto: `AGPL-3.0-or-later`.
- Objetivo del proyecto: científico, forense y comunitario sin finalidad comercial.
- Nota legal importante: la AGPL es una licencia libre y **no** restringe el uso comercial por terceros; el objetivo no comercial se expresa como gobernanza del proyecto, no como cláusula restrictiva.
- Compromiso del proyecto: NexoRAW debe seguir siendo gratuito, abierto,
  auditable y respetuoso con las obligaciones legales de sus dependencias,
  incluidas librerías, herramientas externas y proyectos de terceros.
- Para despliegues y redistribución, seguir:
  - [Cumplimiento Legal y Licencias](docs/LEGAL_COMPLIANCE.md)
  - [Licencias de Terceros](docs/THIRD_PARTY_LICENSES.md)
  - [Soporte AMaZE GPL3](docs/AMAZE_GPL3.md)

## Documentación

- [Architecture](docs/ARCHITECTURE.md)
- [Roadmap](docs/ROADMAP.md)
- [Color Pipeline](docs/COLOR_PIPELINE.md)
- [Revision operativa y plan de profesionalizacion](docs/OPERATIVE_REVIEW_PLAN.md)
- [Changelog](CHANGELOG.md)
- [Manual de Usuario](docs/MANUAL_USUARIO.md)
- [Integración LibRaw + ArgyllCMS](docs/INTEGRACION_LIBRAW_ARGYLL.md)
- [Paquete Debian beta](docs/DEBIAN_PACKAGE.md)
- [Instalador Windows beta](docs/WINDOWS_INSTALLER.md)
- [Cumplimiento Legal y Licencias](docs/LEGAL_COMPLIANCE.md)
- [Licencias de Terceros](docs/THIRD_PARTY_LICENSES.md)
- [Decisiones](docs/DECISIONS.md)
- [Backlog priorizado](docs/ISSUES.md)
