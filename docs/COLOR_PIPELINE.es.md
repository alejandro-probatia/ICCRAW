# Pipeline de Color

_English version: [COLOR_PIPELINE.md](COLOR_PIPELINE.md)_

## Estado Operativo

ProbRAW 0.3.3 implementa el flujo ICC principal y la interfaz de trabajo por
sesión. La aplicación es apta para pruebas controladas y validación de release,
pero todavía no debe presentarse como sistema certificado de producción
científica/forense.

La metodología completa se describe en
[Metodología de revelado RAW y gestión ICC](METODOLOGIA_COLOR_RAW.es.md).

## Principio de Diseño

El pipeline separa:

1. revelado RAW reproducible;
2. perfil de ajuste paramétrico;
3. perfil ICC de entrada cuando hay carta;
4. perfil ICC estándar cuando no hay carta;
5. conversión CMM para derivados;
6. ICC de monitor solo para visualización;
7. auditoría mediante mochilas, manifiestos, Proof y C2PA opcional.

DCP no forma parte del pipeline activo de la serie 0.3.

## Modo Científico (`profiling_mode`)

Objetivo: neutralidad y reproducibilidad, no apariencia creativa.

Reglas:

1. sin sharpen creativo durante medición de carta;
2. sin denoise agresivo durante medición de carta;
3. sin curvas tonales artísticas;
4. balance de blancos fijo o explícito;
5. salida lineal para perfilado;
6. geometría de carta reutilizable entre pasadas.

## Fases

1. `raw-info`: lectura de metadatos técnicos.
2. `develop`: revelado base controlado con LibRaw/rawpy.
3. `detect-chart`: detección de carta, homografía y parches.
4. `sample-chart`: medición robusta por parche.
5. `build-develop-profile`: neutralidad, densidad y EV desde la fila neutra.
6. Receta calibrada: WB fijo, EV limitado por preservación de altas luces,
   salida lineal y sin procesos creativos.
7. Segunda medición de carta con la misma geometría y receta calibrada.
8. `build-profile`: ArgyllCMS (`colprof`) genera el ICC de entrada.
9. `validate-profile`: validación DeltaE 76/2000 del ICC real.
10. `batch-develop`: revelado de lote con perfil de ajuste e ICC asignado.

Las referencias de carta personalizadas se guardan en
`00_configuraciones/references/`. Cada ejecución avanzada de perfilado deja sus
artefactos en `00_configuraciones/profile_runs/`, y los ICC resultantes quedan
registrados como perfiles de sesión activables.

## Invariantes Críticas

1. La receta ejecutada debe coincidir con la receta declarada.
2. El TIFF de auditoría lineal debe escribirse antes de curvas tonales o
   conversiones de salida.
3. La gestión ICC separa asignación de perfil de entrada y conversión a perfil
   de salida.
4. La validación comprueba el ICC real generado, no solo matrices auxiliares.
5. El fallback de detección de carta no genera perfiles automáticamente sin modo
   explícito o revisión.
6. La geometría de carta de la pasada base puede reutilizarse en la pasada
   calibrada.
7. El ICC no debe compensar exposición/densidad básica si la carta permite
   construir antes una receta calibrada.
8. Con carta, el TIFF maestro conserva RGB lineal de cámara/sesión e incrusta el
   ICC de entrada.
9. Sin carta, el RAW se revela en sRGB/Adobe RGB/ProPhoto RGB real, se incrusta
   un ICC estándar y se declara `generic_output_icc`.
10. La visualización en pantalla usa una conversión exclusiva hacia el perfil ICC
    del monitor configurado.
11. El histograma y el overlay de clipping de la GUI se calculan sobre la señal
    colorimétrica de preview antes de aplicar el ICC del monitor.
12. El diagnóstico Gamut 3D es una comparación visual de perfiles; no modifica
    recetas, píxeles, perfiles activos ni manifiestos.

## Gestión de Color del Monitor

El perfil ICC de monitor no participa en el revelado, en el TIFF maestro ni en la
exportación. Solo corrige la representación visual de previews y miniaturas.

Detección:

- Windows: WCS/ICM.
- macOS: ColorSync.
- Linux/BSD: `colord`, `colormgr` o `_ICC_PROFILE`.

Si el perfil desaparece o no puede abrirse, ProbRAW registra el problema y usa
sRGB como fallback visual.

## Previsualización e Histograma

La GUI distingue entre señal de análisis y señal de pantalla:

1. El RAW se revela o previsualiza como RGB lineal normalizado.
2. Los ajustes paramétricos se aplican antes de la conversión de salida.
3. Si hay un ICC de entrada activo y válido, la preview usa ese ICC para generar
   una señal sRGB colorimétrica de revisión.
4. El histograma RGB colorimétrico y el overlay de clipping leen esa señal sRGB
   previa al monitor.
5. Solo después se aplica el ICC del monitor para enviar píxeles corregidos al
   widget de pantalla.

Esto evita que un perfil de monitor estrecho, defectuoso o diferente entre
equipos altere los datos de análisis. A la vez, exige que el usuario calibre el
monitor y configure correctamente su ICC en el sistema operativo para que la
apariencia visual de la preview sea fiable.

## Validez del Perfil

El perfil depende de:

- cámara;
- óptica;
- iluminante;
- receta;
- versión de software;
- configuración relevante del pipeline RAW.

Cambiar esos factores puede degradar o invalidar la validez colorimétrica.
