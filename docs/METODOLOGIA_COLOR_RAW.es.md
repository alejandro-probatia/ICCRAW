# Metodología de Revelado RAW y Gestión ICC

_English version: [METODOLOGIA_COLOR_RAW.md](METODOLOGIA_COLOR_RAW.md)_

Este documento fija el criterio metodológico de NexoRAW para separar revelado
paramétrico, perfil de ajuste, perfil ICC de entrada, perfiles ICC de salida y
perfil ICC del monitor.

La decisión vigente es mantener un flujo científico centrado en ICC. La
integración DCP fue evaluada como posibilidad futura, pero no forma parte del
alcance activo de la serie 0.2 porque añade complejidad y puede mezclar
decisiones colorimétricas con decisiones de apariencia.

## Referencias Consultadas

- RawTherapee, `Sidecar Files - Processing Profiles`:
  https://rawpedia.rawtherapee.com/Sidecar_Files_-_Processing_Profiles
- RawTherapee, `Color Management`:
  https://rawpedia.rawtherapee.com/Color_Management
- RawTherapee, `ICC Profile Creator`:
  https://rawpedia.rawtherapee.com/ICC_Profile_Creator

## Criterio Conceptual

Un RAW no es una imagen RGB final. Es una captura de datos del sensor que debe
interpretarse mediante una receta de revelado: demosaico, balance de blancos,
nivel negro, compensación de exposición, curva tonal, espacio de salida y otros
parámetros.

En NexoRAW, el perfil ICC de entrada no se calcula sobre el RAW desnudo. Se
calcula después de revelar una captura de carta con una receta controlada,
porque las mediciones se hacen sobre valores RGB producidos por el revelador.
Una vez generado, ese ICC describe cómo interpretar los RGB de cámara/sesión
producidos por esa misma receta, cámara e iluminante.

Por tanto:

- la receta corrige y documenta el revelado base;
- el perfil de ajuste guarda decisiones paramétricas por archivo;
- el ICC de entrada describe la respuesta colorimétrica medida de la sesión;
- el ICC de salida describe el espacio final cuando no hay carta o cuando se
  genera un derivado convertido;
- el ICC de monitor solo corrige la visualización.

## Flujo Técnico Recomendado

El contrato metodológico para RAW es:

1. Abrir el RAW con LibRaw/rawpy.
2. Leer modelo de cámara, CFA, black level, white level, white balance as-shot,
   matriz de cámara y perfil embebido cuando existan.
3. Normalizar datos RAW a `float32` lineal.
4. Aplicar sustracción de negro y normalización por blanco.
5. Aplicar balance de blancos en espacio de cámara.
6. Ejecutar demosaico.
7. Producir RGB lineal de cámara/sesión o revelar directamente a un espacio
   estándar cuando no hay carta.
8. Aplicar ajustes paramétricos documentados.
9. Para pantalla, convertir la preview al perfil ICC del monitor si está activo.
10. Para exportación, incrustar el ICC correspondiente y registrar la
    transformación aplicada.

Implementación actual:

- con carta, NexoRAW conserva RGB lineal de cámara/sesión e incrusta el ICC de
  entrada generado;
- sin carta, NexoRAW revela en `sRGB`, `Adobe RGB (1998)` o `ProPhoto RGB` y
  copia/incrusta un ICC estándar real;
- los derivados convertidos desde un ICC de sesión se procesan mediante
  CMM/ArgyllCMS cuando corresponde;
- el perfil del monitor nunca modifica TIFF, hashes, manifiestos ni Proof.

## Perfil de Ajuste por Archivo

NexoRAW 0.2 trata el revelado paramétrico como una propiedad asignada a cada RAW
mediante su mochila:

```text
captura.NEF
captura.NEF.nexoraw.json
```

Una sesión puede contener varios perfiles de ajuste. Esto evita asumir que toda
la sesión es homogénea: una carpeta puede incluir cambios de luz, óptica,
exposición o criterio de salida.

Tipos:

- **Perfil avanzado**: nace de una carta de color y puede incluir ICC de entrada
  de sesión.
- **Perfil básico**: nace de ajustes manuales y se asocia a un ICC estándar si no
  hay carta.

## Flujo Con Carta de Color

Cuando existe una captura válida de carta:

1. Revelar la carta con una receta científica base.
2. Detectar y medir parches de la carta.
3. Generar un perfil de revelado: balance de blancos, densidad y exposición
   derivados de la carta.
4. Medir de nuevo la carta con la receta calibrada.
5. Generar el ICC de entrada de sesión con ArgyllCMS a partir de RGB medidos y
   referencias colorimétricas.
6. Guardar por separado perfil de ajuste, receta calibrada, ICC de entrada,
   reportes QA y overlays.
7. Revelar los RAW equivalentes con ese perfil.
8. Crear TIFF maestro manteniendo RGB de cámara/sesión e incrustando el ICC de
   entrada.

El perfil avanzado puede copiarse a imágenes tomadas bajo condiciones
comparables de cámara, óptica, iluminante, exposición base y receta.

## Flujo Sin Carta de Color

Cuando no existe carta:

1. No se inventa un ICC de sesión.
2. El usuario guarda un perfil de ajuste manual.
3. El usuario elige un espacio estándar real de salida: `sRGB`,
   `Adobe RGB (1998)` o `ProPhoto RGB`.
4. NexoRAW revela el RAW en ese espacio y embebe el ICC estándar.
5. La trazabilidad declara que no hay perfil de entrada medido y que el ICC
   incrustado es `generic_output_icc`.

Este flujo es reproducible y funcional, pero no sustituye la precisión de una
referencia colorimétrica medida.

## TIFF Maestro y Derivados

NexoRAW distingue:

- **TIFF maestro con carta**: RGB de cámara/sesión, perfil de ajuste calibrado,
  ICC de entrada de sesión, NexoRAW Proof y C2PA opcional.
- **TIFF derivado convertido**: salida transformada por CMM a un perfil de
  salida genérico o de dispositivo.
- **TIFF manual sin carta**: RAW revelado en espacio estándar real, ICC estándar
  incrustado y mochila de ajuste por archivo.

Las salidas existentes no se sobrescriben. NexoRAW crea versiones `_v002`,
`_v003`, etc.

## Mochilas y Auditoría

El sidecar de mochila registra:

- identidad y hash del RAW;
- receta de revelado aplicada;
- perfil de ajuste asignado;
- ICC asociado y hash cuando existe;
- ajustes de detalle y render;
- últimas salidas TIFF generadas.

La mochila no sustituye al RAW ni al manifiesto de lote. Su función es transportar
ajustes paramétricos por archivo de forma auditable y portable.
