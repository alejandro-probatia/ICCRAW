# Technical Decisions

## DEC-0001: Lenguaje principal del núcleo

- Estado: aceptada
- Fecha: 2026-04-23

Decisión:

- usar **Python** como lenguaje principal del núcleo y CLI para maximizar mantenibilidad comunitaria y velocidad de iteración científica.

Motivación:

1. ecosistema científico maduro,
2. menor barrera de contribución,
3. integración directa con tooling de visión/colorimetría.

## DEC-0002: Motor de perfil ICC

- Estado: aceptada
- Fecha: 2026-04-23

Decisión:

- motor de build de perfil ICC: **ArgyllCMS** (`colprof`) como único backend soportado.

Motivación:

1. ArgyllCMS es referencia técnica consolidada,
2. permite validación/contraste externo,
3. evita divergencias entre motores y mejora la reproducibilidad entre entornos.

## DEC-0003: Dependencias de imagen y RAW

- Estado: aceptada
- Fecha: 2026-04-23

Decisión:

- LibRaw mediante `rawpy` como motor único de revelado RAW,
- `opencv-python-headless` para detección geométrica,
- `tifffile` para export TIFF 16-bit,
- `colour-science` para métricas y conversiones colorimétricas.

## DEC-0004: Licencia inicial

- Estado: aceptada
- Fecha: 2026-04-23

Decisión:

- licencia del repositorio: `AGPL-3.0-or-later`.
- gobernanza y mantenimiento: comunidad de la **Asociacion Espanola de Imagen Cientifica y Forense**.

Compatibilidad (resumen):

1. LibRaw se integra mediante `rawpy`; ArgyllCMS se usa como herramienta externa para perfilado, validacion y conversion ICC,
2. OpenCV BSD: compatible,
3. `rawpy` pasa a ser dependencia crítica del pipeline RAW.

Cumplimiento (resumen):

1. toda distribucion del software debe incluir acceso a la fuente correspondiente bajo AGPL,
2. en despliegues de red/aplicacion remota, se mantiene obligacion AGPL de ofrecer fuente al usuario remoto,
3. se conserva trazabilidad de herramientas externas y sus versiones en el contexto de ejecucion.

## DEC-0005: Stack de interfaz grafica

- Estado: aceptada
- Fecha: 2026-04-23

Decision:

- usar **Qt for Python (PySide6)** para la GUI.

Motivacion:

1. mayor mantenibilidad a medio plazo para interfaz tecnica compleja,
2. buen rendimiento en visualizacion de imagen y herramientas de analisis,
3. licencia comunitaria LGPLv3/GPLv3 con buen encaje en ecosistema AGPL del proyecto.

## DEC-0006: Objetivo no comercial y licencia libre

- Estado: aceptada
- Fecha: 2026-04-23

Decision:

- mantener `AGPL-3.0-or-later` como licencia del repositorio,
- declarar explicitamente que el objetivo de gobernanza del proyecto es cientifico/comunitario sin finalidad comercial.

Motivacion:

1. la AGPL protege la reciprocidad de mejoras y uso en red,
2. añadir clausulas "solo no comercial" romperia compatibilidad open source y reutilizacion cientifica,
3. se prioriza seguridad juridica y compatibilidad con dependencias libres.

## DEC-0007: AMaZE y demosaic packs GPL3

- Estado: aceptada
- Fecha: 2026-04-25

Decision:

- mantener `AGPL-3.0-or-later` como licencia del repositorio,
- permitir AMaZE cuando el backend `rawpy` este respaldado por LibRaw con
  `DEMOSAIC_PACK_GPL3=True`,
- documentar `rawpy-demosaic` como backend recomendado para builds GPL3,
- no activar ni anunciar AMaZE si la build instalada no incluye el pack GPL3.

Motivacion:

1. el demosaic pack GPL3 de LibRaw exige GPL3+ para el producto resultante,
2. la AGPL del proyecto es compatible con GPL3+ y mantiene reciprocidad comunitaria,
3. la trazabilidad forense requiere registrar el backend exacto y sus flags,
4. la GUI debe evitar bloqueos interactivos cuando una receta antigua pide AMaZE
   en un entorno sin soporte GPL3.

## DEC-0008: Rendimiento de navegacion RAW y cache de previews

- Estado: aceptada
- Fecha: 2026-04-26

Decision:

- tratar miniaturas, preview de navegacion y revelado colorimetrico como tres
  niveles distintos de coste y fidelidad,
- generar miniaturas RAW desde el JPEG embebido siempre que exista,
- no ejecutar demosaic RAW masivo para poblar el navegador de miniaturas,
- guardar miniaturas y previews de navegacion en una cache persistente dentro
  de la sesion cuando el archivo pertenece al proyecto, con cache de usuario
  como respaldo cuando no hay sesion activa,
- usar claves relativas a la raiz de sesion para que una sesion exportada pueda
  reutilizar cache en otra ruta o equipo,
- limitar el trabajo inicial a lotes pequenos y precargar mas miniaturas solo
  cuando el usuario se acerque al final de la vista,
- usar preview RAW rapida por defecto para navegacion interactiva,
- reservar el revelado completo para la carga explicita o para flujos donde la
  fidelidad colorimetrica sea necesaria.

Motivacion:

1. RawTherapee crea las miniaturas iniciales a partir del JPEG embebido y las
   reutiliza desde cache en aperturas posteriores de una carpeta.
2. darktable separa cache primaria en memoria y backend secundario en disco, y
   permite extraer JPEG embebidos para acelerar el primer contacto con una
   coleccion.
3. En carpetas con muchos RAW, el coste de LibRaw/rawpy no debe bloquear la
   seleccion ni el desplazamiento del usuario.
4. La precision colorimetrica debe conservarse en el modo de revision/revelado,
   pero la navegacion necesita una representacion rapida y honesta sobre sus
   limites.

Referencias:

- RawTherapee File Browser: https://rawpedia.rawtherapee.com/File_Browser
- darktable thumbnails: https://docs.darktable.org/usermanual/4.6/en/lighttable/digital-asset-management/thumbnails/
- darktable lighttable preferences: https://docs.darktable.org/usermanual/4.8/en/preferences-settings/lighttable/

## DEC-0009: Perfiles de revelado de sesion

- Estado: aceptada
- Fecha: 2026-04-26

Decision:

- separar el perfil de revelado de la sesion del perfil ICC de camara,
- permitir perfiles de revelado generados desde carta de color y perfiles
  manuales guardados desde los controles configurados por el usuario,
- guardar varios perfiles de revelado dentro de `00_configuraciones/development_profiles/`,
- registrar en la cola que perfil de revelado se aplica a cada imagen,
- aplicar un perfil ICC solo cuando el perfil de revelado lo tenga asociado y
  ese ICC sea activable por las reglas QA actuales,
- conservar rutas relativas dentro de la sesion para que perfiles, recetas,
  manifiestos y cache puedan moverse con la carpeta completa.

Motivacion:

1. Programas de revelado RAW como RawTherapee separan parametros de revelado
   reutilizables de la imagen concreta.
2. ProbRAW debe funcionar tanto con flujo cientifico basado en carta como con
   un flujo operativo sin carta, donde el usuario fija manualmente criterios de
   revelado.
3. Una misma sesion puede contener condiciones de iluminacion, objetivos o
   criterios de salida distintos; por tanto no debe existir un unico perfil de
   revelado global obligatorio.

Referencias:

- RawTherapee Sidecar Files - Processing Profiles:
  https://rawpedia.rawtherapee.com/Sidecar_Files_-_Processing_Profiles

## DEC-0010: TIFF maestro con ICC de entrada de sesion

- Estado: aceptada
- Fecha: 2026-04-26

Decision:

- cuando una sesion genera un ICC propio desde carta, ProbRAW lo considera
  perfil de entrada de sesion;
- el TIFF maestro conserva RGB lineal de camara/sesion e incrusta ese ICC;
- no se convierte el TIFF maestro a sRGB, AdobeRGB o ProPhoto si existe ICC de
  sesion;
- los perfiles estandar de salida quedan reservados para sesiones sin carta o
  para derivados explicitamente convertidos mediante CMM;
- en sesiones sin carta, el perfil manual puede revelar a sRGB, Adobe RGB
  (1998) o ProPhoto RGB reales y usar su ICC estandar como
  `generic_output_icc` incrustado en el TIFF;
- la receta calibrada creada desde carta fuerza `tone_curve=linear`,
  `output_linear=true` y `output_space=scene_linear_camera_rgb` para mantener
  coherencia con el ICC generado.

Motivacion:

1. El ICC de sesion se calcula despues de revelar la carta, pero describe los
   RGB de camara/sesion producidos por esa receta controlada.
2. Convertir directamente a un espacio generico en el TIFF maestro mezcla
   asignacion de perfil de entrada y conversion de salida.
3. Mantener el maestro en el dominio de sesion evita dobles conversiones y
   conserva un artefacto mas fiel para auditoria y derivados posteriores.

Referencias:

- RawTherapee Color Management:
  https://rawpedia.rawtherapee.com/Color_Management
- RawTherapee ICC Profile Creator:
  https://rawpedia.rawtherapee.com/ICC_Profile_Creator
- Metodologia interna:
  [Metodología de revelado RAW y gestión ICC](METODOLOGIA_COLOR_RAW.es.md)

## DEC-0011: Sidecars mochila por RAW

- Estado: aceptada
- Fecha: 2026-04-26

Decision:

- guardar junto a cada RAW un sidecar `nombre.RAW.probraw.json`;
- registrar receta, perfil de revelado asignado, ICC de sesion, ajustes de
  detalle/render, identidad del RAW y salidas TIFF recientes;
- usar JSON por coherencia con los sidecars y manifiestos auditables existentes
  en ProbRAW;
- cargar automaticamente la mochila al seleccionar o reinsertar un RAW en la
  cola cuando el perfil de revelado existe en la sesion.

Motivacion:

1. Los programas de revelado RAW consolidados tratan el revelado como edicion
   parametrica y guardan ajustes en sidecars.
2. Una sesion puede moverse entre equipos o usuarios sin perder los parametros
   por imagen.
3. El sidecar por RAW complementa, no sustituye, `session.json`, ProbRAW Proof ni
   `batch_manifest.json`.

Referencias:

- RawTherapee Sidecar Files - Processing Profiles:
  https://rawpedia.rawtherapee.com/Sidecar_Files_-_Processing_Profiles

## DEC-0012: Perfil ICC de monitor desde el sistema

- Estado: aceptada
- Fecha: 2026-04-26

Decision:

- activar por defecto la gestion ICC de monitor en la GUI;
- detectar automaticamente el perfil configurado en el sistema operativo;
- permitir override manual por usuario;
- aplicar el perfil de monitor solo a previews y miniaturas, nunca al TIFF
  maestro, perfiles de sesion ni exportaciones;
- usar sRGB solo como fallback cuando el sistema no expone ningun perfil o el
  perfil detectado no puede abrirse.

Motivacion:

1. No todos los monitores son sRGB; asumir sRGB puede dar saturacion y tono
   incorrectos en pantallas wide-gamut o calibradas.
2. Los sistemas operativos ya mantienen el perfil ICC activo del monitor, por
   lo que ProbRAW debe consumir esa configuracion antes que pedir al usuario una
   ruta manual.
3. El perfil de monitor es una condicion de visualizacion, no un parametro de
   revelado ni una propiedad del archivo exportado.

Referencias:

- Microsoft GetICMProfileW:
  https://learn.microsoft.com/en-us/windows/win32/api/wingdi/nf-wingdi-geticmprofilew
- Apple CGDisplayCopyColorSpace:
  https://developer.apple.com/documentation/coregraphics/cgdisplaycopycolorspace%28_%3A%29
- Apple CGColorSpace:
  https://developer.apple.com/documentation/CoreGraphics/CGColorSpace
- freedesktop.org colord ColorManager:
  https://www.freedesktop.org/software/colord/gtk-doc/ColorManager.html
- freedesktop.org colord Device:
  https://www.freedesktop.org/software/colord/gtk-doc/Device.html
