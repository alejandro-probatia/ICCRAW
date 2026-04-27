# Reproducibilidad

NexoRAW separa tres niveles:

- RAW original: nunca se modifica.
- Escena lineal: salida numerica despues de LibRaw/demosaico/WB/negro.
- Render final: exposicion, curva, gestion de color, firma y pruebas.

## Tests golden

Los casos canonicos estan en `testdata/regression/MANIFEST.json`.
Cada caso declara:

- entrada,
- receta,
- SHA-256 del TIFF final,
- SHA-256 del TIFF lineal de auditoria.

El test `tests/regression/test_canonical_hashes.py` revela cada caso en un
directorio temporal y compara hashes byte a byte.

## Regenerar hashes

Solo debe hacerse cuando un cambio de algoritmo o dependencia modifica la
salida de forma intencional:

```powershell
python scripts/regenerate_golden_hashes.py --confirm --note "descripcion breve"
```

El script desactiva `use_cache` antes de revelar, actualiza el manifest y anade
una entrada en `tests/regression/golden/REGENERATION_LOG.md`.

## Cache y reproducibilidad

La cache de demosaico guarda arrays `.npy` de escena lineal para rendimiento.
Es opt-in y su clave contiene el SHA-256 completo del RAW y los parametros que
afectan a LibRaw. Los tests golden no usan cache para evitar falsos positivos
de infraestructura.
