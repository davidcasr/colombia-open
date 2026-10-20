"""Extractor de hurto por modalidades (residencias y comercio), fuente Policía Nacional.

Fuente primaria: API Socrata de datos.gov.co, dataset "Reporte Hurto por
Modalidades Policía Nacional" (id `6sqw-8cg5`), publicado por la Dirección
General de la Policía Nacional (DIPON), licencia CC BY-SA 4.0. Confirmado
en vivo el 2026-10-20: 653384 filas, 2010-01-01 a 2025-12-31.

https://www.datos.gov.co/resource/6sqw-8cg5

Mismo formato que lesiones personales (`delincuencia_lesiones_personales_extractor.py`):
microdato por hecho, `codigo_dane` de 8 dígitos (municipio + centro
poblado) y nombres de capital con sufijo " (CT)". A diferencia de
lesiones, la fuente solo trae 2 modalidades (`tipo_de_hurto`): "ARTÍCULO
239. HURTO ENTIDADES COMERCIALES" y "ARTÍCULO 239. HURTO RESIDENCIAS" — se
deriva una columna `modalidad` (comercio / residencias) análoga a
`tipo_lesion`. Decisión de alcance (misma que lesiones, ver
docs/datasets/delincuencia_hurto_modalidades.md):

- Se conservan todas las dimensiones, pero el centro poblado se colapsa a
  municipio: una fila por fecha + cod_mpio + tipo_hurto + arma_medio +
  genero + grupo_etario, con `cantidad` sumada.
- `cantidad` es siempre "1" en la fuente (un hecho = un registro), pero se
  suma igual al agregar por si dos hechos caen en la misma clave.

Notas de calidad de dato conocidas (2026-10-20):

- Al menos 1 fila trae `codigo_dane` = "00000000" (sin municipio, pese a
  traer nombre de departamento/municipio). Se EXCLUYE — no se fabrica un
  código — y el conteo queda en las `notes` de staging, igual que lesiones.
- `genero` viene nulo en ~89% de las filas (582971 de 653384) y
  `grupo_etario` en ~8.8% — no se rellenan.

Se invoca siempre como módulo, nunca como script suelto:
`python -m src.extractors.delincuencia_hurto_modalidades_extractor` desde
la raíz del repo. Ver `.claude/rules/extractors.md` §6.
"""

from __future__ import annotations

import json
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

DATASET_NAME = "delincuencia_hurto_modalidades"
SOURCE_URL = "https://www.datos.gov.co/resource/6sqw-8cg5.json"
SOURCE_NAME = "Policía Nacional (DIPON) — Hurto por modalidades (vía datos.gov.co)"

# 653384 filas conocidas (2026-10-20). Mismo patrón de paginado que lesiones
# y hurto a personas: `$order=:id` explícito, Socrata no garantiza orden
# estable entre páginas sin esto.
PAGE_SIZE = 50_000
PAGE_TIMEOUT_SECONDS = 120
EXPECTED_MIN_ROWS = 600_000

# Código que la fuente usa cuando no hay municipio asignado (mismo defecto
# que lesiones: "00000" de departamento con "000" de centro poblado).
CODIGO_SIN_MUNICIPIO = "00000"

REUSE_POLICY = ReusePolicy(
    status="open-attribution",
    license="CC BY-SA 4.0",
    license_url="https://www.datos.gov.co/resource/6sqw-8cg5",
    attribution_required=True,
    redistribution_ok=True,
    summary=(
        "Datos oficiales de la Policía Nacional (DIPON) publicados en datos.gov.co "
        "bajo CC BY-SA 4.0 (share-alike): redistribuir con atribución a la Policía "
        "Nacional y bajo la misma licencia. Ver docs/licenses/data_licenses.md."
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
# Filas reales observadas en la fuente (2026-10-20): incluye las dos
# modalidades, una capital con sufijo "(CT)", un centro poblado distinto de
# cabecera que se colapsa con su cabecera, una fila con `codigo_dane`
# "00000000" para ejercitar la exclusión, y una sin género.
DELINCUENCIA_HURTO_MODALIDADES_FALLBACK_DATA: list[dict[str, Any]] = [
    {
        "departamento": "BOGOTA",
        "municipio": "Bogotá D.C. (CT)",
        "codigo_dane": "11001000",
        "armas_medios": "NO REPORTADO",
        "fecha_hecho": "15/07/2026",
        "genero": "MASCULINO",
        "grupo_etario": "ADULTOS",
        "tipo_de_hurto": "ARTÍCULO 239. HURTO ENTIDADES COMERCIALES",
        "cantidad": "1",
    },
    {
        "departamento": "BOGOTA",
        "municipio": "Bogotá D.C. (CT)",
        "codigo_dane": "11001009",
        "armas_medios": "NO REPORTADO",
        "fecha_hecho": "15/07/2026",
        "genero": "FEMENINO",
        "grupo_etario": "ADULTOS",
        "tipo_de_hurto": "ARTÍCULO 239. HURTO ENTIDADES COMERCIALES",
        "cantidad": "1",
    },
    {
        "departamento": "SANTANDER",
        "municipio": "Gambita",
        "codigo_dane": "68298000",
        "armas_medios": "ARMA DE FUEGO",
        "fecha_hecho": "24/07/2026",
        "genero": "MASCULINO",
        "grupo_etario": "ADULTOS",
        "tipo_de_hurto": "ARTÍCULO 239. HURTO RESIDENCIAS",
        "cantidad": "1",
    },
    {
        "departamento": "ANTIOQUIA",
        "municipio": "Medellín (CT)",
        "codigo_dane": "05001000",
        "armas_medios": "SIN EMPLEO DE ARMAS",
        "fecha_hecho": "02/06/2026",
        "genero": None,
        "grupo_etario": "ADULTOS",
        "tipo_de_hurto": "ARTÍCULO 239. HURTO RESIDENCIAS",
        "cantidad": "1",
    },
    {
        "departamento": "VALLE DEL CAUCA",
        "municipio": "Cali (CT)",
        "codigo_dane": "76001000",
        "armas_medios": "LLAVE MAESTRA",
        "fecha_hecho": "02/06/2026",
        "genero": None,
        "grupo_etario": None,
        "tipo_de_hurto": "ARTÍCULO 239. HURTO RESIDENCIAS",
        "cantidad": "1",
    },
    {
        "departamento": "ANTIOQUIA",
        "municipio": "Medellín (CT)",
        "codigo_dane": "00000000",
        "armas_medios": "ARMA DE FUEGO",
        "fecha_hecho": "27/06/2014",
        "genero": None,
        "grupo_etario": None,
        "tipo_de_hurto": "ARTÍCULO 239. HURTO ENTIDADES COMERCIALES",
        "cantidad": "1",
    },
]

_SOURCE_COLUMNS = [
    "departamento",
    "municipio",
    "codigo_dane",
    "armas_medios",
    "fecha_hecho",
    "genero",
    "grupo_etario",
    "tipo_de_hurto",
    "cantidad",
]

# Clave de agregación = clave primaria del dataset publicado.
PRIMARY_KEY = ["fecha", "cod_mpio", "tipo_hurto", "arma_medio", "genero", "grupo_etario"]

_OUTPUT_COLUMNS = [
    "fecha",
    "anio",
    "cod_dpto",
    "nombre_dpto",
    "cod_mpio",
    "nombre_mpio",
    "tipo_hurto",
    "modalidad",
    "arma_medio",
    "genero",
    "grupo_etario",
    "cantidad",
]

_SCHEMA = {
    "fecha": pl.Date,
    "anio": pl.Int64,
    "cod_dpto": pl.Utf8,
    "nombre_dpto": pl.Utf8,
    "cod_mpio": pl.Utf8,
    "nombre_mpio": pl.Utf8,
    "tipo_hurto": pl.Utf8,
    "modalidad": pl.Utf8,
    "arma_medio": pl.Utf8,
    "genero": pl.Utf8,
    "grupo_etario": pl.Utf8,
    "cantidad": pl.Int64,
}


def _modalidad_expr(tipo_hurto: pl.Expr) -> pl.Expr:
    return (
        pl.when(tipo_hurto.str.contains(r"(?i)RESIDENCIAS"))
        .then(pl.lit("residencias"))
        .when(tipo_hurto.str.contains(r"(?i)COMERCIALES"))
        .then(pl.lit("comercio"))
        .otherwise(pl.lit(None, dtype=pl.Utf8))
    )


def _most_frequent(values: pl.Expr) -> pl.Expr:
    """Valor más frecuente de un grupo; desempata por orden alfabético para
    que el resultado sea determinista entre builds."""
    return values.drop_nulls().mode().sort().first()


def _normalize(rows: list[dict[str, Any]]) -> tuple[pl.DataFrame, int, int, int]:
    """Devuelve (df, filas_sin_municipio, hechos_sin_municipio,
    filas_descartadas_por_parseo). Vectorizado con Polars: la fuente tiene
    ~650 mil filas."""
    if not rows:
        return pl.DataFrame(schema=_SCHEMA), 0, 0, 0

    raw = pl.DataFrame(rows, schema=dict.fromkeys(_SOURCE_COLUMNS, pl.Utf8)).with_columns(
        pl.col("codigo_dane").str.strip_chars().str.zfill(8).alias("_codigo"),
        pl.col("cantidad")
        .str.strip_chars()
        .cast(pl.Float64, strict=False)
        .cast(pl.Int64, strict=False)
        .alias("_cantidad"),
        pl.col("fecha_hecho")
        .str.strip_chars()
        .str.strptime(pl.Date, "%d/%m/%Y", strict=False)
        .alias("_fecha"),
    )

    # Sin municipio: código ausente, no numérico o "00000..." en la fuente.
    sin_municipio = (
        pl.col("_codigo").is_null()
        | ~pl.col("_codigo").str.contains(r"^\d{8}$")
        | (pl.col("_codigo").str.slice(0, 5) == CODIGO_SIN_MUNICIPIO)
    )
    excluded = raw.filter(sin_municipio)
    excluded_rows = excluded.height
    excluded_hechos = int(excluded["_cantidad"].fill_null(0).sum())

    valid = raw.filter(~sin_municipio)
    parseable = (
        pl.col("_fecha").is_not_null()
        & pl.col("_cantidad").is_not_null()
        & pl.col("tipo_de_hurto").is_not_null()
    )
    skipped = valid.filter(~parseable).height

    records = valid.filter(parseable).select(
        pl.col("_fecha").alias("fecha"),
        pl.col("_codigo").str.slice(0, 2).alias("cod_dpto"),
        pl.col("departamento").str.strip_chars().alias("nombre_dpto"),
        pl.col("_codigo").str.slice(0, 5).alias("cod_mpio"),
        pl.col("municipio").str.strip_chars().str.replace(r"\s*\(CT\)$", "").alias("nombre_mpio"),
        pl.col("tipo_de_hurto").str.strip_chars().alias("tipo_hurto"),
        pl.col("armas_medios").str.strip_chars().alias("arma_medio"),
        pl.col("genero").str.strip_chars().alias("genero"),
        pl.col("grupo_etario").str.strip_chars().alias("grupo_etario"),
        pl.col("_cantidad").alias("cantidad"),
    )

    # Un nombre por código (el más frecuente), no el de cada fila: la fuente
    # puede traer código y nombre contradictorios en unas pocas filas (mismo
    # defecto observado en lesiones personales).
    nombres_mpio = records.group_by("cod_mpio").agg(_most_frequent(pl.col("nombre_mpio")))
    nombres_dpto = records.group_by("cod_dpto").agg(_most_frequent(pl.col("nombre_dpto")))

    df = (
        records.group_by(["cod_dpto", *PRIMARY_KEY])
        .agg(pl.col("cantidad").sum())
        .join(nombres_mpio, on="cod_mpio", how="left")
        .join(nombres_dpto, on="cod_dpto", how="left")
        .with_columns(
            pl.col("fecha").dt.year().cast(pl.Int64).alias("anio"),
            _modalidad_expr(pl.col("tipo_hurto")).alias("modalidad"),
        )
        .select(_OUTPUT_COLUMNS)
        .cast(_SCHEMA)  # type: ignore[arg-type]
        .sort(PRIMARY_KEY, nulls_last=True)
    )
    return df, excluded_rows, excluded_hechos, skipped


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


def _normalization_notes(excluded_rows: int, excluded_hechos: int, skipped: int) -> list[str]:
    notes: list[str] = []
    if excluded_rows > 0:
        notes.append(
            f"{excluded_rows} filas ({excluded_hechos} hechos) excluidas por no "
            "tener municipio en la fuente (codigo_dane ausente o '00000000'); ver "
            "docs/datasets/delincuencia_hurto_modalidades.md."
        )
    if skipped > 0:
        notes.append(
            f"{skipped} filas se descartaron durante la normalización por faltarles "
            "un campo indispensable o no parsear (fecha_hecho/cantidad/tipo_de_hurto)."
        )
    return notes


class DelincuenciaHurtoModalidadesExtractor(BaseExtractor):
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
            df, excluded_rows, excluded_hechos, skipped = _normalize(rows)
            notes.extend(_normalization_notes(excluded_rows, excluded_hechos, skipped))

            ensure_staging_directories()
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            raw_path = RAW_DIR / f"delincuencia_hurto_modalidades_{timestamp}.json"
            # Compacto (sin indent), mismo motivo que lesiones: ~650k filas.
            raw_bytes = json.dumps(rows, ensure_ascii=False).encode("utf-8")
            write_raw_snapshot_atomic(raw_path, raw_bytes)

            return ExtractionResult(
                dataset=DATASET_NAME,
                dataframe=df,
                source_name=SOURCE_NAME,
                source_url=SOURCE_URL,
                source_mode="live",
                source_detail=(
                    f"Socrata API, dataset 6sqw-8cg5, paginado en bloques de {PAGE_SIZE} "
                    "ordenado por :id; agregado de centro poblado a municipio"
                ),
                reuse_policy=REUSE_POLICY,
                raw_snapshot_path=str(raw_path.relative_to(ROOT_DIR)),
                snapshot_hash=compute_sha256(raw_bytes),
                notes=notes,
            )
        except EXPECTED_FETCH_FAILURES as exc:
            df, excluded_rows, excluded_hechos, skipped = _normalize(
                DELINCUENCIA_HURTO_MODALIDADES_FALLBACK_DATA
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
                    *_normalization_notes(excluded_rows, excluded_hechos, skipped),
                ],
            )

    def write_staging(self, result: ExtractionResult) -> Path:
        ensure_staging_directories()
        csv_path = STAGING_DIR / "delincuencia_hurto_modalidades.csv"
        metadata_path = STAGING_DIR / "delincuencia_hurto_modalidades.metadata.json"
        return write_staging_csv_atomic(
            result.dataframe, csv_path, metadata_path, result.to_staging_metadata()
        )


if __name__ == "__main__":
    extractor = DelincuenciaHurtoModalidadesExtractor()
    outcome = extractor.run()
    print(f"[{DATASET_NAME}] source_mode={outcome.source_mode} rows={outcome.dataframe.height}")
