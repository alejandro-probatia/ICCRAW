# C2PA/CAI en NexoRAW

NexoRAW incorpora C2PA como una capa opcional sobre los TIFF finales. No
sustituye los mecanismos existentes: `batch_manifest.json`, hashes SHA-256,
auditoria lineal, perfiles ICC, reportes QA y sidecars siguen siendo parte del
flujo principal.

## Principios de implementacion

1. El RAW original no se modifica nunca.
2. NexoRAW no incrusta C2PA en RAW propietarios originales (`CR2`, `CR3`,
   `NEF`, `ARW`, `RAF`, `RW2`, `ORF`, `PEF`).
3. Para RAW propietarios, el vinculo probatorio se declara en el TIFF final con
   una asercion C2PA firmada: `org.probatia.iccraw.raw-link.v1`.
4. El identificador probatorio del RAW es el SHA-256 de sus bytes exactos.
   Nombre de archivo y ruta son solo metadatos auxiliares.
5. El SHA-256 del TIFF firmado se calcula despues de incrustar C2PA y se guarda
   en el manifiesto externo de NexoRAW. No se incluye dentro del manifiesto C2PA
   embebido para evitar una referencia circular.
6. Si el origen es DNG, NexoRAW intenta pasarlo al SDK C2PA como ingrediente
   `parentOf`, de modo que las credenciales C2PA preexistentes puedan
   conservarse si el SDK lo permite.
7. Los errores de firma, validacion o dependencia ausente no se silencian.
8. La clave privada no se registra en logs ni se almacena en manifiestos.

## Instalacion opcional

```bash
pip install -e .[c2pa]
```

La dependencia opcional es `c2pa-python>=0.32`.

## Firmar TIFFs finales

```bash
nexoraw batch-develop ./raws \
  --recipe recipe_calibrated.yml \
  --profile camera_profile.icc \
  --out ./tiffs \
  --c2pa-sign \
  --c2pa-cert chain.pem \
  --c2pa-key signing.key \
  --c2pa-alg ps256 \
  --c2pa-timestamp-url http://timestamp.digicert.com \
  --session-id sesion-2026-04-25
```

`--c2pa-cert` debe apuntar a la cadena publica PEM. `--c2pa-key` apunta a la
clave privada PEM. Si no se indica otra TSA, NexoRAW usa
`http://timestamp.digicert.com`, que es el valor usado en la documentacion de
referencia de `c2pa-python`. En entornos de produccion o laboratorio se
recomienda migrar la firma a KMS/HSM y definir una TSA propia o institucional,
aunque la CLI local es util para pruebas y despliegues controlados.

La firma se aplica al TIFF final ya renderizado. Despues de firmar, NexoRAW
calcula `output_sha256` y lo guarda en `batch_manifest.json`.

## Asercion RAW -> TIFF

La asercion `org.probatia.iccraw.raw-link.v1` registra:

- SHA-256, tamano, nombre base, extension y MIME estimado del RAW.
- Ruta del RAW como localizador auxiliar no probatorio.
- Metadatos de camara disponibles.
- Hash de receta NexoRAW.
- Hash del perfil ICC usado, si existe.
- Version de NexoRAW.
- Backend RAW, demosaicing, espacio de salida y modo de gestion de color.
- Hash de manifiesto tecnico externo si se proporciona y ya existe.
- Identificador de sesion opcional.
- Fecha/hora UTC de generacion.

## Verificacion

```bash
nexoraw verify-c2pa ./tiffs/captura.tiff \
  --raw ./raws/captura.NEF \
  --manifest ./tiffs/batch_manifest.json
```

La verificacion comprueba:

- que el TIFF contiene un manifiesto C2PA legible;
- que el RAW aportado coincide con el SHA-256 declarado;
- que el TIFF firmado coincide con `output_sha256` del manifiesto externo;
- que el SDK C2PA no devuelve errores de validacion tecnica.

Si falta `--manifest`, la verificacion C2PA y RAW se ejecuta igualmente, pero el
estado global no sera `ok` porque el manifiesto externo no pudo comprobarse.

## Notas operativas

- El campo `technical_manifest_sha256` solo se incluye si el archivo indicado
  por `--c2pa-technical-manifest` existe antes de firmar.
- `batch_manifest.json` se escribe al final del lote, por lo que no puede estar
  dentro del C2PA del mismo lote sin introducir circularidad.
- Certificados autofirmados pueden producir avisos de confianza aunque el
  manifiesto sea tecnicamente legible. Para uso probatorio real, definir una
  politica de certificados, custodia de clave y TSA verificable.
