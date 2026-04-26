# Guia de contribucion

Gracias por colaborar con NexoRAW. Este proyecto prioriza reproducibilidad,
auditoria y trazabilidad para fotografia cientifica, forense y de patrimonio.

## Tipos de contribucion bienvenidos

- Codigo (CLI, GUI, tooling y documentacion tecnica).
- Datasets de cartas de color con licencia clara y trazabilidad documental.
- Validaciones colorimetricas de campo (metricas DeltaE y contexto de captura).
- Traducciones y mejora de documentacion para usuarios no desarrolladores.
- Casos de uso documentados (cientifico, forense, patrimonio, docencia).
- Revision normativa y legal (metadatos, cadena de custodia, licencias).

## Flujo recomendado

1. Haz `fork` del repositorio.
2. Crea una rama descriptiva (`feat/...`, `fix/...`, `docs/...`).
3. Implementa el cambio con tests o evidencia reproducible.
4. Ejecuta las comprobaciones locales.
5. Abre un Pull Request hacia `main`.
6. Atiende revision tecnica y legal antes de merge.

## Entorno local y checks

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
bash scripts/run_checks.sh
```

Checks esperados para contribuciones de codigo:

- `pytest` en verde.
- Compatibilidad con `black`, `ruff` y `mypy` en los archivos cambiados.
- Coherencia con `pyproject.toml` (version de Python, extras y metadatos).
- Sin cambios silenciosos de salida colorimetrica ni de trazabilidad.

## Politica de commits

Usa prefijos semanticos:

- `feat:` nueva capacidad
- `fix:` correccion de bug
- `docs:` documentacion
- `test:` pruebas
- `refactor:` refactor sin cambio funcional

Ejemplo: `docs: add colorimetric validation issue template`.

## Como anadir una nueva carta o referencia

1. Documenta origen, licencia y version de la carta.
2. Anade referencia en `testdata/references/` o `src/iccraw/resources/references/`.
3. Incluye iluminante, observador, fuente y version en el JSON de referencia.
4. Adjunta ejemplo reproducible (deteccion + sample + QA).
5. Actualiza documentacion metodologica si cambia el flujo.

## Politica de datasets

- Licencia clara obligatoria (`CC0`, `CC-BY` o equivalente compatible).
- Incluir checksums SHA-256 de cada archivo.
- Declarar procedencia, autor, fecha y condiciones de captura.
- No subir material sensible ni datos con restriccion legal.

## Recordatorio AGPL

NexoRAW usa `AGPL-3.0-or-later`. Si ejecutas una version derivada como
servicio en red, debes publicar el codigo fuente correspondiente del derivado.

## Conducta comunitaria

Toda participacion se rige por [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
