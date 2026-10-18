---
description: Usar al agregar una fuente de datos nueva a colombia-open (extractor + builder + validación + registro + tests + docs). Recibe el nombre de la fuente y su URL/endpoint.
---

# Agregar una fuente nueva a colombia-open

Antes de escribir código: **verifica el endpoint/URL actual de la fuente**
(curl/fetch real, no solo lo que dice `docs/roadmap/roadmap.md` — esa tabla
puede estar desactualizada). Si el acceso real no coincide con lo que
`docs/roadmap/roadmap.md` describe, corrígelo ahí antes de seguir.

Usa `src/extractors/divipola_extractor.py` + `src/validation/_territorio.py`
+ `data/registry/datasets.json` (entradas `departamentos`/`municipios`)
como plantilla de referencia en cada paso — son el ejemplo end-to-end ya
funcionando de este mismo contrato.

**Regla de alcance**: esta skill implementa UNA fuente, de punta a punta.
No empieces una segunda mientras esta no pase `make check` completo.

## Checklist

### 1. Extractor — `src/extractors/{name}_extractor.py`

- Importaciones absolutas normales desde `src.extractors.base`/
  `src.extractors.http_utils` — sin manipular `sys.path` (ver
  `.claude/rules/extractors.md` §6). El extractor se invoca siempre como
  módulo: `python -m src.extractors.{name}_extractor`.
- Clase `{Name}Extractor(BaseExtractor)` con `dataset_name`, `fetch()`,
  `write_staging()`.
- `fetch()`: try en vivo → except → fallback embebido mínimo (5-15 filas).
  Siempre devuelve `ExtractionResult` con `source_mode` correcto. El
  `except` captura una tupla explícita de fallas esperadas de la fuente
  (`RequestException`, `KeyError`, `ValueError`, `TypeError` — ajusta
  según lo que de verdad pueda fallar en esta fuente), **nunca**
  `except Exception` desnudo (ver `.claude/rules/extractors.md` §1).
- Define `REUSE_POLICY: ReusePolicy` con la licencia real de la fuente
  (revisa el portal — no asumas CC BY por defecto). Si es ambigua,
  **pregunta antes de asumir** y marca `status="restricted"` mientras
  tanto (ver `docs/licenses/data_licenses.md`).
- Normaliza cualquier código administrativo a string de ancho fijo
  (`.zfill(n)`) — nunca lo dejes como int.
- Si la fuente requiere scraping real (no hay API/descarga directa):
  el extractor va bajo el extra `scraping`, no `pipeline` — importa
  `curl_cffi`/`beautifulsoup4` solo ahí, no en `pyproject.toml[pipeline]`.
- `if __name__ == "__main__":` al final, igual que el ejemplo — así
  `make extract` (que invoca `python -m src.extractors.{name}_extractor`)
  puede correrlo.

### 2. Builder — entrada en `src/builders/datasets.py` (o módulo nuevo si el dominio no existe)

- Si la fuente produce un dataset normalizado 1:1 desde staging, no
  necesitas una función `derive_*` — el builder solo lee staging y
  escribe parquet/json directo.
- Si deriva más de un dataset lógico de un mismo staging (como
  `divipola` → `departamentos` + `municipios`), escribe una función
  `derive_{dataset}(staging_df) -> pl.DataFrame` por cada uno.
- Agrega una columna `{campo}_clean` (vía `builders/datasets.py::clean_name`)
  a cualquier columna de nombre que vaya a usarse para búsqueda/join por
  texto.

### 3. Validador — `src/validation/_{dominio}.py`

- Función `validate_{dataset}(df, metadata=None, **kwargs) -> ValidationResult`
  que sigue el contrato de `.claude/rules/validation.md`: nunca lanza,
  siempre devuelve un `ValidationResult` (`src/validation/result.py`), no
  un dict plano.
- Mínimo: columnas requeridas presentes, clave primaria única, ancho fijo
  de cualquier código administrativo, conteo mínimo si `source_mode="live"`.
- Si el dataset referencia códigos de otro dataset ya existente (ej. todo
  dataset territorial futuro probablemente referencia `cod_dpto` o
  `cod_mpio`), valida integridad referencial con
  `_helpers.unknown_codes_count()`.
- **Registra la función**: impórtala y agrégala al dict `VALIDATORS` en
  `src/validation/__init__.py`. Sin esto, `make doctor` falla.

### 4. Registro — entrada en `data/registry/datasets.json`

```json
"{dataset}": {
  "description": "...",
  "extractor": "src/extractors/{name}_extractor.py",
  "source_name": "...",
  "join_keys": ["..."],
  "expected_record_count": 0,
  "outputs": {
    "parquet": "data/normalized/{dataset}.parquet",
    "json": "data/normalized/{dataset}.json"
  },
  "usage_examples": {
    "python": "from colombia_open import ColombiaOpen\n\nhub = ColombiaOpen()\ndf = hub.load_polars('{dataset}')",
    "cli": "colombia-open path {dataset} --output parquet"
  },
  "documentation": "docs/datasets/{dataset}.md"
}
```

### 5. Orquestador — `src/build_pipeline.py`

Agrega el bloque de extracción + derive + validate + write + catalog para
la fuente nueva, siguiendo el patrón ya escrito para `divipola`. Si el
dominio es nuevo, importa el validador nuevo arriba junto a los demás.

### 6. Tests — `tests/{extractors,builders,validation}/test_{name}.py`

Como mínimo (ver los tests de `divipola` como plantilla):
- Extractor: normalización del fallback produce códigos de ancho correcto;
  `run(dry_run=True)` no escribe nada a disco.
- Builder (si aplica `derive_*`): dedup correcto, columna `_clean` presente.
- Validador: caso feliz + un caso por regla de error + dataframe vacío +
  warning en `source_mode="fallback"`.
- Si agregaste algo a `colombia_open/` (ej. un método nuevo en `core.py`
  específico del dominio): test en `tests/test_core_api.py`.

### 7. Documentación y registro final

1. `docs/datasets/{dataset}.md` — descripción, fuente, licencia, esquema
   completo (tabla columna/tipo/descripción), ejemplos de uso, limitaciones
   conocidas. Usa `docs/datasets/municipios.md` como plantilla.
2. Agrega el/los dataset(s) nuevo(s) al enum
   `src/colombia_open/datasets.py::Dataset`.
3. Marca la fila correspondiente en `docs/roadmap/roadmap.md` como implementada, con
   link al extractor (mismo formato que la fila de geografía).
4. Corre `make check` completo — build, verify, test, lint, format-check,
   typecheck, sec. Todo verde antes de considerar la fuente terminada.

## No hagas esto

- No implementes una segunda fuente en la misma sesión "ya que estás
  aquí" — una fuente por fin de semana (ver `CLAUDE.md`).
- No le pongas scraping HTML a una fuente que tiene API JSON o descarga
  directa — verifica eso primero.
- No marques una fuente como lista sin correr `make check` completo.
- No asumas la licencia de una fuente — verifícala en el portal real y,
  si es ambigua, pregunta antes de publicar (ver `docs/licenses/data_licenses.md`).
