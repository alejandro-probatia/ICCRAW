# Manual de Usuario de NexoRAW

NexoRAW es una aplicacion abierta, gratuita y auditable para revelado RAW/TIFF
orientado a fotografia tecnico-cientifica, documental y forense. Su objetivo es
mantener un flujo reproducible desde el RAW original hasta el TIFF final,
conservando trazabilidad, hashes, manifiestos, perfilado ICC y evidencias de
procedimiento. Es una iniciativa de Probatia Forensics SL ofrecida como proyecto
gratuito y de codigo abierto para la comunidad cientifica y forense.

![Gestion de sesion en NexoRAW](assets/screenshots/nexoraw-sesion.png)

## 1. Principios de trabajo

NexoRAW esta pensado para flujos donde la imagen no es solo una fotografia, sino
un registro tecnico que puede requerir auditoria posterior.

Principios operativos:

1. El RAW original no se modifica nunca.
2. El identificador probatorio principal es el SHA-256 de los bytes exactos del
   RAW, no su nombre ni su ruta.
3. Toda salida TIFF debe poder vincularse al RAW, receta, perfil ICC, ajustes y
   contexto de generacion.
4. La previsualizacion debe servir para trabajar con agilidad, pero el render
   final debe conservar el flujo auditado.
5. Los perfiles de revelado e ICC son validos para condiciones comparables:
   camara, optica, iluminante, receta RAW y metodologia de captura.
6. C2PA/CAI es una capa interoperable opcional. La firma autonoma obligatoria
   del proyecto es NexoRAW Proof.

## 2. Instalacion

### 2.1 Dependencias del sistema

NexoRAW usa herramientas externas para tareas cientificas y de metadatos:

- ArgyllCMS: generacion y aplicacion de perfiles ICC.
- exiftool: lectura amplia de metadatos EXIF, GPS y fabricante.

Linux:

```bash
sudo apt-get update
sudo apt-get install -y argyll exiftool
```

macOS:

```bash
brew install argyll-cms exiftool
```

Windows:

1. Instalar ArgyllCMS y anadir sus ejecutables al `PATH`.
2. Instalar `exiftool` y comprobar que esta disponible desde terminal.

Comprobacion:

```bash
nexoraw check-tools --strict
```

### 2.2 Entorno Python

Instalacion base:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

Extras utiles:

```bash
pip install -e .[gui]
pip install -e .[c2pa]
```

El instalador Windows ya incluye C2PA. En instalacion desde codigo, el extra
`c2pa` permite incrustar y leer manifiestos C2PA en TIFF. Si no hay certificado
externo, NexoRAW crea una identidad local autoemitida.

### 2.3 AMaZE y licencia GPL3

El motor RAW base es LibRaw/rawpy. El demosaicing AMaZE solo aparece como
disponible cuando la build de rawpy/LibRaw incluye el demosaic pack GPL3.

Comprobacion:

```bash
python scripts/check_amaze_support.py
```

Si AMaZE no esta disponible, NexoRAW degrada a un algoritmo soportado para evitar
errores de revelado.

## 3. Conceptos clave

### 3.1 Sesion

Una sesion agrupa una captura o lote bajo una estructura persistente:

- `charts/`: capturas de carta colorimetrica.
- `raw/`: RAW originales de sesion.
- `profiles/`: perfiles ICC y sidecars de perfil.
- `exports/`: TIFF finales y previews exportadas.
- `config/`: recetas, informes, manifiestos y estado de sesion.
- `work/`: intermedios auditables y artefactos de perfilado.

La sesion se guarda en `config/session.json`.

### 3.2 Receta RAW

La receta define criterios reproducibles de revelado:

- motor RAW,
- algoritmo de demosaicing,
- balance de blancos,
- nivel negro,
- compensacion de exposicion,
- curva tonal,
- espacio de trabajo,
- espacio de salida,
- salida lineal/no lineal,
- denoise y sharpen de receta.

Durante la generacion de perfil, NexoRAW fuerza parametros cientificos cuando
corresponde: salida lineal, curva lineal, espacio de escena y desactivacion de
filtros que puedan alterar la medicion de carta.

### 3.3 Perfil de revelado e ICC

El flujo de perfilado tiene dos capas:

- Perfil de revelado NexoRAW: ajusta neutralidad, densidad y parametros
  reproducibles desde la carta.
- Perfil ICC: describe la transformacion colorimetrica resultante con ArgyllCMS.

Ambos deben usarse juntos con la misma receta y condiciones de captura.

### 3.4 TIFF final y trazabilidad

Cada TIFF final puede generar:

- TIFF 16-bit final.
- TIFF lineal de auditoria en `_linear_audit/`.
- `batch_manifest.json`.
- sidecar `.nexoraw.proof.json`.
- informacion C2PA embebida si esta configurada.

Si un TIFF de salida ya existe, NexoRAW no lo sobrescribe. Crea versiones:
`captura.tiff`, `captura_v002.tiff`, `captura_v003.tiff`, etc.

## 4. Interfaz grafica

Arranque:

```bash
nexoraw-ui
```

o:

```bash
python -m iccraw.gui
```

La interfaz se divide en tres pestañas principales.

### 4.1 Pestaña Sesion

La pestaña `Sesion` sirve para crear, abrir y guardar el contexto de trabajo.

Funciones:

- definir directorio raiz de sesion,
- nombrar la sesion,
- registrar condiciones de iluminacion,
- registrar notas de toma,
- crear estructura persistente de carpetas,
- guardar estado y cola de trabajo.

![Pestaña de sesion](assets/screenshots/nexoraw-sesion.png)

Uso recomendado:

1. Crear una carpeta de sesion.
2. Pulsar `Crear sesion`.
3. Copiar RAW originales en `raw/` o seleccionar una carpeta existente.
4. Guardar notas de iluminacion y toma.
5. Trabajar siempre dentro de esa raiz para mantener rutas y manifiestos
   coherentes.

### 4.2 Pestaña Calibrar / Aplicar

Esta es la pantalla principal de trabajo.

![Calibrar y aplicar](assets/screenshots/nexoraw-calibrar-aplicar.png)

Zonas:

- Columna izquierda:
  - `Explorador`: unidades, arbol de carpetas y seleccion de archivos.
  - `Visor`: controles de zoom, rotacion y comparacion.
  - `Analisis`: niveles y resumen tecnico del preview.
  - `Metadatos`: visor EXIF/GPS/C2PA/NexoRAW Proof.
  - `Log`: eventos del pipeline y avisos.
- Centro:
  - visor principal sobre fondo gris oscuro neutro,
  - tira inferior de miniaturas,
  - selector de tamano de miniaturas.
- Columna derecha:
  - `Calibrar sesion`,
  - `Correccion basica`,
  - `Nitidez`,
  - `Perfil activo`,
  - `Aplicar sesion`.

#### Explorador y miniaturas

El explorador permite navegar por unidades y carpetas. Las miniaturas muestran
RAW/TIFF/imagenes compatibles y se cachean para evitar recalculos al cambiar de
tamano. Una linea verde sobre la miniatura indica que esa imagen se ha marcado
como referencia colorimetrica.

Botones principales:

- `Usar seleccion como referencias colorimetricas`: marca la seleccion actual
  como capturas de carta para generar perfil.
- `Anadir seleccion a cola`: anade los archivos seleccionados a la cola de
  revelado.

#### Visor principal

Funciones del visor:

- zoom y encaje,
- desplazamiento por arrastre,
- rotacion,
- comparacion original/resultado,
- aplicacion opcional de perfil ICC al resultado,
- marcado manual de carta,
- cuentagotas neutro.

`Comparar original/resultado` divide el visor para revisar el antes y despues
del pipeline de render. El original es la imagen base cargada; el resultado es
la imagen tras perfil, correcciones basicas y nitidez segun los controles
activos.

#### Calibrar sesion

Este panel agrupa las decisiones previas a crear el perfil:

- carpeta o seleccion de referencias colorimetricas,
- referencia JSON de carta,
- perfil ICC de salida,
- tipo de carta,
- confianza minima de deteccion,
- fallback de deteccion,
- formato ICC,
- tipo/calidad de perfil ArgyllCMS,
- criterios RAW globales para la medicion de perfil.

Flujo:

1. Seleccionar una o varias capturas de carta.
2. Pulsar `Usar seleccion como referencias colorimetricas`.
3. Revisar que el indicador muestra las referencias seleccionadas.
4. Ajustar RAW global si procede.
5. Ejecutar `Generar perfil de sesion`.
6. Revisar reporte JSON, DeltaE y estado del perfil.

#### Correccion basica

Panel para ajustes globales de render final:

- iluminante final,
- temperatura,
- matiz,
- cuentagotas neutro,
- brillo en EV,
- nivel negro,
- nivel blanco,
- contraste,
- curva de medios,
- curva tonal avanzada,
- punto negro/blanco de curva.

El cuentagotas neutro permite hacer clic sobre una zona neutral de la imagen
para estimar una correccion de temperatura/matiz. Debe usarse sobre zonas sin
dominantes propias, no sobre parches coloreados.

La curva tonal avanzada se suaviza para evitar saltos tonales bruscos. Es
adecuada para ajuste tecnico de contraste, no para edicion creativa destructiva.

#### Nitidez

Panel para ajustes de detalle del render final:

- nitidez,
- radio de nitidez,
- reduccion de ruido de luminancia,
- reduccion de ruido cromatico,
- correccion de aberracion cromatica lateral rojo/cian,
- correccion de aberracion cromatica lateral azul/amarillo,
- modos de denoise/sharpen heredados por receta.

Estos ajustes se aplican al preview y al lote final cuando `Aplicar ajustes
basicos y de nitidez` esta activado.

#### Perfil activo

Permite cargar el perfil ICC de sesion que se usara en preview/exportacion.

Funciones:

- `Cargar perfil activo`,
- `Usar perfil generado`,
- ver ruta del perfil activo.

Si el perfil no tiene sidecar valido o provoca clipping extremo en preview,
NexoRAW puede desactivar su aplicacion visual y registrar un aviso.

#### Aplicar sesion

Panel para exportar TIFF finales:

- carpeta RAW a revelar,
- carpeta de salida TIFF,
- aplicar perfil ICC de sesion,
- aplicar correcciones basicas y nitidez,
- aplicar a seleccion,
- aplicar a carpeta.

La firma NexoRAW Proof y C2PA no estan aqui porque no son ajustes de imagen. Se
configuran en el menu global.

### 4.3 Visor de metadatos

La pestaña vertical `Metadatos` permite inspeccionar el archivo seleccionado.

![Visor de metadatos](assets/screenshots/nexoraw-metadatos.png)

Pestañas:

- `Resumen`: campos relevantes interpretados.
- `EXIF`: camara, lente, exposicion, fabricante y otros metadatos.
- `GPS`: coordenadas si existen.
- `C2PA`: manifiesto C2PA y validacion si existe.
- `Todo`: JSON completo.

El visor combina:

- `exiftool` para EXIF/GPS,
- sidecar NexoRAW Proof,
- lectura C2PA si el extra esta instalado,
- estado de validacion disponible.

### 4.4 Cola de Revelado

La cola permite diferir revelados y procesar lotes.

![Cola de revelado](assets/screenshots/nexoraw-cola-revelado.png)

Funciones:

- anadir archivos seleccionados,
- anadir RAW de sesion,
- quitar seleccionados,
- limpiar cola,
- revelar cola,
- revisar estado por archivo,
- consultar monitoreo de tareas y log.

## 5. Configuracion global

Las opciones globales estan en:

`Configuracion -> Configuracion global...`

![Configuracion global](assets/screenshots/nexoraw-configuracion-global.png)

### 5.1 Firma / C2PA

Contiene dos bloques.

NexoRAW Proof:

- clave privada Ed25519,
- clave publica,
- frase clave no persistente,
- nombre de firmante,
- generacion de identidad local Proof.

C2PA / CAI:

- certificado C2PA externo opcional,
- clave privada C2PA externa opcional,
- frase clave no persistente,
- algoritmo,
- servidor TSA,
- firmante C2PA.

NexoRAW Proof se genera automaticamente para la trazabilidad autonoma del TIFF
final. C2PA se intenta incrustar automaticamente con credenciales externas si
estan configuradas; si no, se usa una identidad local de laboratorio creada por
NexoRAW.

Variables de entorno utiles:

```bat
set NEXORAW_C2PA_CERT=G:\ruta\chain.pem
set NEXORAW_C2PA_KEY=G:\ruta\signing.key
```

### 5.2 Preview / monitor

Opciones:

- preview RAW rapida,
- lado maximo de preview,
- gestion ICC del monitor,
- perfil ICC/ICM del monitor,
- ruta de guardado de preview PNG.

Para revision colorimetrica, usar preview de alta calidad y activar perfil ICC
del monitor si se dispone de un perfil fiable. La gestion de monitor solo afecta
a pantalla y miniaturas; no cambia TIFFs, hashes ni manifiestos.

## 6. Flujo recomendado con GUI

1. Crear o abrir sesion.
2. Copiar RAW originales a `raw/`.
3. Seleccionar capturas de carta.
4. Marcar `Usar seleccion como referencias colorimetricas`.
5. Revisar RAW global y referencia de carta.
6. Generar perfil de sesion.
7. Revisar overlay, DeltaE, reporte y estado del perfil.
8. Usar el perfil generado como perfil activo.
9. Ajustar correccion basica y nitidez si procede.
10. Configurar NexoRAW Proof en `Configuracion global`.
11. Exportar seleccion, carpeta o cola.
12. Revisar `batch_manifest.json`, sidecars y metadatos.

## 7. Flujo recomendado con CLI

### 7.1 Informacion RAW

```bash
nexoraw raw-info captura.NEF
```

### 7.2 Revelado individual

```bash
nexoraw develop captura.NEF \
  --recipe testdata/recipes/scientific_recipe.yml \
  --out exports/captura.tiff \
  --audit-linear exports/_linear_audit/captura_linear.tiff
```

### 7.3 Deteccion y muestreo de carta

```bash
nexoraw detect-chart exports/carta.tiff \
  --out work/detection.json \
  --preview work/overlay.png \
  --chart-type colorchecker24

nexoraw sample-chart exports/carta.tiff \
  --detection work/detection.json \
  --reference testdata/references/colorchecker24_colorchecker2005_d50.json \
  --recipe testdata/recipes/scientific_recipe.yml \
  --out work/samples.json
```

### 7.4 Perfil de revelado e ICC

```bash
nexoraw build-develop-profile work/samples.json \
  --recipe testdata/recipes/scientific_recipe.yml \
  --out config/development_profile.json \
  --calibrated-recipe config/recipe_calibrated.yml

nexoraw build-profile work/samples.json \
  --recipe config/recipe_calibrated.yml \
  --out profiles/camera_profile.icc \
  --report config/profile_report.json
```

### 7.5 Lote TIFF

```bash
nexoraw batch-develop raw \
  --recipe config/recipe_calibrated.yml \
  --profile profiles/camera_profile.icc \
  --out exports/tiff \
  --proof-key ~/.nexoraw/proof/nexoraw-proof-private.pem \
  --proof-public-key ~/.nexoraw/proof/nexoraw-proof-public.pem
```

### 7.6 Verificacion

```bash
nexoraw verify-proof exports/tiff/captura.tiff.nexoraw.proof.json \
  --tiff exports/tiff/captura.tiff \
  --raw raw/captura.NEF

nexoraw metadata exports/tiff/captura.tiff --out config/metadata.json
```

## 8. Metodologia de perfilado

La metodologia se basa en capturar una carta bajo condiciones controladas,
revelarla en modo cientifico, detectar sus parches, comparar medidas contra una
referencia D50 y construir el perfil de sesion.

Recomendaciones:

- usar iluminacion estable y uniforme,
- evitar clipping en parches blancos y negros,
- mantener camara, lente, ISO, iluminante y exposicion comparables,
- enfocar la carta,
- evitar reflejos especulares,
- no mezclar capturas de carta y objetivos con ajustes de camara distintos,
- reservar una captura de validacion si se quiere QA independiente.

Estados de perfil:

- `draft`: generado sin validacion independiente suficiente.
- `validated`: supera criterios QA configurados.
- `rejected`: no supera umbrales de error.
- `expired`: supera vigencia temporal declarada.

## 9. Trazabilidad, NexoRAW Proof y C2PA

NexoRAW Proof crea un sidecar firmado con:

- SHA-256 del RAW,
- SHA-256 del TIFF final,
- hash de receta,
- hash de perfil ICC,
- hash de ajustes de render,
- metadatos relevantes,
- clave publica del firmante,
- fecha UTC,
- contexto de sesion.

C2PA/CAI se incrusta en el TIFF como capa interoperable cuando el SDK esta
disponible. Si el usuario configura credenciales externas y fallan, la
exportacion se aborta para no ocultar un error de firma. Si se usa la identidad
local autoemitida y no se puede completar C2PA, el TIFF sigue teniendo NexoRAW
Proof y el motivo queda registrado en el proof.

Reglas forenses:

1. No incrustar C2PA en RAW propietarios originales.
2. No registrar claves privadas ni fragmentos de claves.
3. No incluir el hash del TIFF firmado dentro del propio manifiesto C2PA
   embebido.
4. Calcular el hash del TIFF final tras la firma C2PA.
5. Mantener `batch_manifest.json` y auditoria lineal.

## 10. Artefactos generados

Artefactos habituales:

- `*.tiff`: TIFF final.
- `_linear_audit/*.tiff`: TIFF lineal de auditoria.
- `*.nexoraw.proof.json`: firma autonoma NexoRAW Proof.
- `batch_manifest.json`: manifiesto de lote.
- `profile_report.json`: reporte de perfil.
- `qa_session_report.json`: QA de sesion.
- `recipe_calibrated.yml`: receta calibrada.
- `*.profile.json`: sidecar del perfil ICC.
- overlays PNG de deteccion de carta.
- JSON de detecciones y muestras.

## 11. Rendimiento y cache

NexoRAW separa:

- preview rapida para navegacion,
- preview de alta calidad para revision,
- render final auditado.

Optimizaciones incluidas:

- caches de preview por archivo, receta y modo,
- miniaturas cacheadas y reescaladas sin repetir revelado,
- reutilizacion de ajustes de detalle cuando solo cambia tono/curva,
- salida versionada para evitar sobrescrituras,
- tareas largas en segundo plano con progreso global.

Buenas practicas:

- usar preview rapida solo para navegar,
- desactivarla al marcar cartas o revisar color,
- trabajar con carpetas de sesion razonables,
- limpiar colas antiguas,
- evitar recalcular perfil si solo se ajusta render final.

## 12. Problemas frecuentes

### AMaZE no funciona

AMaZE requiere soporte GPL3 en rawpy/LibRaw. Ejecutar:

```bash
python scripts/check_amaze_support.py
```

Si no esta disponible, usar DCB u otro algoritmo soportado.

### La deteccion de carta falla

- mejorar encuadre,
- evitar reflejos,
- usar carta completa,
- comprobar tipo de carta,
- usar `Marcar en visor` para guardar deteccion manual.

### El perfil produce imagen oscura o dominante

- comprobar que la referencia de carta corresponde a la carta real,
- revisar salida lineal/no lineal,
- comprobar que no se perfila desde TIFF incorrecto,
- verificar RAW global antes de generar perfil,
- revisar clipping y DeltaE.

### C2PA muestra `signingCredential.untrusted`

Es esperable con la identidad local de NexoRAW. Significa que el certificado no
pertenece a una lista central CAI, no que el vinculo RAW-TIFF sea invalido. Para
validez probatoria se conserva NexoRAW Proof, el hash RAW, el hash TIFF, la
receta, el perfil ICC y `batch_manifest.json`.

### Los metadatos C2PA aparecen ausentes

Comprobar `nexoraw check-c2pa`. Si el SDK no esta instalado o la firma local no
pudo completarse, la trazabilidad autonoma sigue estando en NexoRAW Proof.

### Falta matplotlib

NexoRAW no requiere `matplotlib` para el flujo actual. El aviso puede venir de
`colour-science`, que detecta funciones de graficado no disponibles. No afecta
al pipeline RAW, ICC, TIFF ni C2PA.

## 13. Documentacion relacionada

- [README](../README.md)
- [NexoRAW Proof](NEXORAW_PROOF.md)
- [C2PA/CAI](C2PA_CAI.md)
- [Integracion LibRaw + ArgyllCMS](INTEGRACION_LIBRAW_ARGYLL.md)
- [Licencias de terceros](THIRD_PARTY_LICENSES.md)
- [Changelog](../CHANGELOG.md)
