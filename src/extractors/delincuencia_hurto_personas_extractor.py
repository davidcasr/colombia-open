"""Extractor de hurto a personas por municipio y día, fuente MinDefensa.

Fuente primaria: API Socrata de datos.gov.co, dataset "HURTO PERSONAS"
(id `4rxi-8m8d`), publicado por el Ministerio de Defensa Nacional con datos
de la Policía Nacional, licencia CC BY-SA 4.0. Confirmado en vivo el
2026-10-19: 651200 filas, 2003-01-01 a 2026-08-31, ~3.77 millones de
víctimas en 1113 municipios.

https://www.datos.gov.co/resource/4rxi-8m8d

La fuente ya viene agregada (una fila por fecha + municipio, con
`cantidad` = número de víctimas) — no es microdato por hecho, así que se
publica con la misma granularidad diaria, sin re-agregar (decisión de
alcance, ver docs/datasets/delincuencia_hurto_personas.md).

Nota de calidad de dato conocida: 365 filas (una por día de 2008, 64185
víctimas en total) vienen con `cod_depto`/`cod_muni`/`municipio` =
"SIN ESTABLECER". Ese año la fuente casi no tiene desagregación municipal
(solo 76 municipios con código, contra ~700-1000 cualquier otro año). Las
filas sin código se EXCLUYEN del dataset — no tienen join posible con
`municipios` y no se fabrica un código para ellas — y el conteo de filas y
víctimas excluidas queda en las `notes` de la metadata de staging. El
validador (`src/validation/_delincuencia.py`) reporta el año de cobertura
municipal anómala como warning.

Los otros dos endpoints del dominio delincuencia traen `codigo_dane` de 8
dígitos y nombres de municipio con sufijos tipo "(CT)": lesiones
(`72sg-cybi`) tiene su propio extractor
(`delincuencia_lesiones_personales_extractor.py`); hurto por modalidades
(`6sqw-8cg5`) también (`delincuencia_hurto_modalidades_extractor.py`).

Se invoca siempre como módulo, nunca como script suelto:
`python -m src.extractors.delincuencia_hurto_personas_extractor` desde la
raíz del repo. Ver `.claude/rules/extractors.md` §6.
"""

from __future__ import annotations

import contextlib
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

DATASET_NAME = "delincuencia_hurto_personas"
SOURCE_URL = "https://www.datos.gov.co/resource/4rxi-8m8d.json"
SOURCE_NAME = "MinDefensa / Policía Nacional — Hurto a personas (vía datos.gov.co)"

# 651200 filas conocidas (2026-10-19). Paginado igual que
# educacion_establecimientos, pero con `$order=:id` explícito: Socrata no
# garantiza un orden estable entre páginas sin $order, y sin él una página
# puede repetir o saltarse filas.
PAGE_SIZE = 50_000
# Observado en vivo: ~2s por página de 50k filas (6 columnas cortas, mucho
# más liviano que educacion). Se deja margen amplio sobre el default de 30s.
PAGE_TIMEOUT_SECONDS = 120
EXPECTED_MIN_ROWS = 600_000

# Valor que la fuente usa en cod_depto/cod_muni cuando no hay municipio.
SIN_ESTABLECER = "SIN ESTABLECER"

REUSE_POLICY = ReusePolicy(
    status="open-attribution",
    license="CC BY-SA 4.0",
    license_url="https://www.datos.gov.co/resource/4rxi-8m8d",
    attribution_required=True,
    redistribution_ok=True,
    summary=(
        "Datos oficiales del Ministerio de Defensa Nacional (fuente: Policía "
        "Nacional) publicados en datos.gov.co bajo CC BY-SA 4.0 (share-alike): "
        "redistribuir con atribución a MinDefensa y bajo la misma licencia. Ver "
        "docs/licenses/data_licenses.md."
    ),
)

# Qué cae a fallback: problemas de la FUENTE (red, HTTP 4xx/5xx tras
# reintentos, JSON con forma inesperada). Un bug de programación real debe
# reventar. Ver `.claude/rules/extractors.md` §1.
EXPECTED_FETCH_FAILURES: tuple[type[Exception], ...] = (
    RequestException,
    KeyError,
    ValueError,
    TypeError,
)

# Fallback mínimo para desarrollo offline / CI sin red. NUNCA se publica.
# Filas reales observadas en la fuente (2026-10-19), incluida una fila
# "SIN ESTABLECER" de 2008 para ejercitar la exclusión también offline.
DELINCUENCIA_HURTO_PERSONAS_FALLBACK_DATA: list[dict[str, Any]] = [
    {
        "fecha_hecho": "2003-02-01T00:00:00.000",
        "cod_depto": "52",
        "departamento": "NARIÑO",
        "cod_muni": "52480",
        "municipio": "NARIÑO",
        "cantidad": "1",
    },
    {
        "fecha_hecho": "2003-02-01T00:00:00.000",
        "cod_depto": "54",
        "departamento": "NORTE DE SANTANDER",
        "cod_muni": "54001",
        "municipio": "CUCUTA",
        "cantidad": "5",
    },
    {
        "fecha_hecho": "2008-03-14T00:00:00.000",
        "cod_depto": "SIN ESTABLECER",
        "departamento": "SIN ESTABLECER",
        "cod_muni": "SIN ESTABLECER",
        "municipio": "SIN ESTABLECER",
        "cantidad": "221",
    },
    {
        "fecha_hecho": "2008-03-14T00:00:00.000",
        "cod_depto": "05",
        "departamento": "ANTIOQUIA",
        "cod_muni": "05001",
        "municipio": "MEDELLIN",
        "cantidad": "8",
    },
    {
        "fecha_hecho": "2025-03-14T00:00:00.000",
        "cod_depto": "08",
        "departamento": "ATLANTICO",
        "cod_muni": "08001",
        "municipio": "BARRANQUILLA",
        "cantidad": "13",
    },
    {
        "fecha_hecho": "2025-03-14T00:00:00.000",
        "cod_depto": "76",
        "departamento": "VALLE DEL CAUCA",
        "cod_muni": "76001",
        "municipio": "CALI",
        "cantidad": "66",
    },
    {
        "fecha_hecho": "2025-03-14T00:00:00.000",
        "cod_depto": "11",
        "departamento": "BOGOTA D.C.",
        "cod_muni": "11001",
        "municipio": "BOGOTA D.C.",
        "cantidad": "482",
    },
    {
        "fecha_hecho": "2025-03-14T00:00:00.000",
        "cod_depto": "05",
        "departamento": "ANTIOQUIA",
        "cod_muni": "05001",
        "municipio": "MEDELLIN",
        "cantidad": "74",
    },
]

_SCHEMA = {
    "fecha": pl.Date,
    "anio": pl.Int64,
    "cod_dpto": pl.Utf8,
    "nombre_dpto": pl.Utf8,
    "cod_mpio": pl.Utf8,
    "nombre_mpio": pl.Utf8,
    "cantidad": pl.Int64,
}


def _parse_fecha(value: str) -> date:
    """Socrata entrega `calendar_date` como '2026-08-31T00:00:00.000' —
    siempre medianoche, solo la parte de fecha tiene sentido."""
    return date.fromisoformat(value[:10])


def _build_record(row: dict[str, Any]) -> dict[str, Any]:
    """Puede lanzar (KeyError/ValueError/TypeError) si a la fila le falta un
    campo indispensable o no parsea; `_normalize()` lo atrapa por fila."""
    fecha = _parse_fecha(row["fecha_hecho"])
    return {
        "fecha": fecha,
        "anio": fecha.year,
        "cod_dpto": str(row["cod_depto"]).zfill(2),
        "nombre_dpto": row.get("departamento"),
        "cod_mpio": str(row["cod_muni"]).zfill(5),
        "nombre_mpio": row.get("municipio"),
        "cantidad": int(float(row["cantidad"])),
    }


def _is_sin_establecer(row: dict[str, Any]) -> bool:
    """Fila sin municipio asignado en la fuente (defecto conocido de 2008).
    Se detecta por código no numérico, no solo por el literal exacto, para
    que una variante de texto futura tampoco se cuele como código."""
    cod_muni = row.get("cod_muni")
    return cod_muni is None or not str(cod_muni).isdigit()


def _normalize(rows: list[dict[str, Any]]) -> tuple[pl.DataFrame, int, int, int]:
    """Devuelve (df, filas_sin_establecer, victimas_sin_establecer,
    filas_descartadas_por_parseo)."""
    records: list[dict[str, Any]] = []
    excluded_rows = 0
    excluded_victims = 0
    skipped = 0
    for row in rows:
        if _is_sin_establecer(row):
            excluded_rows += 1
            with contextlib.suppress(KeyError, ValueError, TypeError):
                excluded_victims += int(float(row["cantidad"]))
            continue
        try:
            records.append(_build_record(row))
        except (KeyError, ValueError, TypeError):
            skipped += 1
    df = pl.DataFrame(records, schema=_SCHEMA)
    return df.sort(["fecha", "cod_mpio"]), excluded_rows, excluded_victims, skipped


def _fetch_all_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = get_json(
            SOURCE_URL,
            params={"$limit": PAGE_SIZE, "$offset": offset, "$order": ":id"},
            timeout=PAGE_TIMEOUT_SECONDS,
        )
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return rows


def _normalization_notes(excluded_rows: int, excluded_victims: int, skipped: int) -> list[str]:
    notes: list[str] = []
    if excluded_rows > 0:
        notes.append(
            f"{excluded_rows} filas ({excluded_victims} víctimas) excluidas por no "
            f"tener municipio en la fuente (cod_muni='{SIN_ESTABLECER}'); ver "
            "docs/datasets/delincuencia_hurto_personas.md."
        )
    if skipped > 0:
        notes.append(
            f"{skipped} filas se descartaron durante la normalización por faltarles "
            "un campo indispensable o no parsear (fecha_hecho/cod_depto/cod_muni/cantidad)."
        )
    return notes


class DelincuenciaHurtoPersonasExtractor(BaseExtractor):
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
            df, excluded_rows, excluded_victims, skipped = _normalize(rows)
            notes.extend(_normalization_notes(excluded_rows, excluded_victims, skipped))

            ensure_staging_directories()
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            raw_path = RAW_DIR / f"delincuencia_hurto_personas_{timestamp}.json"
            # Compacto (sin indent), mismo motivo que educacion: ~650k filas.
            raw_bytes = json.dumps(rows, ensure_ascii=False).encode("utf-8")
            write_raw_snapshot_atomic(raw_path, raw_bytes)

            return ExtractionResult(
                dataset=DATASET_NAME,
                dataframe=df,
                source_name=SOURCE_NAME,
                source_url=SOURCE_URL,
                source_mode="live",
                source_detail=(
                    f"Socrata API, dataset 4rxi-8m8d, paginado en bloques de {PAGE_SIZE} "
                    "ordenado por :id"
                ),
                reuse_policy=REUSE_POLICY,
                raw_snapshot_path=str(raw_path.relative_to(ROOT_DIR)),
                snapshot_hash=compute_sha256(raw_bytes),
                notes=notes,
            )
        except EXPECTED_FETCH_FAILURES as exc:
            df, excluded_rows, excluded_victims, skipped = _normalize(
                DELINCUENCIA_HURTO_PERSONAS_FALLBACK_DATA
            )
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
                    "NO se publica.",
                    *_normalization_notes(excluded_rows, excluded_victims, skipped),
                ],
            )

    def write_staging(self, result: ExtractionResult) -> Path:
        ensure_staging_directories()
        csv_path = STAGING_DIR / "delincuencia_hurto_personas.csv"
        metadata_path = STAGING_DIR / "delincuencia_hurto_personas.metadata.json"
        return write_staging_csv_atomic(
            result.dataframe, csv_path, metadata_path, result.to_staging_metadata()
        )


if __name__ == "__main__":
    extractor = DelincuenciaHurtoPersonasExtractor()
    outcome = extractor.run()
    print(f"[{DATASET_NAME}] source_mode={outcome.source_mode} rows={outcome.dataframe.height}")
