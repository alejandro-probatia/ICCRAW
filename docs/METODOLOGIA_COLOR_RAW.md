# Metodologia de revelado RAW y gestion ICC

Este documento fija el criterio metodologico de NexoRAW para separar revelado
parametrico, perfil de entrada de sesion y perfiles de salida. La decision se
inspira en flujos consolidados de reveladores RAW como RawTherapee, adaptados al
objetivo tecnico, cientifico y forense del proyecto.

## Referencias consultadas

- RawTherapee, `Sidecar Files - Processing Profiles`:
  https://rawpedia.rawtherapee.com/Sidecar_Files_-_Processing_Profiles
- RawTherapee, `Color Management`:
  https://rawpedia.rawtherapee.com/Color_Management
- RawTherapee, `How to create DCP color profiles`:
  https://rawpedia.rawtherapee.com/How_to_create_DCP_color_profiles
- RawTherapee, `ICC Profile Creator`:
  https://rawpedia.rawtherapee.com/ICC_Profile_Creator

## Criterio conceptual

Un RAW no es una imagen RGB final. Es una captura de datos del sensor que debe
ser interpretada mediante una receta de revelado: demosaicing, balance de
blancos, nivel negro, compensacion de exposicion, curva tonal, espacio de trabajo
y otros parametros. En RawTherapee esta receta persistente se denomina
`processing profile` y se guarda como sidecar asociado a la imagen.

El perfil ICC o DCP de camara no se calcula sobre el RAW desnudo. Se calcula
despues de revelar una captura de carta con una receta controlada, porque las
mediciones se hacen sobre valores RGB ya producidos por el revelador. Sin
embargo, una vez generado, ese perfil describe como interpretar los RGB de
camara/sesion producidos por esa misma receta, camara e iluminante. Por tanto,
en NexoRAW se trata como **perfil de entrada de sesion**, no como perfil generico
de salida.

RawTherapee separa tres clases: perfil de entrada, perfil de pantalla y perfil
de salida. El perfil de salida se usa cuando se guarda una imagen transformada a
un espacio destino como sRGB, un espacio amplio o un perfil de impresora. Ese
paso no debe confundirse con asignar el perfil propio de la sesion al RGB que
todavia esta en dominio de camara/sesion.

En NexoRAW 0.2, el ajuste parametrico se considera una propiedad asignada a un
RAW concreto mediante su mochila `RAW.nexoraw.json`. Una sesion puede tener
varios perfiles de ajuste: algunos avanzados, nacidos de carta de color, y otros
basicos, nacidos de ajustes manuales. El usuario puede copiar el perfil desde
una miniatura y pegarlo en otras imagenes tomadas bajo condiciones comparables.

Esto evita un problema metodologico: una sesion no siempre es homogenea. Puede
contener varias iluminaciones, objetivos, exposiciones o criterios de salida. El
perfil global unico queda sustituido por perfiles por imagen, reutilizables y
trazables.

## Flujo con carta de color

Cuando existe una captura valida de carta:

1. Revelar la carta con una receta cientifica base.
2. Detectar y medir parches de la carta.
3. Generar un perfil de revelado de sesion: balance de blancos, densidad y
   parametros reproducibles derivados de la carta.
4. Re-revelar/medir la carta con esa receta calibrada.
5. Generar el ICC de entrada de sesion con ArgyllCMS a partir de esos RGB
   calibrados y las referencias colorimetricas.
6. Guardar por separado:
   - perfil de revelado NexoRAW,
   - receta calibrada,
   - ICC de entrada de sesion,
   - reportes QA y validacion.
7. Revelar los RAW de la sesion con la receta calibrada.
8. Crear el TIFF maestro manteniendo RGB lineal de camara/sesion e incrustando
   el ICC propio de la sesion.

En la GUI, el RAW usado como carta queda marcado en azul porque contiene un
perfil avanzado. Ese perfil puede copiarse y pegarse en otras miniaturas. La
validez de esa copia depende de que camara, optica, iluminante, exposicion base
y criterios RAW sean comparables.

El TIFF maestro no se convierte a sRGB, AdobeRGB o ProPhoto cuando hay ICC de
sesion. Hacerlo en esta fase mezclaria dos operaciones distintas y podria
introducir dobles conversiones o una perdida innecesaria de informacion.

## Flujo sin carta de color

Cuando no existe carta:

1. No se inventa un ICC de sesion.
2. Se permite guardar un perfil de revelado manual con los parametros definidos
   por el usuario.
3. El usuario puede elegir un ICC generico de salida: sRGB, Adobe RGB (1998) o
   ProPhoto RGB. NexoRAW genera ese perfil dentro de la sesion y lo incrusta en
   el TIFF final.
4. La trazabilidad debe declarar que no hay perfil de entrada medido y que el
   ICC incrustado es un `generic_output_icc`.

En la GUI, el RAW queda marcado en verde porque contiene un perfil basico. Ese
perfil tambien puede copiarse y pegarse en otras imagenes. Es un flujo operativo
y reproducible, pero no tiene la misma fuerza colorimetrica que un perfil
avanzado con carta.

## TIFF maestro y derivados

NexoRAW distingue dos tipos de salida:

- **TIFF maestro de sesion**: RGB de camara/sesion, receta calibrada, ICC de
  entrada de sesion incrustado, NexoRAW Proof y C2PA opcional.
- **TIFF derivado de intercambio**: convertido mediante CMM desde el ICC de
  sesion hacia un perfil de salida generico o de dispositivo, con ese perfil de
  salida incrustado.
- **TIFF manual sin carta**: receta paramétrica definida por el usuario,
  mochila NexoRAW por archivo, ICC generico de salida incrustado. Este flujo es
  funcional, pero no sustituye la precision de una carta colorimetrica.

La version actual implementa el TIFF maestro de sesion como salida preferente
cuando hay carta. Para sesiones sin carta implementa la asignacion de sRGB,
Adobe RGB (1998) o ProPhoto RGB como perfiles genericos de salida; cuando existe
ICC de entrada de sesion, las salidas genericas se tratan como derivados
convertidos por CMM.

## Sidecars mochila

Cada RAW puede llevar un sidecar de NexoRAW junto al archivo original:

```text
captura.NEF
captura.NEF.nexoraw.json
```

El sidecar registra:

- identidad y hash del RAW,
- receta de revelado aplicada,
- perfil de revelado de sesion asignado,
- ICC de sesion asociado y hash,
- ajustes de detalle y render,
- ultimas salidas TIFF generadas.

Este archivo no sustituye al RAW ni al manifiesto de lote. Su funcion es
transportar los parametros parametricos de revelado por archivo, de forma
equivalente al papel practico de los PP3 de RawTherapee, pero usando un esquema
JSON propio y auditable de NexoRAW.

La mochila es tambien el contrato que permite mover una sesion entre equipos. Si
la estructura relativa se mantiene, otra persona puede abrir la carpeta,
recuperar miniaturas/cache y saber que ajustes estaban asignados a cada RAW sin
depender del estado interno de la aplicacion.
