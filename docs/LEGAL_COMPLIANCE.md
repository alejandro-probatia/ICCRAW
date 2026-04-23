# Cumplimiento Legal y Licencias

## Alcance

Este documento define el marco de cumplimiento legal de ICCRAW para uso cientifico y forense.

## Licencia del proyecto

- ICCRAW se distribuye bajo `AGPL-3.0-or-later`.
- Toda redistribucion (codigo fuente o binarios) debe preservar:
  - aviso de copyright,
  - licencia AGPL,
  - acceso a la fuente correspondiente.
- Si el software se ofrece como servicio de red, debe mantenerse el acceso a la fuente correspondiente para usuarios remotos (AGPL).

## Herramientas externas del flujo

ICCRAW utiliza herramientas externas ejecutadas por subprocess:

- `dcraw` para revelado RAW.
- `ArgyllCMS` (`colprof`) para construccion de perfiles ICC.
- `exiftool` para metadatos.

Politica de integracion:

1. no se embeben ni redistribuyen binarios de terceros dentro del repositorio,
2. la instalacion se realiza desde paquetes oficiales del sistema o fuentes oficiales,
3. se registran versiones de dependencias en `run_context` para auditoria.

## Reglas de cumplimiento operativo

1. No eliminar ni modificar avisos de licencia de terceros.
2. Mantener este archivo y `LICENSE` sincronizados con la politica vigente.
3. Documentar en changelog cualquier cambio de licencia o dependencia critica.
4. Antes de publicar builds o contenedores, verificar que:
   - se adjunta licencia AGPL del proyecto,
   - se documentan dependencias externas,
   - existe mecanismo claro para obtener la fuente correspondiente.

## Gobernanza comunitaria

El mantenimiento del proyecto recae en la comunidad de la:

- **Asociacion Espanola de Imagen Cientifica y Forense**.

Se recomienda revisiones periodicas de cumplimiento legal y trazabilidad para entornos de peritaje y cadena de custodia digital.
