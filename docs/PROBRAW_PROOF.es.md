# ProbRAW Proof

ProbRAW Proof es la capa de firma autonoma de ProbRAW. Su objetivo es evitar
que la validez probatoria dependa exclusivamente de C2PA o de una lista central
de autoridades admitidas.

No implementa criptografia propia. Usa criptografia estandar:

- SHA-256 para identificar bytes exactos.
- Ed25519 para firma digital asimetrica.
- JSON canonico con claves ordenadas para calcular y verificar la firma.

## Modelo de confianza

ProbRAW Proof no decide quien es una autoridad. Firma el manifiesto con la clave
privada del perito, laboratorio o institucion. La confianza se establece
publicando y custodiando la clave publica:

- en un informe pericial;
- en una web institucional;
- en un repositorio publico;
- mediante acta o registro externo;
- mediante firma cruzada por otra entidad.

Un tercero puede verificar que:

1. el sidecar fue firmado por la clave privada correspondiente;
2. la clave publica coincide con la huella declarada;
3. el RAW aportado coincide con el SHA-256 firmado;
4. el TIFF final coincide con el SHA-256 firmado;
5. la receta, perfil ICC y ajustes declarados son los contenidos en el proof.

## Relacion con C2PA

C2PA sigue siendo compatible, pero no es obligatorio para que un TIFF de ProbRAW
tenga trazabilidad criptografica. La politica queda asi:

- ProbRAW Proof: capa autonoma obligatoria y generada automaticamente para TIFF final.
- C2PA: capa interoperable; usa certificado externo si existe o identidad local
  autoemitida si no existe.
- `batch_manifest.json`: manifiesto externo de lote, se mantiene.
- Auditoria lineal, hashes y perfiles ICC: se mantienen.

Si C2PA puede incrustarse, ProbRAW lo escribe primero. Despues calcula el hash
del TIFF ya firmado con C2PA y crea el sidecar ProbRAW Proof. Asi se evita
firmar bytes que luego cambien. Si el lector C2PA informa
`signingCredential.untrusted` con la identidad local, se interpreta como
advertencia de confianza externa, no como perdida del vinculo RAW-TIFF.

## Identidad local

En uso normal no hace falta ejecutar ningun comando: si no hay variables de
entorno ni rutas configuradas, ProbRAW crea automaticamente la identidad Proof en
`~/.probraw/proof`.

Para generar o reemplazar manualmente una identidad:

```bash
probraw proof-keygen \
  --private-key ~/.probraw/proof/probraw-proof-private.pem \
  --public-key ~/.probraw/proof/probraw-proof-public.pem
```

Para cifrar la clave privada:

```bash
probraw proof-keygen \
  --private-key ~/.probraw/proof/probraw-proof-private.pem \
  --public-key ~/.probraw/proof/probraw-proof-public.pem \
  --passphrase "frase larga y privada"
```

La clave privada no debe subirse al repositorio, enviarse por correo ni quedar
sin control de acceso. La clave publica si puede distribuirse.

## Exportar TIFF con ProbRAW Proof

```bash
probraw batch-develop ./raws \
  --recipe recipe_calibrated.yml \
  --profile camera_profile.icc \
  --out ./tiffs
```

Tambien puede configurarse por entorno:

```bash
export PROBRAW_PROOF_KEY=~/.probraw/proof/probraw-proof-private.pem
export PROBRAW_PROOF_PUBLIC_KEY=~/.probraw/proof/probraw-proof-public.pem
export PROBRAW_PROOF_SIGNER_NAME="Laboratorio / Perito"
```

Cada TIFF final genera un sidecar:

```text
captura.tiff
captura.tiff.probraw.proof.json
```

## Verificar

```bash
probraw verify-proof captura.tiff.probraw.proof.json \
  --tiff captura.tiff \
  --raw captura.NEF \
  --public-key probraw-proof-public.pem
```

La verificacion devuelve `status=ok` solo si firma, clave publica, RAW, TIFF y
hash de ajustes coinciden. El hash de ajustes no es el unico registro: se usa
como control de integridad sobre un bloque `render_settings` completo que queda
firmado dentro del proof.

## Contenido firmado

El sidecar incluye y firma:

- SHA-256 y tamano del RAW original.
- SHA-256 y tamano del TIFF final.
- nombre base, extension, MIME y ruta auxiliar no probatoria;
- metadatos de camara disponibles;
- version de ProbRAW;
- backend RAW y algoritmo de demosaicing;
- receta completa y hash de receta;
- perfil ICC usado y hash;
- modo de gestion de color;
- bloque `render_settings` completo: receta RAW, ajustes de detalle/nitidez,
  ajustes de contraste/render, gestion de color, flujo RAW/color y criterios de
  reproducibilidad;
- resumen de ajustes para lectura rapida, manteniendo el bloque completo para
  reproduccion experimental;
- estado C2PA si se incrusto;
- clave publica y huella SHA-256 del firmante.

La ruta del RAW o TIFF nunca es el identificador probatorio principal. El
identificador probatorio son los hashes de los bytes exactos.
