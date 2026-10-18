"""Extractor de códigos DIVIPOLA (departamentos + municipios), fuente DANE.

Fuente primaria: API Socrata de datos.gov.co, dataset "DIVIPOLA- Códigos
municipios" (id `gdxc-w37w`), publicado por el DANE, licencia CC BY-SA 4.0.
Confirmado en vivo el 2026-10-17: 1122 municipios, 33 departamentos.

https://www.datos.gov.co/Mapas-Nacionales/DIVIPOLA-C-digos-municipios/gdxc-w37w

Nota de alcance: esta fuente entrega código + nombre + centroide (lon/lat),
NO geometría de polígonos. La geometría del Marco Geoestadístico Nacional
(MGN) queda pendiente como una segunda iteración de esta misma fuente — ver
docs/roadmap/roadmap.md.

Se invoca siempre como módulo, nunca como script suelto:
`python -m src.extractors.divipola_extractor` desde la raíz del repo (así
`src` se resuelve como paquete). Ver `.claude/rules/extractors.md` §6.
"""

from __future__ import annotations

from datetime import UTC, datetime
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

DATASET_NAME = "divipola"
SOURCE_URL = "https://www.datos.gov.co/resource/gdxc-w37w.json"
SOURCE_NAME = "DANE — DIVIPOLA Códigos municipios (vía datos.gov.co)"

# Límite de página generoso: la fuente tiene 1122 filas conocidas (2026-10-17).
# Si algún día retorna >= FETCH_LIMIT filas, probablemente hay que paginar —
# ver la advertencia en `notes` más abajo.
FETCH_LIMIT = 5000
EXPECTED_MIN_ROWS = 1000

REUSE_POLICY = ReusePolicy(
    status="open-attribution",
    license="CC BY-SA 4.0",
    license_url="https://www.datos.gov.co/resource/gdxc-w37w",
    attribution_required=True,
    redistribution_ok=True,
    summary=(
        "Datos oficiales del DANE publicados en datos.gov.co bajo "
        "CC BY-SA 4.0 (share-alike): redistribuir con atribución al DANE y "
        "bajo la misma licencia. Ver docs/licenses/data_licenses.md."
    ),
)

# Qué cae a fallback: problemas de la FUENTE (red caída, HTTP 4xx/5xx tras
# agotar reintentos, JSON con forma distinta a la esperada — JSONDecodeError
# hereda de ValueError). Un bug de programación real (AttributeError,
# NameError, etc.) NO está acá a propósito: debe reventar fuerte en vez de
# disfrazarse de "fuente caída". Ver `.claude/rules/extractors.md` §1.
EXPECTED_FETCH_FAILURES: tuple[type[Exception], ...] = (
    RequestException,
    KeyError,
    ValueError,
    TypeError,
)

# Fallback mínimo para desarrollo offline / CI sin red. NUNCA se publica:
# la CI de publicación rechaza cualquier dataset con source_mode="fallback".
DIVIPOLA_FALLBACK_DATA: list[dict[str, Any]] = [
    {
        "cod_dpto": "11",
        "dpto": "BOGOTÁ, D.C.",
        "cod_mpio": "11001",
        "nom_mpio": "BOGOTÁ, D.C.",
        "tipo_municipio": "Capital",
        "longitud": "-74,083652",
        "latitud": "4,609710",
    },
    {
        "cod_dpto": "05",
        "dpto": "ANTIOQUIA",
        "cod_mpio": "05001",
        "nom_mpio": "MEDELLÍN",
        "tipo_municipio": "Municipio",
        "longitud": "-75,581775",
        "latitud": "6,246631",
    },
    {
        "cod_dpto": "76",
        "dpto": "VALLE DEL CAUCA",
        "cod_mpio": "76001",
        "nom_mpio": "CALI",
        "tipo_municipio": "Municipio",
        "longitud": "-76,531985",
        "latitud": "3,420556",
    },
]


def _parse_coord(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value.replace(",", "."))
    except ValueError:
        return None


def _normalize(rows: list[dict[str, Any]]) -> pl.DataFrame:
    records = [
        {
            "cod_dpto": str(row["cod_dpto"]).zfill(2),
            "nombre_dpto": row["dpto"],
            "cod_mpio": str(row["cod_mpio"]).zfill(5),
            "nombre_mpio": row["nom_mpio"],
            "tipo_municipio": row.get("tipo_municipio", ""),
            "longitud": _parse_coord(row.get("longitud")),
            "latitud": _parse_coord(row.get("latitud")),
        }
        for row in rows
    ]
    df = pl.DataFrame(
        records,
        schema={
            "cod_dpto": pl.Utf8,
            "nombre_dpto": pl.Utf8,
            "cod_mpio": pl.Utf8,
            "nombre_mpio": pl.Utf8,
            "tipo_municipio": pl.Utf8,
            "longitud": pl.Float64,
            "latitud": pl.Float64,
        },
    )
    return df.unique(subset=["cod_mpio"], keep="first").sort("cod_mpio")


class DivipolaExtractor(BaseExtractor):
    @property
    def dataset_name(self) -> str:
        return DATASET_NAME

    def fetch(self, **kwargs: Any) -> ExtractionResult:
        notes: list[str] = []
        try:
            rows = get_json(SOURCE_URL, params={"$limit": FETCH_LIMIT})
            if len(rows) >= FETCH_LIMIT:
                notes.append(
                    f"La fuente devolvió >= {FETCH_LIMIT} filas: posible truncamiento, "
                    "considerar paginación ($offset)."
                )
            if len(rows) < EXPECTED_MIN_ROWS:
                notes.append(
                    f"La fuente devolvió solo {len(rows)} filas, menos de las "
                    f"{EXPECTED_MIN_ROWS} esperadas como mínimo."
                )
            df = _normalize(rows)

            ensure_staging_directories()
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            raw_path = RAW_DIR / f"divipola_{timestamp}.json"
            write_raw_snapshot_atomic(raw_path, rows)
            snapshot_bytes = raw_path.read_bytes()

            return ExtractionResult(
                dataset=DATASET_NAME,
                dataframe=df,
                source_name=SOURCE_NAME,
                source_url=SOURCE_URL,
                source_mode="live",
                source_detail="Socrata API, dataset gdxc-w37w",
                reuse_policy=REUSE_POLICY,
                raw_snapshot_path=str(raw_path.relative_to(ROOT_DIR)),
                snapshot_hash=compute_sha256(snapshot_bytes),
                notes=notes,
            )
        except EXPECTED_FETCH_FAILURES as exc:
            df = _normalize(DIVIPOLA_FALLBACK_DATA)
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
        csv_path = STAGING_DIR / "divipola.csv"
        metadata_path = STAGING_DIR / "divipola.metadata.json"
        return write_staging_csv_atomic(
            result.dataframe, csv_path, metadata_path, result.to_staging_metadata()
        )


if __name__ == "__main__":
    extractor = DivipolaExtractor()
    outcome = extractor.run()
    print(f"[{DATASET_NAME}] source_mode={outcome.source_mode} rows={outcome.dataframe.height}")
