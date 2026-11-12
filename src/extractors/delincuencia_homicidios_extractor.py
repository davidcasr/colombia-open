"""Extractor de víctimas de homicidio por municipio y día, fuente MinDefensa.

Fuente primaria: API Socrata de datos.gov.co, dataset "HOMICIDIO" (id
`m8fd-ahd9`), publicado por el Ministerio de Defensa Nacional con datos de
la Policía Nacional, licencia CC BY-SA 4.0. Confirmado en vivo el
2026-11-12: 345195 filas, 2003-01-01 a 2026-09-30, 345917 víctimas en 1108
municipios, ninguna fila sin código de municipio.

https://www.datos.gov.co/resource/m8fd-ahd9

Misma familia que `delincuencia_hurto_personas` (`fecha_hecho`/`cod_depto`/
`cod_muni`/`cantidad`, códigos DIVIPOLA de 2 y 5 dígitos), pero con cinco
dimensiones más: `zona`, `sexo`, `arma_medio`, `_modalidad_presunta` y
`spoa_caracterizacion`. Es casi microdato (una fila ≈ una víctima,
`cantidad` entre 1 y 38) y las filas NO son únicas ni por todas sus
dimensiones: la misma fecha, municipio y combinación aparece repetida.
Se publica igual que `delincuencia_hurto_modalidades`: con todas las
dimensiones de la fuente, agregando a una fila por combinación única con
`cantidad` sumada — sin perder víctimas ni dimensiones (decisión de
alcance, ver docs/datasets/delincuencia_homicidios.md).

Las filas sin municipio (código ausente o no numérico, como el
"SIN ESTABLECER" de hurto a personas) se excluyen y se cuentan en las
`notes` de la metadata de staging. Hoy la fuente no trae ninguna; la regla
queda por si aparecen.

Se invoca siempre como módulo, nunca como script suelto:
`python -m src.extractors.delincuencia_homicidios_extractor` desde la raíz
del repo. Ver `.claude/rules/extractors.md` §6.
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

DATASET_NAME = "delincuencia_homicidios"
SOURCE_URL = "https://www.datos.gov.co/resource/m8fd-ahd9.json"
SOURCE_NAME = "MinDefensa / Policía Nacional — Homicidio (vía datos.gov.co)"

# 345195 filas conocidas (2026-11-12). Mismo patrón de paginado que hurto a
# personas: `$order=:id` explícito, Socrata no garantiza orden estable
# entre páginas sin esto.
PAGE_SIZE = 50_000
PAGE_TIMEOUT_SECONDS = 120
EXPECTED_MIN_ROWS = 300_000

REUSE_POLICY = ReusePolicy(
    status="open-attribution",
    license="CC BY-SA 4.0",
    license_url="https://www.datos.gov.co/resource/m8fd-ahd9",
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
# Filas reales observadas en la fuente (2026-11-12): incluye dos filas
# idénticas en todas sus dimensiones (se suman), un feminicidio, una fila
# sin `arma_medio`, y una "SIN ESTABLECER" sintética para ejercitar la
# exclusión también offline.
DELINCUENCIA_HOMICIDIOS_FALLBACK_DATA: list[dict[str, Any]] = [
    {
        "fecha_hecho": "2026-09-30T00:00:00.000",
        "cod_depto": "27",
        "departamento": "CHOCO",
        "cod_muni": "27006",
        "municipio": "ACANDI",
        "zona": "RURAL",
        "sexo": "MASCULINO",
        "arma_medio": "ARMA DE FUEGO",
        "_modalidad_presunta": "SICARIATO",
        "spoa_caracterizacion": "HOMICIDIO INTENCIONAL O CON DOLO",
        "cantidad": "1",
    },
    {
        "fecha_hecho": "2026-09-30T00:00:00.000",
        "cod_depto": "68",
        "departamento": "SANTANDER",
        "cod_muni": "68081",
        "municipio": "BARRANCABERMEJA",
        "zona": "URBANA",
        "sexo": "MASCULINO",
        "arma_medio": "ARMA BLANCA / CORTOPUNZANTE",
        "_modalidad_presunta": "RIÑAS",
        "spoa_caracterizacion": "HOMICIDIO INTENCIONAL O CON DOLO",
        "cantidad": "1",
    },
    {
        "fecha_hecho": "2026-09-30T00:00:00.000",
        "cod_depto": "08",
        "departamento": "ATLANTICO",
        "cod_muni": "08001",
        "municipio": "BARRANQUILLA",
        "zona": "URBANA",
        "sexo": "MASCULINO",
        "arma_medio": "ARMA DE FUEGO",
        "_modalidad_presunta": "SICARIATO",
        "spoa_caracterizacion": "HOMICIDIO INTENCIONAL O CON DOLO",
        "cantidad": "1",
    },
    {
        "fecha_hecho": "2003-01-01T00:00:00.000",
        "cod_depto": "05",
        "departamento": "ANTIOQUIA",
        "cod_muni": "05001",
        "municipio": "MEDELLIN",
        "zona": "URBANA",
        "sexo": "MASCULINO",
        "arma_medio": "ARMA DE FUEGO",
        "_modalidad_presunta": "NO REPORTADA",
        "spoa_caracterizacion": "HOMICIDIO INTENCIONAL O CON DOLO",
        "cantidad": "1",
    },
    {
        "fecha_hecho": "2003-01-01T00:00:00.000",
        "cod_depto": "05",
        "departamento": "ANTIOQUIA",
        "cod_muni": "05001",
        "municipio": "MEDELLIN",
        "zona": "URBANA",
        "sexo": "MASCULINO",
        "arma_medio": "ARMA DE FUEGO",
        "_modalidad_presunta": "NO REPORTADA",
        "spoa_caracterizacion": "HOMICIDIO INTENCIONAL O CON DOLO",
        "cantidad": "1",
    },
    {
        "fecha_hecho": "2025-03-14T00:00:00.000",
        "cod_depto": "11",
        "departamento": "CUNDINAMARCA",
        "cod_muni": "11001",
        "municipio": "BOGOTÁ D.C. (CT)",
        "zona": "URBANA",
        "sexo": "FEMENINO",
        "arma_medio": "ARMA BLANCA / CORTOPUNZANTE",
        "_modalidad_presunta": "VIOLENCIA INTRAFAMILIAR",
        "spoa_caracterizacion": "FEMINICIDIO",
        "cantidad": "1",
    },
    {
        "fecha_hecho": "2025-03-14T00:00:00.000",
        "cod_depto": "76",
        "departamento": "VALLE",
        "cod_muni": "76001",
        "municipio": "CALI (CT)",
        "zona": "URBANA",
        "sexo": "MASCULINO",
        "arma_medio": None,
        "_modalidad_presunta": None,
        "spoa_caracterizacion": "HOMICIDIO INTENCIONAL O CON DOLO",
        "cantidad": "2",
    },
    {
        "fecha_hecho": "2025-03-14T00:00:00.000",
        "cod_depto": "SIN ESTABLECER",
        "departamento": "SIN ESTABLECER",
        "cod_muni": "SIN ESTABLECER",
        "municipio": "SIN ESTABLECER",
        "zona": "URBANA",
        "sexo": "MASCULINO",
        "arma_medio": "ARMA DE FUEGO",
        "_modalidad_presunta": "SICARIATO",
        "spoa_caracterizacion": "HOMICIDIO INTENCIONAL O CON DOLO",
        "cantidad": "1",
    },
]

_SOURCE_COLUMNS = [
    "fecha_hecho",
    "cod_depto",
    "departamento",
    "cod_muni",
    "municipio",
    "zona",
    "sexo",
    "arma_medio",
    "_modalidad_presunta",
    "spoa_caracterizacion",
    "cantidad",
]

# Clave de agregación = clave primaria del dataset publicado.
PRIMARY_KEY = [
    "fecha",
    "cod_mpio",
    "zona",
    "sexo",
    "arma_medio",
    "modalidad_presunta",
    "caracterizacion",
]

_OUTPUT_COLUMNS = [
    "fecha",
    "anio",
    "cod_dpto",
    "nombre_dpto",
    "cod_mpio",
    "nombre_mpio",
    "zona",
    "sexo",
    "arma_medio",
    "modalidad_presunta",
    "caracterizacion",
    "cantidad",
]

_SCHEMA = {
    "fecha": pl.Date,
    "anio": pl.Int64,
    "cod_dpto": pl.Utf8,
    "nombre_dpto": pl.Utf8,
    "cod_mpio": pl.Utf8,
    "nombre_mpio": pl.Utf8,
    "zona": pl.Utf8,
    "sexo": pl.Utf8,
    "arma_medio": pl.Utf8,
    "modalidad_presunta": pl.Utf8,
    "caracterizacion": pl.Utf8,
    "cantidad": pl.Int64,
}


def _most_frequent(values: pl.Expr) -> pl.Expr:
    """Valor más frecuente de un grupo; desempata por orden alfabético para
    que el resultado sea determinista entre builds."""
    return values.drop_nulls().mode().sort().first()


def _clean_text(name: str) -> pl.Expr:
    """Recorta espacios y convierte el texto vacío en nulo — la fuente
    entrega algunos `arma_medio`/`_modalidad_presunta` sin valor."""
    stripped = pl.col(name).str.strip_chars()
    return pl.when(stripped == "").then(None).otherwise(stripped)


def _normalize(rows: list[dict[str, Any]]) -> tuple[pl.DataFrame, int, int, int]:
    """Devuelve (df, filas_sin_municipio, victimas_sin_municipio,
    filas_descartadas_por_parseo). Vectorizado con Polars: la fuente tiene
    ~345 mil filas."""
    if not rows:
        return pl.DataFrame(schema=_SCHEMA), 0, 0, 0

    raw = pl.DataFrame(rows, schema=dict.fromkeys(_SOURCE_COLUMNS, pl.Utf8)).with_columns(
        pl.col("cod_muni").str.strip_chars().alias("_cod_muni"),
        pl.col("cod_depto").str.strip_chars().alias("_cod_depto"),
        pl.col("cantidad")
        .str.strip_chars()
        .cast(pl.Float64, strict=False)
        .cast(pl.Int64, strict=False)
        .alias("_cantidad"),
        # Socrata entrega `calendar_date` como '2026-09-30T00:00:00.000' —
        # siempre medianoche, solo la parte de fecha tiene sentido.
        pl.col("fecha_hecho")
        .str.strip_chars()
        .str.slice(0, 10)
        .str.strptime(pl.Date, "%Y-%m-%d", strict=False)
        .alias("_fecha"),
    )

    # Sin municipio: código ausente o no numérico ("SIN ESTABLECER" en otros
    # conjuntos de la misma familia). Se detecta por forma, no por literal.
    sin_municipio = pl.col("_cod_muni").is_null() | ~pl.col("_cod_muni").str.contains(r"^\d{1,5}$")
    excluded = raw.filter(sin_municipio)
    excluded_rows = excluded.height
    excluded_victims = int(excluded["_cantidad"].fill_null(0).sum())

    valid = raw.filter(~sin_municipio)
    parseable = (
        pl.col("_fecha").is_not_null()
        & pl.col("_cantidad").is_not_null()
        & pl.col("_cod_depto").str.contains(r"^\d{1,2}$").fill_null(False)
    )
    skipped = valid.filter(~parseable).height

    records = valid.filter(parseable).select(
        pl.col("_fecha").alias("fecha"),
        pl.col("_cod_depto").str.zfill(2).alias("cod_dpto"),
        pl.col("departamento").str.strip_chars().alias("nombre_dpto"),
        pl.col("_cod_muni").str.zfill(5).alias("cod_mpio"),
        pl.col("municipio").str.strip_chars().str.replace(r"\s*\(CT\)$", "").alias("nombre_mpio"),
        _clean_text("zona").alias("zona"),
        _clean_text("sexo").alias("sexo"),
        _clean_text("arma_medio").alias("arma_medio"),
        _clean_text("_modalidad_presunta").alias("modalidad_presunta"),
        _clean_text("spoa_caracterizacion").alias("caracterizacion"),
        pl.col("_cantidad").alias("cantidad"),
    )

    # Un nombre por código (el más frecuente), no el de cada fila: mismo
    # criterio que lesiones y hurto por modalidades, para que un código
    # tenga siempre un único nombre en el dataset publicado.
    nombres_mpio = records.group_by("cod_mpio").agg(_most_frequent(pl.col("nombre_mpio")))
    nombres_dpto = records.group_by("cod_dpto").agg(_most_frequent(pl.col("nombre_dpto")))

    df = (
        records.group_by(["cod_dpto", *PRIMARY_KEY])
        .agg(pl.col("cantidad").sum())
        .join(nombres_mpio, on="cod_mpio", how="left")
        .join(nombres_dpto, on="cod_dpto", how="left")
        .with_columns(pl.col("fecha").dt.year().cast(pl.Int64).alias("anio"))
        .select(_OUTPUT_COLUMNS)
        .cast(_SCHEMA)  # type: ignore[arg-type]
        .sort(PRIMARY_KEY, nulls_last=True)
    )
    return df, excluded_rows, excluded_victims, skipped


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
            "tener municipio en la fuente (cod_muni ausente o no numérico); ver "
            "docs/datasets/delincuencia_homicidios.md."
        )
    if skipped > 0:
        notes.append(
            f"{skipped} filas se descartaron durante la normalización por faltarles "
            "un campo indispensable o no parsear (fecha_hecho/cod_depto/cantidad)."
        )
    return notes


class DelincuenciaHomicidiosExtractor(BaseExtractor):
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
            raw_path = RAW_DIR / f"delincuencia_homicidios_{timestamp}.json"
            # Compacto (sin indent), mismo motivo que hurto a personas: ~345k filas.
            raw_bytes = json.dumps(rows, ensure_ascii=False).encode("utf-8")
            write_raw_snapshot_atomic(raw_path, raw_bytes)

            return ExtractionResult(
                dataset=DATASET_NAME,
                dataframe=df,
                source_name=SOURCE_NAME,
                source_url=SOURCE_URL,
                source_mode="live",
                source_detail=(
                    f"Socrata API, dataset m8fd-ahd9, paginado en bloques de {PAGE_SIZE} "
                    "ordenado por :id; filas repetidas agregadas por combinación única"
                ),
                reuse_policy=REUSE_POLICY,
                raw_snapshot_path=str(raw_path.relative_to(ROOT_DIR)),
                snapshot_hash=compute_sha256(raw_bytes),
                notes=notes,
            )
        except EXPECTED_FETCH_FAILURES as exc:
            df, excluded_rows, excluded_victims, skipped = _normalize(
                DELINCUENCIA_HOMICIDIOS_FALLBACK_DATA
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
        csv_path = STAGING_DIR / "delincuencia_homicidios.csv"
        metadata_path = STAGING_DIR / "delincuencia_homicidios.metadata.json"
        return write_staging_csv_atomic(
            result.dataframe, csv_path, metadata_path, result.to_staging_metadata()
        )


if __name__ == "__main__":
    extractor = DelincuenciaHomicidiosExtractor()
    outcome = extractor.run()
    print(f"[{DATASET_NAME}] source_mode={outcome.source_mode} rows={outcome.dataframe.height}")
