# Soporte AMaZE y demosaic packs GPL

## Decisión de licencia

ICCRAW se distribuye bajo `AGPL-3.0-or-later`. Esta licencia es compatible con
la condición GPL3+ exigida por el demosaic pack GPL3 de LibRaw, que incluye el
algoritmo AMaZE.

La integración de AMaZE debe mantener estas reglas:

1. conservar `LICENSE` y los avisos de copyright del proyecto,
2. conservar avisos/licencias de `rawpy-demosaic`, LibRaw y los demosaic packs,
3. distribuir el código fuente correspondiente junto al binario o mediante una
   URL pública equivalente,
4. documentar en cada release qué build de `rawpy`/LibRaw se ha usado,
5. no presentar AMaZE como disponible si `rawpy.flags["DEMOSAIC_PACK_GPL3"]`
   no es `True`.

## Backend recomendado

El camino preferente es usar `rawpy-demosaic`, un fork GPL3 de `rawpy` que
incluye los packs GPL2/GPL3 de LibRaw y exporta el mismo módulo Python
`rawpy`.

Instalación cuando exista wheel compatible con la plataforma:

```bash
pip uninstall -y rawpy
pip install rawpy-demosaic
python scripts/check_amaze_support.py
```

El comando debe informar:

```json
{
  "amaze_supported": true
}
```

## Windows

Si PyPI no ofrece wheel compatible con la versión de Python usada para el
instalador Windows, hay que construir una wheel propia de `rawpy-demosaic` o de
`rawpy` enlazada con LibRaw compilado con:

```text
LIBRAW_DEMOSAIC_PACK_GPL2
LIBRAW_DEMOSAIC_PACK_GPL3
```

La wheel resultante y el instalador de ICCRAW deben incluir avisos de licencia
GPL3/AGPL y una forma clara de obtener el código fuente correspondiente.

## Comprobación operativa

ICCRAW no infiere soporte AMaZE por la presencia del enum
`rawpy.DemosaicAlgorithm.AMAZE`; esa constante puede existir aunque el pack no
esté compilado. La comprobación válida es:

```python
import rawpy
assert rawpy.flags["DEMOSAIC_PACK_GPL3"] is True
```

Si la comprobación falla, la GUI degrada las recetas AMaZE a `dcb` para evitar
bloqueos durante la calibración interactiva. La CLI y el backend fallan con un
error explícito para preservar reproducibilidad.
