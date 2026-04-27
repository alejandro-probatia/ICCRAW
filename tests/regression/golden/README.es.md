# Golden hashes

Estos casos fijan hashes SHA-256 del TIFF canonico y del TIFF lineal de
auditoria para detectar cambios accidentales en la salida reproducible.

Los inputs actuales usan TIFFs sinteticos versionados en `testdata/` para que
el test sea ligero y no dependa de RAW propietarios pesados. Las recetas tienen
`use_cache: false` para validar siempre el path de calculo, no un artefacto
cacheado.

Para regenerar hashes tras un cambio intencional de motor numerico:

```powershell
python scripts/regenerate_golden_hashes.py --confirm
```
