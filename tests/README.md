# Tests

Este directorio se reserva para suites de integración de alto nivel (cross-crate y datasets reales).

Actualmente:

- tests unitarios por crate en `core/*/src/lib.rs`.
- tests de CLI en `cli/tests/smoke.rs`.

Próximas suites aquí:

1. regresión colorimétrica con dataset real de cartas,
2. reproducibilidad inter-plataforma,
3. comparación contra perfiles externos de referencia.
