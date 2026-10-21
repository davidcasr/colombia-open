"""Extractor de la Tasa de Cambio Representativa del Mercado (TRM), fuente
Superintendencia Financiera de Colombia.

Fuente primaria: API Socrata de datos.gov.co, dataset "Tasa de Cambio
Representativa del Mercado - TRM" (id `32sa-8pi3`), publicado por la
Superintendencia Financiera de Colombia (SUPERFINANCIERA) — calculada con
la metodología del Banco de la República, pero el ente que la certifica y
publica es la Superfinanciera, no el Banco directamente (corrección sobre
`docs/roadmap/roadmap.md`, que la mapeaba bajo "Banco de la República").
Licencia CC BY-SA 4.0. Confirmado en vivo el 2026-10-22: 8372 filas,
1991-12-02 a la fecha, actualizado a diario.

https://www.datos.gov.co/resource/32sa-8pi3.json

Es la fuente más simple del catálogo: sin paginación (8372 filas caben en
un solo request), sin dimensión territorial (es una serie nacional), sin
necesidad de agregación.

Nota de granularidad: la fuente no es "un valor por día calendario" — es
"un valor por publicación", con un rango de vigencia
(`vigenciadesde`/`vigenciahasta`) que puede cubrir varios días (ej. la TRM
del viernes aplica también el fin de semana). Confirmado en vivo: 1942 de
8372 filas tienen `vigenciadesde != vigenciahasta`. Se publica tal cual
—una fila por publicación, con `vigente_hasta` para que quien necesite
expandir a un valor por día calendario lo haga él mismo— en vez de
fabricar filas para los días sin publicación propia.

Se invoca siempre como módulo, nunca como script suelto:
`python -m src.extractors.macroeconomia_trm_extractor` desde la raíz del
repo. Ver `.claude/rules/extractors.md` §6.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import polars as pl
from requests import RequestException

from src.extractors.base import (
    RAW_DIR,
    ROOT_DIR,
    STAGING_DIR,
    BaseExtractor,
    ExtractionResult,
    ReusePolicy,
    compute_sha256,
    ensure_staging_directories,
    write_raw_snapshot_atomic,
    write_staging_csv_atomic,
)
from src.extractors.http_utils import get_json

DATASET_NAME = "macroeconomia_trm"
SOURCE_URL = "https://www.datos.gov.co/resource/32sa-8pi3.json"
SOURCE_NAME = "Superintendencia Financiera de Colombia (SUPERFINANCIERA) — TRM (vía datos.gov.co)"

# 8372 filas conocidas (2026-10-22) — muy por debajo de cualquier límite de
# página de Socrata, un solo request alcanza. $limit generoso por si crece.
FETCH_LIMIT = 20_000
FETCH_TIMEOUT_SECONDS = 60
EXPECTED_MIN_ROWS = 8_000

PRIMARY_KEY = ["fecha"]

REUSE_POLICY = ReusePolicy(
    status="open-attribution",
    license="CC BY-SA 4.0",
    license_url="https://www.datos.gov.co/resource/32sa-8pi3",
    attribution_required=True,
    redistribution_ok=True,
    summary=(
        "Datos oficiales de la Superintendencia Financiera de Colombia "
        "(SUPERFINANCIERA) publicados en datos.gov.co bajo CC BY-SA 4.0 "
        "(share-alike): redistribuir con atribución a la Superfinanciera y "
        "bajo la misma licencia. Ver docs/licenses/data_licenses.md."
    ),
)

# Qué cae a fallback: problemas de la FUENTE (red caída, HTTP 4xx/5xx tras
# reintentos, JSON con forma inesperada). Un bug de programación real debe
# reventar. Ver `.claude/rules/extractors.md` §1.
EXPECTED_FETCH_FAILURES: tuple[type[Exception], ...] = (
    RequestException,
    KeyError,
    ValueError,
    TypeError,
)

# Fallback mínimo para desarrollo offline / CI sin red. NUNCA se publica.
# Filas reales observadas en la fuente (2026-10-22), incluida una con
# vigenciadesde != vigenciahasta (fin de semana) para ejercitar ese caso.
MACROECONOMIA_TRM_FALLBACK_DATA: list[dict[str, Any]] = [
    {
        "valor": "3191.47",
        "unidad": "COP",
        "vigenciadesde": "2026-10-22T00:00:00.000",
        "vigenciahasta": "2026-10-22T00:00:00.000",
    },
    {
        "valor": "3163.76",
        "unidad": "COP",
        "vigenciadesde": "2026-10-21T00:00:00.000",
        "vigenciahasta": "2026-10-21T00:00:00.000",
    },
    {
        "valor": "3156.32",
        "unidad": "COP",
        "vigenciadesde": "2026-10-20T00:00:00.000",
        "vigenciahasta": "2026-10-20T00:00:00.000",
    },
    {
        "valor": "3174.67",
        "unidad": "COP",
        "vigenciadesde": "2026-10-17T00:00:00.000",
        "vigenciahasta": "2026-10-19T00:00:00.000",
    },
    {
        "valor": "3170.46",
        "unidad": "COP",
        "vigenciadesde": "2026-10-16T00:00:00.000",
        "vigenciahasta": "2026-10-16T00:00:00.000",
    },
]

_SCHEMA = {
    "fecha": pl.Date,
    "vigente_hasta": pl.Date,
    "trm": pl.Float64,
}


def _parse_fecha(value: str) -> date:
    """Socrata entrega `calendar_date` como '2026-10-22T00:00:00.000' —
    siempre medianoche, solo la parte de fecha tiene sentido."""
    return date.fromisoformat(value[:10])


def _build_record(row: dict[str, Any]) -> dict[str, Any]:
    """Puede lanzar (KeyError/ValueError/TypeError) si a esta fila le falta
    un campo indispensable o no parsea. `_normalize()` lo atrapa por fila."""
    return {
        "fecha": _parse_fecha(row["vigenciadesde"]),
        "vigente_hasta": _parse_fecha(row["vigenciahasta"]),
        "trm": float(row["valor"]),
    }


def _normalize(rows: list[dict[str, Any]]) -> tuple[pl.DataFrame, int]:
    records: list[dict[str, Any]] = []
    skipped = 0
    for row in rows:
        try:
            records.append(_build_record(row))
        except (KeyError, ValueError, TypeError):
            skipped += 1
    df = pl.DataFrame(records, schema=_SCHEMA)
    return df.sort("fecha"), skipped


def _fetch_all_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = get_json(
        SOURCE_URL,
        params={"$limit": FETCH_LIMIT, "$order": "vigenciadesde"},
        timeout=FETCH_TIMEOUT_SECONDS,
    )
    return rows


class MacroeconomiaTrmExtractor(BaseExtractor):
    @property
    def dataset_name(self) -> str:
        return DATASET_NAME

    def fetch(self, **kwargs: Any) -> ExtractionResult:
        notes: list[str] = []
        try:
            rows = _fetch_all_rows()
            if len(rows) < EXPECTED_MIN_ROWS:
                notes.append(
                    f"La fuente devolvió solo {len(rows)} filas, menos de las "
                    f"{EXPECTED_MIN_ROWS} esperadas como mínimo."
                )
            df, skipped = _normalize(rows)
            if skipped > 0:
                notes.append(
                    f"{skipped} filas se descartaron durante la normalización por "
                    "faltarles un campo indispensable o no parsear "
                    "(valor/vigenciadesde/vigenciahasta)."
                )

            ensure_staging_directories()
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            raw_path = RAW_DIR / f"macroeconomia_trm_{timestamp}.json"
            raw_bytes = json.dumps(rows, ensure_ascii=False, indent=2).encode("utf-8")
            write_raw_snapshot_atomic(raw_path, raw_bytes)

            return ExtractionResult(
                dataset=DATASET_NAME,
                dataframe=df,
                source_name=SOURCE_NAME,
                source_url=SOURCE_URL,
                source_mode="live",
                source_detail="Socrata API, dataset 32sa-8pi3, sin paginación (dataset pequeño)",
                reuse_policy=REUSE_POLICY,
                raw_snapshot_path=str(raw_path.relative_to(ROOT_DIR)),
                snapshot_hash=compute_sha256(raw_bytes),
                notes=notes,
            )
        except EXPECTED_FETCH_FAILURES as exc:
            df, _skipped = _normalize(MACROECONOMIA_TRM_FALLBACK_DATA)
            return ExtractionResult(
                dataset=DATASET_NAME,
                dataframe=df,
                source_name=SOURCE_NAME,
                source_url=SOURCE_URL,
                source_mode="fallback",
                source_detail=f"fallback embebido tras fallo de fetch en vivo: {exc!r}",
                reuse_policy=REUSE_POLICY,
                notes=[
                    "source_mode=fallback: dataset de muestra para desarrollo offline, "
                    "NO se publica."
                ],
            )

    def write_staging(self, result: ExtractionResult) -> Path:
        ensure_staging_directories()
        csv_path = STAGING_DIR / "macroeconomia_trm.csv"
        metadata_path = STAGING_DIR / "macroeconomia_trm.metadata.json"
        return write_staging_csv_atomic(
            result.dataframe, csv_path, metadata_path, result.to_staging_metadata()
        )


if __name__ == "__main__":
    extractor = MacroeconomiaTrmExtractor()
    outcome = extractor.run()
    print(f"[{DATASET_NAME}] source_mode={outcome.source_mode} rows={outcome.dataframe.height}")
