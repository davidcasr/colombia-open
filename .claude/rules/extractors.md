---
description: Contrato para cualquier archivo en src/extractors/
appliesTo: "src/extractors/**"
---

# Contrato de extractores

Todo extractor implementa `BaseExtractor` (`src/extractors/base.py`) y
sigue este contrato. La skill `.claude/skills/new-source/SKILL.md` genera
un esqueleto que ya lo cumple — si estás escribiendo uno a mano, verifica
cada punto.

## 1. Try en vivo, fallback solo si todo falla — y solo para fallas esperadas

```python
EXPECTED_FETCH_FAILURES: tuple[type[Exception], ...] = (RequestException, KeyError, ValueError, TypeError)

def fetch(self, **kwargs) -> ExtractionResult:
    try:
        ...  # fuente en vivo
        return ExtractionResult(..., source_mode="live", ...)
    except EXPECTED_FETCH_FAILURES as exc:
        ...  # fallback embebido mínimo
        return ExtractionResult(..., source_mode="fallback", ...)
```

- **Nunca uses `except Exception` desnudo aquí.** Captura solo las fallas
  que de verdad pueden venir de la fuente: errores de red/HTTP
  (`requests.RequestException`), forma de JSON inesperada (`KeyError`,
  `TypeError`), o un valor que no parsea (`ValueError` — esto incluye
  `JSONDecodeError`, que hereda de `ValueError`). Un bug de programación
  real (`AttributeError` por un typo, `NameError`, etc.) **debe reventar**,
  no disfrazarse de "fuente caída" — un `except Exception` amplio esconde
  justo los errores que más urgen arreglar.
- `fetch()` **nunca lanza** ante una falla esperada de la lista de arriba
  si hay un fallback posible — siempre devuelve un `ExtractionResult`, con
  `source_mode` reflejando la verdad.
- El fallback es una muestra mínima embebida en el propio archivo
  (5-15 filas representativas), solo para desarrollo offline. **Nunca se
  presenta como dato real** y **nunca se publica**:
  `scripts/verify_pipeline.py --require-live` lo rechaza.
- Si de verdad no hay fallback razonable (la fuente es indispensable y no
  hay snapshot previo), es correcto dejar que la excepción se propague —
  mejor un build que falla fuerte que un silencio.

## 2. Snapshot crudo, write-once

Cada fetch en vivo exitoso escribe el payload crudo (antes de normalizar)
a `data/raw/{dataset}_{timestamp}.json` vía
`write_raw_snapshot_atomic()`. Nunca se edita ese archivo después de
escrito — es el rastro de auditoría de qué devolvió la fuente exactamente.
Guarda también su SHA256 (`compute_sha256()`) en el `ExtractionResult`.

## 3. Normalización: códigos administrativos como string de ancho fijo

```python
"cod_dpto": str(row["cod_dpto"]).zfill(2),   # nunca int
"cod_mpio": str(row["cod_mpio"]).zfill(5),   # nunca int
```

Cualquier columna que sea un código administrativo (departamento,
municipio, y los que vengan en fuentes futuras) se normaliza a string de
ancho fijo en el extractor, no después. Pandas/Polars/Excel truncan ceros
iniciales de un int silenciosamente — ese bug no se detecta en los tests a
menos que verifiques explícitamente el ancho (ver
`.claude/rules/validation.md`).

## 4. Staging: CSV + metadata.json, siempre juntos

`write_staging()` escribe ambos atómicamente
(`write_staging_csv_atomic()`). El metadata.json sigue el esquema de
`ExtractionResult.to_staging_metadata()`:

```json
{
  "dataset": "...",
  "source_name": "...",
  "source_url": "...",
  "source_mode": "live" | "fallback",
  "source_detail": "...",
  "refreshed_at_utc": "...",
  "record_count": 0,
  "fields": ["..."],
  "notes": ["..."],
  "raw_snapshot_path": "...",
  "snapshot_hash": "...",
  "reuse_policy": { "status": "...", "license": "...", ... }
}
```

Nunca se escribe el CSV sin su metadata.json hermano — un builder que lo
encuentre sin metadata debe fallar fuerte, no asumir valores.

## 5. Red: reintentos solo en errores de red, nunca en 4xx/5xx

Usa `src/extractors/http_utils.py::get_json`/`get_bytes` — ya tienen
backoff exponencial para `ConnectionError`/`Timeout` (vía `tenacity`).
**No reintentes en respuestas 4xx/5xx** — eso es una respuesta real del
servidor (dato cambió de formato, endpoint movido, bloqueo anti-bot), no
un problema de red transitorio; cae a fallback o deja que falle.

## 6. Siempre se invoca como módulo, nunca como script suelto

```python
from src.extractors.base import BaseExtractor, ExtractionResult, ...
from src.extractors.http_utils import get_json
```

Importaciones absolutas normales, sin manipular `sys.path` ni try/except
de importación. Esto funciona porque la convención del proyecto es
**invocar siempre con `-m` desde la raíz del repo**:
`python -m src.extractors.{name}_extractor` (así lo hace el Makefile y la
CI) — nunca `python src/extractors/{name}_extractor.py` directo, que
fallaría al importar porque `src` no quedaría en el path.

No reintroduzcas el truco de `sys.path.insert()` / `try: from src.x import
... except ModuleNotFoundError: from x import ...` — es deuda técnica que
otros proyectos cargan por compatibilidad histórica con código viejo, que
este proyecto no tiene. Si un extractor nuevo "necesita" ese truco para
funcionar, el problema real es que algo lo está invocando sin `-m`.

## 7. Si la fuente requiere scraping real (no API/descarga directa)

Eso va bajo el extra `scraping` (`curl_cffi`, `beautifulsoup4`,
`defusedxml`), no `pipeline`. Antes de llegar ahí: ¿de verdad no hay una
API JSON o un endpoint de descarga directa? Prefiere siempre eso —
scraping HTML es la fuente más frágil y cara de mantener (ver `docs/roadmap/roadmap.md`,
fuentes 🟠/🔴).
