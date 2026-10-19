"""Extractor de lesiones personales por municipio y día, fuente Policía Nacional.

Fuente primaria: API Socrata de datos.gov.co, dataset "Reporte Lesiones
Personales y en Accidente de Tránsito Policía Nacional" (id `72sg-cybi`),
publicado por la Dirección General de la Policía Nacional (DIPON), licencia
CC BY-SA 4.0. Confirmado en vivo el 2026-10-19: 1381416 filas, 2010-01-01 a
2026-07-31, ~2.35 millones de víctimas.

https://www.datos.gov.co/resource/72sg-cybi

A diferencia de hurto a personas, la fuente trae dimensiones por hecho
(conducta del Código Penal, arma/medio, género y grupo etario de la víctima)
y un `codigo_dane` de 8 dígitos = municipio (5) + centro poblado (3, "000" =
cabecera). Decisión de alcance (confirmada por David, ver
docs/datasets/delincuencia_lesiones_personales.md):

- Se conservan todas las dimensiones, pero el centro poblado se colapsa a
  municipio: una fila por fecha + cod_mpio + conducta + arma_medio + genero
  + grupo_etario, con `cantidad` sumada. No existe hoy un dataset de centros
  poblados para hacer join con los 3 dígitos finales.
- Las lesiones culposas en accidente de tránsito (~un tercio de la fuente)
  se incluyen, con una columna derivada `tipo_lesion` (dolosa /
  culposa_transito / culposa_otra) para poder filtrarlas.

Notas de calidad de dato conocidas (2026-10-19):

- 4 filas traen `codigo_dane` = "00000000" (sin municipio). Se EXCLUYEN —
  no se fabrica un código — y el conteo queda en las `notes` de staging.
- ~20 filas traen un código que contradice el nombre de municipio y
  departamento de la misma fila (ej. `25754001` = Soacha, Cundinamarca, con
  municipio "Jamundí" / departamento "VALLE"). Se confía en el código (es la
  clave de join) y el nombre publicado por `cod_mpio` es el más frecuente en
  la fuente para ese código, no el de cada fila.
- Los nombres de capital de departamento vienen con sufijo " (CT)"
  ("Bucaramanga (CT)"); se quita en `nombre_mpio`.

Se invoca siempre como módulo, nunca como script suelto:
`python -m src.extractors.delincuencia_lesiones_personales_extractor` desde
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

DATASET_NAME = "delincuencia_lesiones_personales"
SOURCE_URL = "https://www.datos.gov.co/resource/72sg-cybi.json"
SOURCE_NAME = (
    "Policía Nacional (DIPON) — Lesiones personales y en accidente de tránsito (vía datos.gov.co)"
)

# 1381416 filas conocidas (2026-10-19). Paginado con `$order=:id` explícito,
# igual que hurto a personas: sin $order Socrata no garantiza un orden
# estable entre páginas.
PAGE_SIZE = 50_000
# Observado en vivo: ~3s por página de 50k filas (9 columnas cortas).
PAGE_TIMEOUT_SECONDS = 120
EXPECTED_MIN_ROWS = 1_300_000

# Código que la fuente usa cuando no hay municipio asignado.
CODIGO_SIN_MUNICIPIO = "00000"

REUSE_POLICY = ReusePolicy(
    status="open-attribution",
    license="CC BY-SA 4.0",
    license_url="https://www.datos.gov.co/resource/72sg-cybi",
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
# Filas reales observadas en la fuente (2026-10-19): incluye una capital con
# sufijo "(CT)", un centro poblado distinto de cabecera que se colapsa con
# su cabecera, una fila con `codigo_dane` "00000000" para ejercitar la
# exclusión, una con código y nombre contradictorios, y una sin género.
DELINCUENCIA_LESIONES_PERSONALES_FALLBACK_DATA: list[dict[str, Any]] = [
    {
        "departamento": "SANTANDER",
        "municipio": "Bucaramanga (CT)",
        "codigo_dane": "68001000",
        "armas_medios": "VEHICULO",
        "fecha_hecho": "23/02/2024",
        "genero": "FEMENINO",
        "grupo_etario": "ADULTOS",
        "descripci_n_conducta": "ARTÍCULO 120. LESIONES CULPOSAS ( EN ACCIDENTE DE TRANSITO )",
        "cantidad": "1",
    },
    {
        "departamento": "BOYACÁ",
        "municipio": "Nobsa",
        "codigo_dane": "15491000",
        "armas_medios": "VEHICULO",
        "fecha_hecho": "11/03/2024",
        "genero": "MASCULINO",
        "grupo_etario": "ADULTOS",
        "descripci_n_conducta": "ARTÍCULO 120. LESIONES CULPOSAS ( EN ACCIDENTE DE TRANSITO )",
        "cantidad": "1",
    },
    {
        "departamento": "BOLÍVAR",
        "municipio": "Cartagena (CT)",
        "codigo_dane": "13001000",
        "armas_medios": "CONTUNDENTES",
        "fecha_hecho": "05/03/2024",
        "genero": "MASCULINO",
        "grupo_etario": "ADULTOS",
        "descripci_n_conducta": "ARTÍCULO 111. LESIONES PERSONALES",
        "cantidad": "2",
    },
    {
        "departamento": "BOLÍVAR",
        "municipio": "Cartagena (CT)",
        "codigo_dane": "13001009",
        "armas_medios": "CONTUNDENTES",
        "fecha_hecho": "05/03/2024",
        "genero": "MASCULINO",
        "grupo_etario": "ADULTOS",
        "descripci_n_conducta": "ARTÍCULO 111. LESIONES PERSONALES",
        "cantidad": "1",
    },
    {
        "departamento": "ANTIOQUIA",
        "municipio": "Medellín (CT)",
        "codigo_dane": "05001000",
        "armas_medios": "ARMA BLANCA / CORTOPUNZANTE",
        "fecha_hecho": "14/03/2025",
        "genero": "FEMENINO",
        "grupo_etario": "ADOLESCENTES",
        "descripci_n_conducta": "ARTÍCULO 111. LESIONES PERSONALES",
        "cantidad": "1",
    },
    {
        "departamento": "ANTIOQUIA",
        "municipio": "Medellín (CT)",
        "codigo_dane": "05001000",
        "armas_medios": "SIN EMPLEO DE ARMAS",
        "fecha_hecho": "14/03/2025",
        "genero": None,
        "grupo_etario": "ADULTOS",
        "descripci_n_conducta": "ARTICULO 120 LESIONES CULPOSAS",
        "cantidad": "1",
    },
    {
        "departamento": "BOGOTA",
        "municipio": "Bogotá D.C. (CT)",
        "codigo_dane": "11001000",
        "armas_medios": "ACIDO",
        "fecha_hecho": "14/03/2025",
        "genero": "FEMENINO",
        "grupo_etario": "ADULTOS",
        "descripci_n_conducta": "ARTÍCULO 113. DEFORMIDAD",
        "cantidad": "1",
    },
    {
        "departamento": "CUNDINAMARCA",
        "municipio": "Soacha",
        "codigo_dane": "25754000",
        "armas_medios": "CONTUNDENTES",
        "fecha_hecho": "16/03/2016",
        "genero": "MASCULINO",
        "grupo_etario": "ADULTOS",
        "descripci_n_conducta": "ARTÍCULO 111. LESIONES PERSONALES",
        "cantidad": "3",
    },
    {
        "departamento": "CUNDINAMARCA",
        "municipio": "Soacha",
        "codigo_dane": "25754000",
        "armas_medios": "ARMA BLANCA / CORTOPUNZANTE",
        "fecha_hecho": "19/03/2016",
        "genero": "FEMENINO",
        "grupo_etario": "ADULTOS",
        "descripci_n_conducta": "ARTÍCULO 111. LESIONES PERSONALES",
        "cantidad": "1",
    },
    {
        "departamento": "VALLE",
        "municipio": "Jamundí",
        "codigo_dane": "25754001",
        "armas_medios": "CONTUNDENTES",
        "fecha_hecho": "19/03/2016",
        "genero": "MASCULINO",
        "grupo_etario": "ADULTOS",
        "descripci_n_conducta": "ARTÍCULO 111. LESIONES PERSONALES",
        "cantidad": "1",
    },
    {
        "departamento": "CUNDINAMARCA",
        "municipio": "Agua de Dios",
        "codigo_dane": "00000000",
        "armas_medios": "CONTUNDENTES",
        "fecha_hecho": "03/01/2010",
        "genero": "MASCULINO",
        "grupo_etario": "ADULTOS",
        "descripci_n_conducta": "ARTÍCULO 111. LESIONES PERSONALES",
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
    "descripci_n_conducta",
    "cantidad",
]

# Clave de agregación = clave primaria del dataset publicado.
PRIMARY_KEY = ["fecha", "cod_mpio", "conducta", "arma_medio", "genero", "grupo_etario"]

_OUTPUT_COLUMNS = [
    "fecha",
    "anio",
    "cod_dpto",
    "nombre_dpto",
    "cod_mpio",
    "nombre_mpio",
    "conducta",
    "tipo_lesion",
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
    "conducta": pl.Utf8,
    "tipo_lesion": pl.Utf8,
    "arma_medio": pl.Utf8,
    "genero": pl.Utf8,
    "grupo_etario": pl.Utf8,
    "cantidad": pl.Int64,
}

# Artículos del Código Penal (Ley 599 de 2000) observados en la fuente.
# 120 = lesiones culposas, 126 = lesiones culposas al feto; el resto
# (111-119, 125, 136) son modalidades dolosas. Un artículo nuevo que aparezca
# en la fuente queda con `tipo_lesion` nulo y el validador lo reporta.
_ARTICULOS_CULPOSOS = [120, 126]
_ARTICULOS_DOLOSOS = [111, 112, 113, 114, 115, 116, 117, 118, 119, 125, 136]


def _tipo_lesion_expr(conducta: pl.Expr) -> pl.Expr:
    articulo = conducta.str.extract(r"(?i)ART[IÍ]CULO\s+(\d+)").cast(pl.Int64, strict=False)
    return (
        pl.when(articulo.is_in(_ARTICULOS_CULPOSOS) & conducta.str.contains(r"(?i)TR[AÁ]NSITO"))
        .then(pl.lit("culposa_transito"))
        .when(articulo.is_in(_ARTICULOS_CULPOSOS))
        .then(pl.lit("culposa_otra"))
        .when(articulo.is_in(_ARTICULOS_DOLOSOS))
        .then(pl.lit("dolosa"))
        .otherwise(pl.lit(None, dtype=pl.Utf8))
    )


def _most_frequent(values: pl.Expr) -> pl.Expr:
    """Valor más frecuente de un grupo; desempata por orden alfabético para
    que el resultado sea determinista entre builds."""
    return values.drop_nulls().mode().sort().first()


def _normalize(rows: list[dict[str, Any]]) -> tuple[pl.DataFrame, int, int, int]:
    """Devuelve (df, filas_sin_municipio, victimas_sin_municipio,
    filas_descartadas_por_parseo). Vectorizado con Polars: la fuente tiene
    ~1.4 millones de filas."""
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
    excluded_victims = int(excluded["_cantidad"].fill_null(0).sum())

    valid = raw.filter(~sin_municipio)
    parseable = (
        pl.col("_fecha").is_not_null()
        & pl.col("_cantidad").is_not_null()
        & pl.col("descripci_n_conducta").is_not_null()
    )
    skipped = valid.filter(~parseable).height

    records = valid.filter(parseable).select(
        pl.col("_fecha").alias("fecha"),
        pl.col("_codigo").str.slice(0, 2).alias("cod_dpto"),
        pl.col("departamento").str.strip_chars().alias("nombre_dpto"),
        pl.col("_codigo").str.slice(0, 5).alias("cod_mpio"),
        pl.col("municipio").str.strip_chars().str.replace(r"\s*\(CT\)$", "").alias("nombre_mpio"),
        pl.col("descripci_n_conducta").str.strip_chars().alias("conducta"),
        pl.col("armas_medios").str.strip_chars().alias("arma_medio"),
        pl.col("genero").str.strip_chars().alias("genero"),
        pl.col("grupo_etario").str.strip_chars().alias("grupo_etario"),
        pl.col("_cantidad").alias("cantidad"),
    )

    # Un nombre por código (el más frecuente), no el de cada fila: unas
    # pocas filas de la fuente traen código y nombre contradictorios.
    nombres_mpio = records.group_by("cod_mpio").agg(_most_frequent(pl.col("nombre_mpio")))
    nombres_dpto = records.group_by("cod_dpto").agg(_most_frequent(pl.col("nombre_dpto")))

    df = (
        records.group_by(["cod_dpto", *PRIMARY_KEY])
        .agg(pl.col("cantidad").sum())
        .join(nombres_mpio, on="cod_mpio", how="left")
        .join(nombres_dpto, on="cod_dpto", how="left")
        .with_columns(
            pl.col("fecha").dt.year().cast(pl.Int64).alias("anio"),
            _tipo_lesion_expr(pl.col("conducta")).alias("tipo_lesion"),
        )
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
            "tener municipio en la fuente (codigo_dane ausente o '00000000'); ver "
            "docs/datasets/delincuencia_lesiones_personales.md."
        )
    if skipped > 0:
        notes.append(
            f"{skipped} filas se descartaron durante la normalización por faltarles "
            "un campo indispensable o no parsear (fecha_hecho/cantidad/descripci_n_conducta)."
        )
    return notes


class DelincuenciaLesionesPersonalesExtractor(BaseExtractor):
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
            raw_path = RAW_DIR / f"delincuencia_lesiones_personales_{timestamp}.json"
            # Compacto (sin indent), mismo motivo que hurto: ~1.4M filas.
            raw_bytes = json.dumps(rows, ensure_ascii=False).encode("utf-8")
            write_raw_snapshot_atomic(raw_path, raw_bytes)

            return ExtractionResult(
                dataset=DATASET_NAME,
                dataframe=df,
                source_name=SOURCE_NAME,
                source_url=SOURCE_URL,
                source_mode="live",
                source_detail=(
                    f"Socrata API, dataset 72sg-cybi, paginado en bloques de {PAGE_SIZE} "
                    "ordenado por :id; agregado de centro poblado a municipio"
                ),
                reuse_policy=REUSE_POLICY,
                raw_snapshot_path=str(raw_path.relative_to(ROOT_DIR)),
                snapshot_hash=compute_sha256(raw_bytes),
                notes=notes,
            )
        except EXPECTED_FETCH_FAILURES as exc:
            df, excluded_rows, excluded_victims, skipped = _normalize(
                DELINCUENCIA_LESIONES_PERSONALES_FALLBACK_DATA
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
        csv_path = STAGING_DIR / "delincuencia_lesiones_personales.csv"
        metadata_path = STAGING_DIR / "delincuencia_lesiones_personales.metadata.json"
        return write_staging_csv_atomic(
            result.dataframe, csv_path, metadata_path, result.to_staging_metadata()
        )


if __name__ == "__main__":
    extractor = DelincuenciaLesionesPersonalesExtractor()
    outcome = extractor.run()
    print(f"[{DATASET_NAME}] source_mode={outcome.source_mode} rows={outcome.dataframe.height}")
