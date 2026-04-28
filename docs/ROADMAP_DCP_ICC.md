# Roadmap técnico — Integración DCP + ICC en NexoRAW

Documento de planificación para añadir soporte de perfiles DCP como
**perfil de entrada de cámara**, manteniendo el flujo ICC existente como
sistema formal de gestión, conversión, validación y salida.

Este roadmap es **planificación**, no contiene cambios de implementación. Se
escribe para servir de guía a tareas futuras, una por fase, sin romper el
funcionamiento ni los tests actuales.

---

## 1. Resumen ejecutivo

NexoRAW ya define una arquitectura ICC seria: revelado lineal con
LibRaw/rawpy, generación de perfil ICC de sesión con ArgyllCMS (`colprof`),
conversión CMM con `cctiff`, validación ΔE76/ΔE2000 sobre el ICC real e
incrustación del ICC en TIFF/JPEG/PNG, todo con auditoría JSON
(NexoRAW Proof, sidecar por RAW y manifest de batch).

El objetivo de este roadmap es **añadir DCP (DNG Camera Profile) como perfil
de entrada de cámara** sin desplazar el flujo ICC. En concreto:

- **Añadir soporte DCP**: detectar, registrar, hashear y, en fases
  posteriores, aplicar componentes colorimétricos del DCP.
- **Mantener ICC como flujo principal**: el ICC sigue siendo el portador
  formal del color en sesión y en salida; DCP es estrictamente
  *interpretación de la cámara*.
- **Separar modo científico/forense de modo visual**: una política
  declarativa (`dcp_policy: scientific | visual`) decide qué componentes
  del DCP se aplican (matrices vs. tone curve / hue-sat / look table).
- **Mejorar trazabilidad y reproducibilidad**: cada perfil empleado
  (DCP, ICC de sesión, ICC de salida, ICC de monitor) queda registrado con
  hash SHA-256 y rol explícito.
- **Evitar automatismos opacos**: ningún DCP se aplica de forma
  silenciosa. Si el DCP no es compatible con la cámara, o si su hash no
  coincide con el registrado, la operación falla con error explícito.

Principio rector: **DCP no sustituye a ICC**. DCP describe cómo
interpretar el RAW de una cámara concreta; ICC describe cómo gestionar y
convertir color formalmente entre espacios.

---

## 2. Estado actual del proyecto

Esta sección describe únicamente lo que está implementado hoy, con
referencias al código. No anticipa funcionalidades futuras.

### 2.1 Layout y nombres

- El paquete real de implementación es [src/iccraw/](../src/iccraw/).
- [src/nexoraw/](../src/nexoraw/) es un shim de compatibilidad
  ([src/nexoraw/__init__.py:1-9](../src/nexoraw/__init__.py)) durante el
  rename comercial del proyecto. **El roadmap propone alojar los nuevos
  módulos en `src/iccraw/color/`** para no introducir un código
  duplicado en `src/nexoraw/`. Si en el futuro se completa el rename,
  basta con re-exportar desde `nexoraw.color`.

### 2.2 Receta y guard científica

- El modelo de receta es la dataclass `Recipe` en
  [src/iccraw/core/models.py:59-82](../src/iccraw/core/models.py). Carga
  YAML/JSON en [src/iccraw/core/recipe.py:11](../src/iccraw/core/recipe.py).
- `scientific_guard()` ([src/iccraw/core/recipe.py:42-53](../src/iccraw/core/recipe.py))
  bloquea/avisa si en `profiling_mode=true` el usuario activa `denoise`,
  `sharpen`, `tone_curve` no lineal o `output_linear=false`.
- La receta **no contiene** hoy campos para perfil de entrada de cámara,
  perfil de sesión, perfil de salida ni perfil de monitor; el perfil
  efectivo se infiere de `output_space` y de la presencia o no de un ICC
  de sesión generado.

### 2.3 Pipeline RAW → lineal

- Punto de entrada: `develop_controlled()`
  ([src/iccraw/raw/pipeline.py:62-94](../src/iccraw/raw/pipeline.py)).
- Dos ramas:
  - `develop_scene_linear_array` → LibRaw con `output_color=raw` para
    preservar **camera RGB** (modo perfil de sesión).
  - `develop_standard_linear_array` → LibRaw revela directamente a sRGB,
    Adobe RGB (1998) o ProPhoto RGB (modo flujo sin carta).
- Render final aplica `exposure_compensation` y `tone_curve`
  (linear/srgb/gamma:N) en
  `render_recipe_output_array`
  ([src/iccraw/raw/pipeline.py:154-167](../src/iccraw/raw/pipeline.py)).
- Demosaicing soportado por `LIBRAW_DEMOSAIC_MAP` (DCB por defecto, AMaZE
  bajo build GPL3).

### 2.4 Generación y validación de perfil ICC

- ICC se construye con ArgyllCMS `colprof` desde muestras CGATS LAB/RGB
  ([src/iccraw/profile/builder.py:32-110](../src/iccraw/profile/builder.py)).
- Perfiles ICC estándar de salida (sRGB, AdobeRGB, ProPhoto) en
  [src/iccraw/profile/generic.py](../src/iccraw/profile/generic.py).
- Validación ΔE76/ΔE2000 con `xicclu` sobre el ICC real
  (`validate_profile`, [src/iccraw/profile/builder.py:159-188](../src/iccraw/profile/builder.py)).
- La matriz `matrix_camera_to_xyz` se conserva como diagnóstico, no
  sustituye al ICC real (documentado en [docs/INTEGRACION_LIBRAW_ARGYLL.md:111-114](INTEGRACION_LIBRAW_ARGYLL.md)).

### 2.5 Modos de gestión de color (export)

- `color_management_mode()`
  ([src/iccraw/profile/export.py:439-456](../src/iccraw/profile/export.py))
  decide entre:
  - `camera_rgb_with_input_icc` (master TIFF de sesión).
  - `converted_srgb` / `converted_adobe_rgb` / `converted_prophoto_rgb`
    (derivadas vía `cctiff` desde ICC de sesión).
  - `standard_<espacio>_output_icc` (flujo sin carta, ICC estándar
    incrustado).
  - `no_profile` (sin ICC).
- `write_signed_profiled_tiff()`
  ([src/iccraw/profile/export.py:527](../src/iccraw/profile/export.py))
  encadena export + firma NexoRAW Proof + C2PA opcional.

### 2.6 Trazabilidad y auditoría

- **Sidecar por RAW** `<file>.nexoraw.json`
  ([src/iccraw/sidecar.py](../src/iccraw/sidecar.py), schema
  `org.probatia.nexoraw.raw-sidecar.v1`): incluye receta, perfil de
  desarrollo, modo de gestión de color, ruta y hash SHA-256 del ICC
  asociado.
- **NexoRAW Proof** ([src/iccraw/provenance/nexoraw_proof.py](../src/iccraw/provenance/nexoraw_proof.py)):
  registra `color_management_mode`, `icc_profile_role`,
  `icc_profile_sha256`, `render_settings_sha256`, recipe completa y
  firma Ed25519. Es obligatorio para los TIFF finales.
- **C2PA opcional** ([src/iccraw/provenance/c2pa.py](../src/iccraw/provenance/c2pa.py)):
  añade `_raw_color_pipeline_trace()` (líneas 407-450) con metadatos
  declarativos del pipeline (engine LibRaw/rawpy, pasos lineales,
  espacio de trabajo, transformación de display y de export).
- **Manifest de batch** (dataclass `BatchManifest` en
  [src/iccraw/core/models.py:226](../src/iccraw/core/models.py)):
  `recipe_sha256`, `profile_path`, `color_management_mode`, ICC final.

### 2.7 Display ICC

- [src/iccraw/display_color.py](../src/iccraw/display_color.py) maneja
  el ICC del monitor exclusivamente para previsualización (Windows,
  macOS, Linux/colord). **El ICC de monitor no participa en revelado,
  master TIFF ni export** (invariante 9 en
  [docs/COLOR_PIPELINE.md:64](COLOR_PIPELINE.md)).

### 2.8 Lo que NO existe hoy

Confirmado por inspección:

- **Soporte DCP**: no hay parser, no hay aplicación de matrices DCP, no
  hay tone curve DCP, no hay HueSatMap, no hay LookTable, no hay
  ForwardMatrix, no hay BaselineExposure. Búsqueda
  `grep -r "DCP" src/` y `grep -r "forward_matrix" src/` devuelven cero
  resultados.
- **Registro central de perfiles** (DCP/ICC) por Make/Model con resolución
  determinista: existe parcialmente la generación per-sesión, pero no un
  `profile_registry` que permita resolver un perfil a partir de
  `EXIF.Make/Model` o a partir de un identificador declarado en la receta.
- **Política `scientific|visual`** explícita: hoy `profiling_mode=true`
  controla la guard de receta, pero no se proyecta sobre componentes de
  un DCP (porque no hay DCP).
- **Distinción explícita en la receta entre `camera_input_profile`,
  `session_profile`, `output_profile`, `display_profile`**: la receta
  actual mezcla los conceptos en `output_space` + presencia/ausencia de
  ICC de sesión.

### 2.9 Lo que no debe romperse

- El contrato `raw_developer: libraw` ([src/iccraw/raw/pipeline.py:111-113](../src/iccraw/raw/pipeline.py))
  y la matriz de demosaicing soportada.
- Las invariantes 1-9 del pipeline en
  [docs/COLOR_PIPELINE.md:44-66](COLOR_PIPELINE.md), en particular la
  separación asignación/conversión y el papel limitado del ICC de
  monitor.
- Los modos `camera_rgb_with_input_icc`, `converted_*` y
  `standard_*_output_icc` que ya están firmados en NexoRAW Proof y
  C2PA: añadir DCP no debe cambiar su semántica ni su nombre.
- El schema del sidecar (`schema_version: 1`); cualquier ampliación
  debe ser **aditiva** y mantener compatibilidad de lectura.
- El test suite actual (191 tests pasando salvo el caso de encoding
  pre-existente `test_selected_color_reference_images_update_reference_label_without_profile_marker`).

---

## 3. Arquitectura objetivo

Se proponen módulos nuevos en `src/iccraw/color/` (no en `src/nexoraw/`,
porque hoy el paquete real es `iccraw`). Cuando el rename a `nexoraw` se
complete, se añade un shim `src/nexoraw/color/__init__.py` que reexporta.

### 3.1 Módulos

#### `src/iccraw/color/dcp.py`

Responsabilidades:

- Parsear ficheros DCP (formato DNG SDK / Adobe DCP).
- Exponer una dataclass `DcpProfile` con campos:
  - `unique_camera_model` (string, identifica cámara de origen)
  - `profile_name` (string)
  - `calibration_illuminant_1`, `calibration_illuminant_2` (códigos LightSource EXIF)
  - `color_matrix_1`, `color_matrix_2` (3×3, opcionales)
  - `forward_matrix_1`, `forward_matrix_2` (3×3, opcionales)
  - `reduction_matrix_1`, `reduction_matrix_2` (3×3, opcionales)
  - `hue_sat_map_dims`, `hue_sat_map_data_1/2` (opcionales)
  - `look_table_dims`, `look_table_data` (opcional)
  - `tone_curve` (puntos opcional)
  - `baseline_exposure_offset` (float, opcional)
  - `default_black_render` (string)
  - `embed_policy` (allowed/copy_only/etc.)
  - `unique_id_sha256` (hash del DCP completo, calculado al cargar)
- Helpers: `load(path) -> DcpProfile`,
  `inspect_components(profile) -> list[str]`,
  `is_compatible(profile, exif_make, exif_model) -> bool`.
- Punto de extensión: `apply_matrices(image_camera_rgb, profile, illuminant_xy) -> image_xyz`.
  En fases iniciales puede estar `NotImplementedError`; debe declararse
  explícitamente que aún no se aplica.

#### `src/iccraw/color/icc.py`

Responsabilidades:

- Centralizar lectura/escritura/inspección de ICC ya repartidos por
  [profile/builder.py](../src/iccraw/profile/builder.py),
  [profile/export.py](../src/iccraw/profile/export.py) y
  [profile/generic.py](../src/iccraw/profile/generic.py). No reescribirlos:
  exponer fachadas estables (`describe(path)`, `sha256(path)`,
  `embed(tiff_bytes, icc_bytes)`) y consolidar la API que usa el resto.
- Ofrecer `assign_icc(image, icc_path)` y `convert_icc(image, src_icc, dst_icc)`
  como dos operaciones nominalmente distintas (refleja invariante 3 de
  [docs/COLOR_PIPELINE.md:48-50](COLOR_PIPELINE.md)).
- Helpers de validación: clase, dispositivo (Input/Display/Output), PCS,
  TRC, dimensión LUT, tag list — necesarios para que `profile_registry`
  pueda decidir si un fichero es válido como `camera_input`,
  `session`, `output` o `display`.

#### `src/iccraw/color/profile_registry.py`

Responsabilidades:

- Mantener un índice `cameras.yaml` (provisto por el proyecto y/o por el
  usuario) con entradas:
  ```yaml
  - make: NIKON CORPORATION
    model: NIKON D850
    dcp:
      path: profiles/dcp/nikon-d850-d65.dcp
      sha256: 3a...
    notes: "Perfil de fábrica para D850 a D65"
  ```
- Resolver un DCP/ICC a partir de:
  1. ruta explícita en la receta;
  2. identificador lógico en la receta + lookup en el registro;
  3. `EXIF.Make/Model` del RAW + lookup en el registro.
- Verificar SHA-256 del fichero contra el registrado y **fallar** si no
  coincide. Nada de fallback silencioso.
- API: `resolve_camera_input(recipe, raw_metadata) -> ResolvedProfile`,
  `register_profile(path, kind, sha256) -> RegistryEntry`.
- Persistir warnings (sustituciones, fallback declarado a matriz LibRaw)
  en una estructura serializable que se incrusta en el sidecar y en
  NexoRAW Proof.

#### `src/iccraw/color/color_pipeline.py`

Responsabilidades:

- Orquestador que coordina:
  ```
  RAW → LibRaw lineal camera RGB
      → camera input profile (DCP | ICC entrada | matriz LibRaw)
      → working space (sesión)
      → session ICC opcional
      → output ICC + incrustación
  ```
- Punto único donde se aplica la **política `scientific|visual`** sobre
  los componentes del DCP (ver §5).
- Genera el bloque `color_pipeline_trace` que se embebe en sidecar,
  NexoRAW Proof y C2PA. Sustituye/extiende el actual
  `_raw_color_pipeline_trace()`
  ([src/iccraw/provenance/c2pa.py:407-450](../src/iccraw/provenance/c2pa.py))
  con los nuevos campos (DCP, política, componentes aplicados/omitidos).
- No reimplementa lo que ya existe: delega revelado en
  `iccraw.raw.pipeline`, ICC build/validate en `iccraw.profile.builder`
  y CMM/export en `iccraw.profile.export`.

### 3.2 Recipe extensions (declarativas, opcionales, aditivas)

Campos nuevos opcionales en `Recipe`:

```yaml
camera_input_profile:
  kind: dcp | icc | libraw_matrix
  path: profiles/dcp/nikon-d850-d65.dcp   # opcional si se resuelve por registry
  sha256: 3a...                           # opcional, validado si presente
  illuminant_hint: D65                    # opcional, para selección DCP dual-illuminant
dcp_policy: scientific | visual            # default scientific
session_profile:
  path: ...
  sha256: ...
output_profile:
  kind: standard | custom
  space: srgb | adobe_rgb | prophoto_rgb
  path: ...                               # solo si custom
display_profile:
  source: system | manual
  path: ...                               # solo si manual
  scope: preview_only                     # invariante: no afecta export
```

Compatibilidad: si todos estos campos están ausentes, NexoRAW debe
seguir comportándose exactamente como hoy.

---

## 4. Modelo conceptual DCP + ICC

### 4.1 ¿Qué hace cada uno?

- **DCP** (DNG Camera Profile) describe **cómo interpretar el RAW de una
  cámara concreta**: matrices de cámara → XYZ para uno o dos
  iluminantes, opcionalmente forward matrices, hue/sat map (perceptual),
  look table (perceptual), tone curve y baseline exposure. Es un
  *perfil de interpretación de cámara*.
- **ICC** describe **cómo gestionar y convertir color formalmente**:
  perfiles de entrada (Input/Scanner), de espacio de trabajo
  (Display/Workspace), de salida (Output) y de monitor (Display). Es la
  representación interoperable y el portador de color en archivos
  finales.

### 4.2 Cuatro perfiles, cuatro roles

| Rol | Qué describe | Ejemplo NexoRAW actual | Ejemplo objetivo (DCP+ICC) |
|---|---|---|---|
| Perfil de entrada de cámara | RAW camera RGB → XYZ | matriz LibRaw o ICC sesión generado | DCP de cámara o ICC de entrada o matriz LibRaw (fallback) |
| Perfil de sesión | RGB de sesión usado en edición lineal | `scene_linear_camera_rgb` + ICC sesión incrustado | igual; el DCP no lo sustituye, lo *alimenta* |
| Perfil de salida | espacio donde se entrega la imagen | sRGB / AdobeRGB / ProPhoto | igual; ICC custom adicionalmente |
| Perfil de monitor | corrección visual en pantalla | ICC del sistema, solo preview | igual; **invariante: no se incrusta jamás en exports** |

### 4.3 Asignar vs. convertir

- **Asignar perfil**: declarar cómo deben interpretarse los píxeles
  actuales sin transformarlos. Ej.: incrustar ICC de sesión en un TIFF
  cuyos píxeles son RGB lineal de cámara.
- **Convertir perfil**: aplicar una transformación CMM (ArgyllCMS
  `cctiff`, LittleCMS) que cambia los valores de los píxeles del espacio
  origen al espacio destino. Ej.: derivar un TIFF sRGB desde el TIFF
  master con ICC de sesión.
- DCP siempre "asigna" en el sentido de que define la transformación
  *desde* camera RGB; cuando aplicamos el DCP estamos convirtiendo
  camera RGB → XYZ, no asignando un perfil arbitrario a los píxeles.

### 4.4 Por qué el ICC de monitor nunca debe afectar a exports

El ICC de monitor describe la respuesta del *display físico* del
operador. Si se incrustara o aplicara al export, el archivo entregado
contendría datos calibrados para un monitor específico, no para un
flujo formal de color. Esto rompería interoperabilidad, validación
ΔE y trazabilidad. NexoRAW ya documenta esta invariante en
[docs/COLOR_PIPELINE.md:64-66](COLOR_PIPELINE.md) y la separa en
[src/iccraw/display_color.py](../src/iccraw/display_color.py); el
roadmap la mantiene literal.

---

## 5. Modos de trabajo

La política se declara en la receta como `dcp_policy` y se evalúa
explícitamente en `color_pipeline.py`.

### 5.1 Modo científico / forense (default)

Prioriza linealidad, neutralidad y trazabilidad. **Por defecto**:

- **Aplicar**: `color_matrix_1`/`color_matrix_2` (con interpolación
  según iluminante) y, si está presente y es compatible,
  `forward_matrix_1`/`forward_matrix_2`.
- **No aplicar** (en modo científico):
  - `tone_curve` del DCP,
  - `look_table` (LookTable),
  - `hue_sat_map` (perceptual),
  - `baseline_exposure_offset` (a menos que se declare explícitamente y
    se registre como ajuste no neutral),
  - cualquier ajuste creativo no documentado en el DCP.
- **Registrar en auditoría** todos los componentes presentes y todos
  los componentes omitidos por política.
- **Validar ΔE** sobre el ICC final, después de las matrices del DCP y
  antes de cualquier curva o look perceptual.

### 5.2 Modo visual / documental

Permite un revelado más perceptual, manteniendo trazabilidad:

- Permite `tone_curve`, `look_table`, `hue_sat_map`,
  `baseline_exposure_offset`.
- Debe etiquetarse claramente en sidecar, NexoRAW Proof y C2PA con
  `dcp_policy: visual` y la lista de componentes aplicados.
- No debe presentarse como "validación científica" en informes.
- ΔE puede calcularse, pero el informe debe avisar de que el resultado
  incluye transformaciones perceptuales.

### 5.3 Reglas comunes

- **Cualquier cambio de política** entre dos sesiones debe regenerar
  hashes de receta (`recipe_sha256`) y de render
  (`render_settings_sha256`); ninguna salida debe heredar firma de un
  modo anterior.
- En CLI y GUI, el modo visual debe avisar con un texto claro tipo
  *"Modo visual: incluye transformaciones perceptuales del DCP. No
  apto para validación colorimétrica estricta."*

---

## 6. Roadmap por fases

Cada fase contiene entregables concretos. Las fases iniciales no
aplican DCP; sólo construyen la arquitectura, configuración y
auditoría sobre las que las fases avanzadas pueden actuar.

### FASE 0 — Auditoría del estado actual

Objetivo: cerrar la inventory antes de tocar código.

- Confirmar puntos de entrada/salida del pipeline de color.
- Listar todos los lugares donde se lee/escribe ICC, se incrusta o se
  ejecuta `cctiff`/`xicclu`/`colprof`.
- Listar todos los campos de auditoría relacionados con color
  (`color_management_mode`, `icc_profile_*`, `raw_color_pipeline`,
  `render_settings`).
- Detectar dependencias externas (Argyll, ExifTool, AMaZE, LittleCMS).
- Documentar limitaciones conocidas (single-illuminant, ausencia de
  baseline exposure, etc.).

Entregable: un `docs/COLOR_AUDIT.md` (o sección en este roadmap, si se
prefiere mantenerlo único) con el inventario en formato tabla. **No
modifica código.**

### FASE 1 — Modelo de configuración y receta YAML

Objetivo: introducir los nuevos campos opcionales en `Recipe` sin
romper recetas existentes.

- Añadir `camera_input_profile`, `session_profile`, `output_profile`,
  `display_profile`, `dcp_policy` a `Recipe` y a su normalizador
  ([src/iccraw/core/recipe.py](../src/iccraw/core/recipe.py)).
- Si todos los campos nuevos están vacíos, NexoRAW se comporta exactamente
  como hoy.
- Validar mutuamente excluyentes (no se puede declarar `kind: dcp` con
  `path` apuntando a un `.icc`, etc.).
- Errores claros: `"DCP declarado pero no encontrado: <path>"`,
  `"sha256 declarado no coincide con el fichero"`.
- Registrar como `fallback` cuando se cae a matriz LibRaw porque no hay
  DCP/ICC de entrada disponibles.

Entregable: campos en `Recipe` + tests YAML/JSON + esquemas de error.

### FASE 2 — Registro de perfiles y trazabilidad

Objetivo: tener un único punto de resolución de perfiles, con hashes y
warnings.

- Crear [src/iccraw/color/profile_registry.py](../src/iccraw/color/profile_registry.py)
  (no existe hoy).
- Indexar `cameras.yaml` (en
  `src/iccraw/resources/profiles/cameras.yaml` o similar). Inicialmente
  vacío; el usuario añade entradas.
- API mínima: `resolve_camera_input`, `register_profile`,
  `verify_sha256`, `list_profiles_for(make, model)`.
- Calcular SHA-256 de DCP e ICC al registrarlos.
- Impedir sustituciones silenciosas: cualquier reemplazo o fallback
  emite un warning estructurado que llega al sidecar y a NexoRAW
  Proof (campo nuevo `color.profile_resolution_warnings`).

Entregable: registry + warnings + tests unitarios. **Aún no se aplica
ningún DCP**.

### FASE 3 — Soporte básico DCP no destructivo

Objetivo: poder declarar y verificar un DCP en la receta sin
aplicarlo todavía.

- Crear [src/iccraw/color/dcp.py](../src/iccraw/color/dcp.py).
- Implementar `load(path) -> DcpProfile` mínimo: parsear estructura
  DCP, exponer metadatos (nombre, cámara, iluminantes), calcular
  `unique_id_sha256`.
- Comprobar compatibilidad por `unique_camera_model` o por
  `EXIF.Make/Model` del RAW. Si no coinciden, **error**.
- En el pipeline actual: si la receta declara un DCP, se loguea, se
  registra en el sidecar y NexoRAW Proof, **pero el revelado sigue
  igual** (LibRaw camera matrix). Documentar esto explícitamente como
  `dcp_state: declared_not_applied` en la auditoría.
- No simular soporte completo: cualquier intento de "aplicar DCP" en
  esta fase debe producir error si el código aún no lo implementa.

Entregable: `dcp.py` + integración no destructiva + tests con un DCP
de prueba de cámara conocida.

### FASE 4 — Inspección avanzada DCP

Objetivo: saber qué componentes contiene un DCP y poder mostrarlos.

- Detectar y exponer en `DcpProfile`:
  - color matrix (1/2),
  - forward matrix (1/2),
  - reduction matrix,
  - hue/sat map,
  - tone curve,
  - look table,
  - baseline exposure / offset.
- API `inspect_components(profile) -> dict` que liste presentes y
  ausentes.
- CLI `nexoraw inspect-dcp <path>` y reflejo en GUI (lectura, no
  edición).
- Registrar en sidecar y NexoRAW Proof, por cada render, qué
  componentes existen y cuáles **se aplicarán o se omitirán** según la
  política del momento (aunque la aplicación efectiva venga en fase 6).

Entregable: inspección + CLI + tests con DCPs de muestra.

### FASE 5 — Política `scientific` / `visual`

Objetivo: implementar la política y bloquear/permitir según modo.

- Añadir `dcp_policy` a `Recipe` (ya en fase 1, ahora se hace efectivo).
- En color_pipeline: si `dcp_policy=scientific`, lista negra explícita
  de componentes (tone curve, look table, hue/sat, baseline_exposure
  no documentado).
- Si `visual`, permitirlos pero etiquetar.
- Errores y warnings claros en CLI; en GUI, indicador visual
  ("modo científico / modo visual") y diálogo de confirmación al
  cambiar de uno a otro.
- Registrar política y componentes filtrados en NexoRAW Proof y C2PA.

Entregable: política + tests + UI/CLI flags.

### FASE 6 — Aplicación efectiva de DCP

Objetivo: aplicar realmente las matrices DCP (y opcionalmente
componentes perceptuales en modo visual).

- Investigación previa: qué librerías permiten aplicar DCP completo
  (matrices duales con interpolación, forward matrix, hue/sat,
  baseline exposure, tone curve). Candidatas:
  - implementación propia con `numpy` y la spec DCP/DNG (pública pero
    extensa);
  - `colour-science` (parcial),
  - bindings de `dcraw`/`libraw` que soporten DCP de forma controlada,
  - integración con RawTherapee como referencia metodológica (no como
    runtime).
- Definir alcance soportado en esta fase: probablemente *sólo
  matrices* (color matrix interpolada por iluminante, opcionalmente
  forward matrix). Documentar explícitamente el subconjunto cubierto.
- Escribir `apply_camera_input(image_camera_rgb, profile, illuminant_hint) -> image_xyz`
  con tests de regresión sobre RAWs controlados (Macbeth, IT8) y
  comparación contra el flujo ICC actual.
- No romper el flujo ICC existente: cuando no hay DCP, el comportamiento
  debe ser el de hoy.

Entregable: aplicación parcial documentada + suite de regresión + nota
metodológica en CHANGELOG.

### FASE 7 — Integración ICC reforzada

Objetivo: revisar que el ICC sigue funcionando como contrato formal,
incluso con DCP en juego.

- Reverificar invariantes 1-9 de
  [docs/COLOR_PIPELINE.md:44-66](COLOR_PIPELINE.md), añadiendo:
  - 10. *El DCP, si se aplica, lo hace antes del ICC de sesión y nunca
    sustituye al ICC en el archivo final.*
  - 11. *El ICC de monitor sigue siendo preview-only.*
- Auditar `write_profiled_tiff` y `_write_converted_output_tiff_with_argyll`
  ([src/iccraw/profile/export.py:473-708](../src/iccraw/profile/export.py))
  para asegurar que la incrustación ICC sigue siendo bytewise idéntica
  con/sin DCP.
- Tests que verifiquen embedded ICC en TIFF/JPEG/PNG.
- Tests que verifiquen que el display_profile no aparece nunca en un
  archivo final.

Entregable: tests de invariantes + nota en COLOR_PIPELINE.md.

### FASE 8 — CLI

- `nexoraw inspect-dcp <path>`
- `nexoraw register-profile --kind dcp|icc <path>`
- `nexoraw develop --camera-dcp <path> [--dcp-policy scientific|visual]`
- `nexoraw batch-develop --camera-dcp <path>`
- Mensajes de error consistentes:
  - "DCP no compatible con la cámara: <make>/<model> vs <unique_camera_model>"
  - "SHA-256 del DCP no coincide con el registrado"
  - "Modo visual seleccionado: se aplicarán transformaciones perceptuales"

Entregable: ampliación de [src/iccraw/cli.py](../src/iccraw/cli.py) +
tests de invocación + ayuda actualizada.

### FASE 9 — GUI

- Selector de **DCP** en el panel de receta/calibración.
- Selector de **política** (`Científico` / `Visual`) con explicación
  inline.
- Indicador de compatibilidad de cámara (✓ / ✗ con motivo).
- Mostrar SHA-256 del DCP/ICC en uso (truncado, con copy).
- Aviso explícito si se activan componentes perceptuales (banner
  amarillo o icono).
- Internacionalización: añadir cadenas a `locales/en.ts` y recompilar
  `en.qm`.

Entregable: panel GUI + traducciones + smoke manual.

### FASE 10 — Tests

A lo largo de las fases anteriores se irán añadiendo tests; esta fase
consolida la cobertura mínima:

- Unitarios: `Recipe` con campos nuevos, parser DCP, registry,
  política.
- Recetas YAML de ejemplo con DCP, sin DCP, sólo ICC, mixto.
- Fallback a matriz LibRaw cuando no hay DCP/ICC.
- Hash mismatch produce error.
- Sidecar / NexoRAW Proof contienen los nuevos campos.
- TIFF/JPEG firmado lleva ICC esperado y no lleva el `display_profile`.
- Política `scientific` filtra componentes perceptuales.
- Política `visual` los permite y los etiqueta.

Entregable: `tests/test_dcp_*.py`, `tests/test_color_pipeline.py`,
`tests/test_profile_registry.py`. CI verde.

### FASE 11 — Documentación

- Actualizar [docs/COLOR_PIPELINE.md](COLOR_PIPELINE.md) y su
  versión `.es.md` con el nuevo modelo de cuatro perfiles.
- Actualizar [docs/ARCHITECTURE.md](ARCHITECTURE.md) con los nuevos
  módulos `iccraw.color.*`.
- Añadir ejemplos de receta YAML en `examples/recipes/dcp_*.yml`.
- Añadir explicación DCP vs ICC reusable como referencia.
- Documentar advertencias metodológicas (subconjunto del DCP soportado,
  iluminante asumido, etc.).
- Actualizar [README.md](../README.md) si procede (mención mínima).

Entregable: docs + ejemplos + README actualizado.

### FASE 12 — Validación científica

- Preparar dataset de prueba con varios RAWs y carta ColorChecker o
  IT8 bajo iluminante conocido (D50/D65).
- Generar 4 ramas de revelado:
  1. perfil genérico (sin carta, sin DCP),
  2. ICC de sesión actual (carta + colprof),
  3. DCP solo (matrices, sin curva),
  4. DCP + ICC de sesión.
- Medir ΔE76 y ΔE2000 sobre los parches y reportar diferencias.
- Documentar:
  - límites observados (efecto del iluminante asumido, dispersión por
    parche),
  - cuándo DCP+ICC mejora,
  - cuándo no aporta o introduce ruido.
- Generar `docs/VALIDATION_DCP_ICC.md` con metodología, números y
  conclusiones.

Entregable: informe técnico + dataset (o referencias al dataset).

---

## 7. Dependencias técnicas

### 7.1 Cubierto por la arquitectura actual

- Lectura/escritura ICC, embed en TIFF, conversión CMM con Argyll
  `cctiff`/`xicclu`, build con `colprof`. Todo presente
  ([src/iccraw/profile/builder.py](../src/iccraw/profile/builder.py),
  [src/iccraw/profile/export.py](../src/iccraw/profile/export.py)).
- Lectura RAW lineal con LibRaw/rawpy
  ([src/iccraw/raw/pipeline.py](../src/iccraw/raw/pipeline.py)).
- Auditoría JSON, sidecar, NexoRAW Proof
  ([src/iccraw/sidecar.py](../src/iccraw/sidecar.py),
  [src/iccraw/provenance/nexoraw_proof.py](../src/iccraw/provenance/nexoraw_proof.py)).
- Display ICC preview con LittleCMS/ImageCms
  ([src/iccraw/display_color.py](../src/iccraw/display_color.py)).

### 7.2 Requiere rawpy/LibRaw

- Demosaicing (DCB / AMaZE GPL3 si build lo incluye).
- Camera matrix embebida del RAW (cuando exista) — útil para fallback.
- Acceso a `EXIF.Make/Model` para resolución por registry.

### 7.3 Requiere ArgyllCMS

- `colprof` (build de ICC sesión).
- `cctiff` (conversión CMM).
- `xicclu`/`icclu` (validación ΔE).
- ICCs estándar de referencia para flujo sin carta.

### 7.4 Requiere LittleCMS (vía Pillow ImageCms)

- Conversión preview de monitor.
- Posible uso futuro para conversiones "simples" en pipeline (no
  reemplaza Argyll para validación).

### 7.5 Posibles librerías adicionales para DCP

- **Implementación propia con `numpy`** sobre la spec DCP/DNG: control
  total, no añade dependencias, esfuerzo significativo. *Probable
  camino preferente para el subconjunto matrices*.
- **`colour-science`** (ya dependencia del proyecto, ver
  [pyproject.toml:29](../pyproject.toml)): no incluye parser DCP
  completo, pero ofrece transformaciones colorimétricas (XYZ, RGB,
  iluminantes) que sirven de base.
- **RawTherapee** como referencia metodológica (no como runtime); su
  documentación pública es la mejor guía sobre componentes DCP.
- **Adobe DNG SDK** (C++, GPL/MIT mixta): referencia normativa, no
  binding Python directo. Riesgo de licencias si se enlaza.

### 7.6 Partes del formato DCP no soportadas inicialmente

- Tone curve y look table en modo científico (deliberado, por política).
- Profile pairs con illuminantes no estándar (D50/D55/D65/D75 son los
  habituales; otros illuminantes pueden requerir interpolación cuidadosa).
- DCPs cifrados o con `embed_policy: no_copy`.
- DCPs que dependan de ProfileLookTableDims con dimensiones inusuales.

### 7.7 Riesgos al aplicar DCP parcialmente

- Si se aplican matrices pero no la baseline exposure correspondiente,
  el rango tonal puede quedar desplazado respecto a la referencia
  Adobe.
- Si se interpolan dos color matrices con un iluminante asumido
  incorrecto, el ΔE puede empeorar.
- Si se aplica `forward_matrix` sin la chromatic adaptation correcta,
  los neutros pueden derivar.
- Estos riesgos justifican el modo científico como default y el
  registro detallado de iluminante y componentes.

---

## 8. Riesgos metodológicos

Lista explícita de errores que el roadmap **debe prevenir**:

1. **Aplicar curvas creativas en modo científico** — bloqueado por
   `dcp_policy=scientific` y por `scientific_guard()` extendido.
2. **Conversión prematura a sRGB** — sigue prohibido cuando el flujo
   tiene ICC de sesión (master TIFF en camera RGB con ICC sesión
   incrustado, derivados aparte).
3. **Aplicar perfiles en orden incorrecto** — el orden canónico es
   `LibRaw → DCP/ICC entrada → working space → ICC sesión → CMM →
   ICC salida`. Cualquier otro orden debe rechazarse.
4. **Usar perfil de monitor para exportar** — invariante 9 actual
   ampliada a invariante 11 (§6 fase 7).
5. **Usar DCP incompatible con otra cámara** — bloqueado por
   verificación `unique_camera_model`/EXIF.
6. **Sustituir perfiles silenciosamente** — el registry verifica
   SHA-256, los warnings se persisten. Cualquier no-coincidencia es
   error.
7. **Confundir perfil de entrada con perfil de salida** — la receta los
   declara como campos distintos; la GUI no permite asignar uno como
   el otro.
8. **Validar ΔE después de transformaciones perceptuales** —
   informes en modo visual incluyen banner; ΔE estricto requiere modo
   científico.

---

## 9. Criterios de aceptación por fase

| Fase | Entregables | Pruebas mínimas | Documentación | "Hecha" cuando |
|---|---|---|---|---|
| 0 | Inventario de color | n/a | `COLOR_AUDIT.md` (o sección) | Lista de invariantes y ficheros revisada y aprobada |
| 1 | Campos receta | parser YAML/JSON, normalizador, errores | ejemplo en `examples/recipes/` | Receta con campos vacíos = comportamiento actual; receta con campos llenos pasa validación |
| 2 | `profile_registry` | unit tests resolución + hash mismatch | sección en `ARCHITECTURE.md` | Resolver por make/model y por path; warnings persistidos |
| 3 | DCP load + declarar | parser DCP, compatibilidad cámara | nota en `COLOR_PIPELINE.md` | DCP declarado aparece en sidecar/Proof con `dcp_state: declared_not_applied` |
| 4 | Inspección DCP | dict componentes, CLI inspect-dcp | sección DCP en `COLOR_PIPELINE.md` | `nexoraw inspect-dcp` lista todos los componentes presentes |
| 5 | Política | tests política sci/visual + guard | sección política | En sci, perceptuales bloqueados; en visual, permitidos y etiquetados |
| 6 | Aplicación matrices DCP | regresión Macbeth/IT8 | nota metodológica + alcance soportado | ΔE estable y reproducible; flujo ICC actual no se rompe |
| 7 | ICC reforzado | tests embed/no-embed display | invariantes 10-11 en `COLOR_PIPELINE.md` | Tests pasan; auditoría refleja DCP+ICC |
| 8 | CLI | tests invocación + help | ayuda CLI | `nexoraw develop --camera-dcp ...` end-to-end |
| 9 | GUI | smoke manual + traducciones | sección GUI | Selector + indicador compatibilidad operativos |
| 10 | Tests consolidados | cobertura DCP + política | n/a | CI verde con DCP de ejemplo |
| 11 | Documentación | n/a | `COLOR_PIPELINE.md`, `ARCHITECTURE.md`, README | Docs actualizadas y revisadas |
| 12 | Validación científica | dataset + ΔE | `VALIDATION_DCP_ICC.md` | Informe entregado |

---

## 10. Orden recomendado de implementación

El principio rector es: **construir trazabilidad y configuración antes
que aplicación efectiva**. Los primeros pasos no aplican DCP de forma
real; sólo permiten declararlo, validarlo y dejar trazabilidad. La
aplicación colorimétrica completa llega cuando esté claro qué
subconjunto del formato podemos soportar correctamente.

Orden propuesto:

1. **Fase 0** — auditoría y cierre del inventario.
2. **Fase 1** — campos opcionales en `Recipe`. Cero impacto si están
   vacíos.
3. **Fase 2** — `profile_registry` con resolución por path / make-model
   y verificación SHA-256.
4. **Fase 3** — soporte DCP "declarativo": el DCP puede declararse,
   verificarse y registrarse en auditoría, pero **no se aplica**.
5. **Fase 4** — inspección DCP: saber qué tiene el perfil, mostrarlo en
   CLI/GUI, listar componentes que se aplicarán u omitirán según
   política.
6. **Fase 5** — política `scientific` / `visual` activa, sin aplicar
   todavía, sólo para reflejarse en auditoría y bloquear configuraciones
   inconsistentes (p. ej. modo científico con tone curve creativa).
7. **Fase 6** — aplicación efectiva del DCP, *empezando por matrices y
   forward matrix*. Documentar explícitamente el subconjunto cubierto y
   medir ΔE contra el flujo ICC actual.
8. **Fase 7** — endurecer ICC: añadir invariantes 10-11 y tests de
   embed/no-embed.
9. **Fase 8 + 9** — CLI y GUI en paralelo, una vez la aplicación es
   estable.
10. **Fase 10** — consolidar tests.
11. **Fase 11** — documentación final.
12. **Fase 12** — validación científica con dataset y publicación de
    resultados.

Con este orden, después de la fase 5 NexoRAW puede ya **aceptar DCPs en
recetas, validarlos, registrarlos y dejar trazabilidad completa**, sin
aplicar todavía ninguna transformación. Esto cubre buena parte del
valor metodológico (declaración explícita y auditable) sin asumir
ninguna decisión colorimétrica que no esté validada por las fases 6 y
12.

---

## Apéndice A — Preguntas abiertas

Cuestiones técnicas que requieren decisión o investigación antes de
implementar:

- **A1**. ¿Implementación propia de aplicación DCP en `numpy` vs.
  binding a una librería existente? Decisión bloquea la fase 6.
- **A2**. ¿Cómo seleccionar el iluminante cuando un DCP tiene dos? La
  opción más rigurosa es estimar el iluminante de la escena desde WB
  as-shot; la más simple es exigir que la receta lo declare
  (`illuminant_hint`). El roadmap propone empezar por declarado y
  añadir estimación más adelante.
- **A3**. ¿Cómo combinar DCP + ICC de sesión sin doble corrección?
  Opción a) DCP solo en flujo sin carta; ICC de sesión en flujo con
  carta; b) DCP siempre como entrada, ICC de sesión como refinamiento
  posterior. Requiere validación experimental (fase 12) antes de fijar.
- **A4**. ¿Quién mantiene `cameras.yaml`? ¿Comunidad, autor, fork por
  laboratorio? Afecta a la cadena de custodia: un registro firmado
  centralmente da más garantías.
- **A5**. ¿Compatibilidad con DCPs cifrados / `embed_policy: no_copy`?
  Decisión legal + técnica.
- **A6**. ¿Persistencia del estado del registry (DB ligera, ficheros
  JSON, ambos)? Afecta a la portabilidad entre máquinas y a la
  reproducibilidad cross-equipo.
