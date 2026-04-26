# Politica de seguridad

## Versiones soportadas

| Version | Estado | Soporte de seguridad |
| --- | --- | --- |
| 0.2.x (beta) | Activa | Si |
| 0.1.x (beta historica) | Mantenimiento minimo | No |
| < 0.1.0-beta.5 | Legacy | No |

## Como reportar una vulnerabilidad

No abras issues publicos para vulnerabilidades.

Reporta de forma privada a: `[contacto-pendiente@dominio]`.

Incluye, si es posible:

- Version de NexoRAW y sistema operativo.
- Vector de ataque y pasos reproducibles.
- Impacto potencial (confidencialidad, integridad, disponibilidad).
- Prueba de concepto minima.

## Tiempos de respuesta esperados

- Acuse de recibo: hasta 72 horas.
- Evaluacion inicial: hasta 7 dias naturales.
- Propuesta de mitigacion o plan de parche: hasta 21 dias naturales.

Si el caso requiere coordinacion con terceros, se informara el estado por el
mismo canal privado.

## Alcance (in scope)

- Vulnerabilidades en parsing de RAW o de imagenes usadas en el pipeline.
- Riesgos en ejecucion de subprocesos externos (`ExifTool`, `ArgyllCMS`).
- Manipulacion maliciosa de sidecars, manifests o proof (`.nexoraw.proof.json`,
  `batch_manifest.json`, C2PA) que comprometa trazabilidad.

## Fuera de alcance (out of scope)

- Errores cosmeticos de GUI sin impacto de seguridad.
- Fallos de dependencias upstream sin exploit propio en NexoRAW.
  En esos casos, reporta tambien al tracker del proveedor afectado.
- Solicitudes de hardening generico sin escenario reproducible.

## Divulgacion responsable

No publiques detalles tecnicos de una vulnerabilidad antes de que exista parche
o mitigacion documentada para usuarios.
