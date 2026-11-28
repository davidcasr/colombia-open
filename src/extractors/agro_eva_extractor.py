"""Extractor de Evaluaciones Agropecuarias Municipales (EVA), fuentes UPRA
(2019-2025) y MinAgricultura (2006-2018).

Fuentes primarias, ambas vía API Socrata de datos.gov.co, licencia CC BY-SA
4.0:

- UPRA — "Evaluaciones Agropecuarias Municipales - EVA. 2019 - 2025. Base
  Agrícola" (id `uejq-wxrr`). Confirmado en vivo el 2026-11-27: 166732
  filas, años 2019-2025, actualizado recientemente (serie viva).
  https://www.datos.gov.co/resource/uejq-wxrr.json
- MinAgricultura — "Evaluaciones Agropecuarias Municipales EVA" (id
  `2pnw-mmge`). Confirmado en vivo el 2026-11-27: 206068 filas, años
  **2006**-2018 (el roadmap documentaba "2007-2018"; corregido tras
  verificar en vivo — hay filas de 2006). Sin actualizar desde 2019-11
  (`rowsUpdatedAt` del recurso): es una serie cerrada, continuada por UPRA
  desde 2019. https://www.datos.gov.co/resource/2pnw-mmge.json

**Decisión de alcance — por qué se mezclan dos fuentes en un solo
extractor.** Ambas series cubren el mismo fenómeno (evaluaciones
agropecuarias municipales) sin solaparse en años (2006-2018 vs. 2019-2025:
confirmado en vivo, sin filas duplicadas), pero con **esquemas de columnas
distintos** para los mismos conceptos (p. ej. `c_digo_dane_municipio` vs.
`c_d_mun`, `rea_sembrada` vs. `rea_sembrada_ha`). Publicarlas como un solo
dataset con un esquema común es curación, no fabricación de dato: cada fila
se etiqueta con `serie_fuente` para que quede auditable de cuál API vino.

**Defecto de la fuente MinAgricultura (2006-2018), no de este extractor**:
`c_d_dep`/`c_d_mun` están tipados como `number` en Socrata (confirmado en
vivo: Antioquia llega como `"5"`, Atlántico como `"8"`, nunca `"05"`/`"08"`)
— el bug clásico de "se comió el cero inicial" que `.claude/rules/
validation.md` documenta. Se corrige con `.zfill()` en la normalización,
igual que cualquier otro código administrativo del proyecto. La serie UPRA
(2019-2025) ya trae el código completo como string (`"05001"`).

Ninguna de las dos series reporta Bogotá, D.C. (`cod_dpto` 11) — 32 de 33
departamentos en ambas series, confirmado en vivo. No es un bug del
extractor: Bogotá no tiene área rural dentro de su división política para
reportar a EVA.

`codigo_cultivo` solo existe en la serie UPRA — queda `null` para filas de
la serie MinAgricultura (no se fabrica un código inexistente).

`rendimiento_t_ha` no es obligatorio: cuando no se cosechó nada
(`area_cosechada_ha` = 0), MinAgricultura omite el campo (3433 filas,
confirmado en vivo 2026-11-27 — Socrata no emite claves nulas) mientras
UPRA publica "0.00". Esas filas son pérdida de cosecha real y se conservan
con rendimiento nulo — no se imputa 0 para emparejar la convención de UPRA.

Se invoca siempre como módulo, nunca como script suelto:
`python -m src.extractors.agro_eva_extractor` desde la raíz del repo. Ver
`.claude/rules/extractors.md` §6.
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

DATASET_NAME = "agro_eva"

# El dataset combina dos recursos; SOURCE_URL es el de la serie viva (UPRA).
# Debe ser un literal: scripts/check_source_urls.py lo lee con `ast`.
SOURCE_URL = "https://www.datos.gov.co/resource/uejq-wxrr.json"
SOURCE_URL_UPRA = SOURCE_URL
SOURCE_URL_MINAGRICULTURA = "https://www.datos.gov.co/resource/2pnw-mmge.json"
SOURCE_NAME = (
    "UPRA (2019-2025) / MinAgricultura (2006-2018) — Evaluaciones "
    "Agropecuarias Municipales (EVA), vía datos.gov.co"
)

SERIE_UPRA = "upra_2019_2025"
SERIE_MINAGRICULTURA = "minagricultura_2006_2018"

# 166732 (UPRA) + 206068 (MinAgricultura) filas conocidas (2026-11-27).
# Paginado igual que delincuencia_hurto_personas: $order=:id explícito,
# Socrata no garantiza orden estable entre páginas sin él.
PAGE_SIZE = 50_000
PAGE_TIMEOUT_SECONDS = 120
EXPECTED_MIN_ROWS_UPRA = 150_000
EXPECTED_MIN_ROWS_MINAGRICULTURA = 190_000

REUSE_POLICY = ReusePolicy(
    status="open-attribution",
    license="CC BY-SA 4.0",
    license_url="https://www.datos.gov.co/resource/uejq-wxrr",
    attribution_required=True,
    redistribution_ok=True,
    summary=(
        "Datos oficiales de la Unidad de Planificación de Tierras Rurales "
        "(UPRA, serie 2019-2025) y del Ministerio de Agricultura y "
        "Desarrollo Rural (MinAgricultura, serie 2006-2018) publicados en "
        "datos.gov.co bajo CC BY-SA 4.0 (share-alike): redistribuir con "
        "atribución a la entidad de origen de cada fila (ver columna "
        "`serie_fuente`) y bajo la misma licencia. Ver "
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

UPRA_COLUMN_MAP: dict[str, str | None] = {
    "cod_dpto": "c_digo_dane_departamento",
    "nombre_dpto": "departamento",
    "cod_mpio": "c_digo_dane_municipio",
    "nombre_mpio": "municipio",
    "grupo_cultivo": "grupo_cultivo",
    "subgrupo_cultivo": "subgrupo",
    "cultivo": "cultivo",
    "desagregacion_cultivo": "desagregaci_n_cultivo",
    "anio": "a_o",
    "periodo": "periodo",
    "area_sembrada_ha": "rea_sembrada",
    "area_cosechada_ha": "rea_cosechada",
    "produccion_t": "producci_n",
    "rendimiento_t_ha": "rendimiento",
    "ciclo_cultivo": "ciclo_del_cultivo",
    "estado_fisico_cultivo": "estado_f_sico_del_cultivo",
    "codigo_cultivo": "c_digo_del_cultivo",
    "nombre_cientifico_cultivo": "nombre_cient_fico_del_cultivo",
}

MINAGRICULTURA_COLUMN_MAP: dict[str, str | None] = {
    "cod_dpto": "c_d_dep",
    "nombre_dpto": "departamento",
    "cod_mpio": "c_d_mun",
    "nombre_mpio": "municipio",
    "grupo_cultivo": "grupo_de_cultivo",
    "subgrupo_cultivo": "subgrupo_de_cultivo",
    "cultivo": "cultivo",
    "desagregacion_cultivo": "desagregaci_n_regional_y",
    "anio": "a_o",
    "periodo": "periodo",
    "area_sembrada_ha": "rea_sembrada_ha",
    "area_cosechada_ha": "rea_cosechada_ha",
    "produccion_t": "producci_n_t",
    "rendimiento_t_ha": "rendimiento_t_ha",
    "ciclo_cultivo": "ciclo_de_cultivo",
    "estado_fisico_cultivo": "estado_fisico_produccion",
    "codigo_cultivo": None,  # no existe en la serie MinAgricultura
    "nombre_cientifico_cultivo": "nombre_cientifico",
}

_SCHEMA = {
    "cod_dpto": pl.Utf8,
    "nombre_dpto": pl.Utf8,
    "cod_mpio": pl.Utf8,
    "nombre_mpio": pl.Utf8,
    "grupo_cultivo": pl.Utf8,
    "subgrupo_cultivo": pl.Utf8,
    "cultivo": pl.Utf8,
    "desagregacion_cultivo": pl.Utf8,
    "anio": pl.Int32,
    "periodo": pl.Utf8,
    "area_sembrada_ha": pl.Float64,
    "area_cosechada_ha": pl.Float64,
    "produccion_t": pl.Float64,
    "rendimiento_t_ha": pl.Float64,
    "ciclo_cultivo": pl.Utf8,
    "estado_fisico_cultivo": pl.Utf8,
    "codigo_cultivo": pl.Utf8,
    "nombre_cientifico_cultivo": pl.Utf8,
    "serie_fuente": pl.Utf8,
}

# Fallback mínimo para desarrollo offline / CI sin red. NUNCA se publica.
# Filas reales observadas en cada fuente (2026-11-27), en la forma cruda
# exacta de cada API — ejercita el merge de dos esquemas distintos incluso
# offline. Incluye el caso real de MinAgricultura sin cero inicial en
# `c_d_dep`/`c_d_mun` (Antioquia "5", no "05").
AGRO_EVA_UPRA_FALLBACK_DATA: list[dict[str, Any]] = [
    {
        "c_digo_dane_departamento": "05",
        "departamento": "Antioquia",
        "c_digo_dane_municipio": "05001",
        "municipio": "Medellín",
        "grupo_cultivo": "Hortalizas",
        "subgrupo": "Hortalizas de tallo",
        "cultivo": "Apio",
        "desagregaci_n_cultivo": "Apio",
        "a_o": "2021",
        "periodo": "2021A",
        "rea_sembrada": "8.00",
        "rea_cosechada": "8.00",
        "producci_n": "128.00",
        "rendimiento": "16.00",
        "ciclo_del_cultivo": "Transitorio",
        "estado_f_sico_del_cultivo": "En fresco",
        "c_digo_del_cultivo": "1050600",
        "nombre_cient_fico_del_cultivo": "Apium graveolens",
    },
    {
        "c_digo_dane_departamento": "76",
        "departamento": "Valle del Cauca",
        "c_digo_dane_municipio": "76001",
        "municipio": "Santiago de Cali",
        "grupo_cultivo": "Hortalizas",
        "subgrupo": "Hortalizas de hoja",
        "cultivo": "Acelga",
        "desagregaci_n_cultivo": "Acelga",
        "a_o": "2019",
        "periodo": "2019A",
        "rea_sembrada": "3.00",
        "rea_cosechada": "3.00",
        "producci_n": "12.00",
        "rendimiento": "4.00",
        "ciclo_del_cultivo": "Transitorio",
        "estado_f_sico_del_cultivo": "En fresco",
        "c_digo_del_cultivo": "1050100",
        "nombre_cient_fico_del_cultivo": "Beta vulgaris var. cicla",
    },
    {
        "c_digo_dane_departamento": "05",
        "departamento": "Antioquia",
        "c_digo_dane_municipio": "05001",
        "municipio": "Medellín",
        "grupo_cultivo": "Hortalizas",
        "subgrupo": "Hortalizas de tallo",
        "cultivo": "Apio",
        "desagregaci_n_cultivo": "Apio",
        "a_o": "2022",
        "periodo": "2022A",
        "rea_sembrada": "8.00",
        "rea_cosechada": "8.00",
        "producci_n": "127.44",
        "rendimiento": "15.93",
        "ciclo_del_cultivo": "Transitorio",
        "estado_f_sico_del_cultivo": "En fresco",
        "c_digo_del_cultivo": "1050600",
        "nombre_cient_fico_del_cultivo": "Apium graveolens",
    },
]

AGRO_EVA_MINAGRICULTURA_FALLBACK_DATA: list[dict[str, Any]] = [
    {
        # Antioquia sin cero inicial ("5", no "05") — defecto real de la
        # fuente, confirmado en vivo. El extractor lo corrige con zfill.
        "c_d_dep": "5",
        "departamento": "ANTIOQUIA",
        "c_d_mun": "5440",
        "municipio": "MARINILLA",
        "grupo_de_cultivo": "HORTALIZAS",
        "subgrupo_de_cultivo": "ACELGA",
        "cultivo": "ACELGA",
        "desagregaci_n_regional_y": "ACELGA",
        "a_o": "2016",
        "periodo": "2016A",
        "rea_sembrada_ha": "11",
        "rea_cosechada_ha": "11",
        "producci_n_t": "297",
        "rendimiento_t_ha": "27.00",
        "estado_fisico_produccion": "FRUTO FRESCO",
        "nombre_cientifico": "BETA VULGARIS",
        "ciclo_de_cultivo": "TRANSITORIO",
    },
    {
        "c_d_dep": "25",
        "departamento": "CUNDINAMARCA",
        "c_d_mun": "25754",
        "municipio": "SOACHA",
        "grupo_de_cultivo": "HORTALIZAS",
        "subgrupo_de_cultivo": "ACELGA",
        "cultivo": "ACELGA",
        "desagregaci_n_regional_y": "ACELGA",
        "a_o": "2006",
        "periodo": "2006B",
        "rea_sembrada_ha": "82",
        "rea_cosechada_ha": "80",
        "producci_n_t": "1440",
        "rendimiento_t_ha": "18.00",
        "estado_fisico_produccion": "FRUTO FRESCO",
        "nombre_cientifico": "BETA VULGARIS",
        "ciclo_de_cultivo": "TRANSITORIO",
    },
    {
        "c_d_dep": "8",
        "departamento": "ATLANTICO",
        "c_d_mun": "8001",
        "municipio": "BARRANQUILLA",
        "grupo_de_cultivo": "FIBRAS",
        "subgrupo_de_cultivo": "ALGODON",
        "cultivo": "ALGODON",
        "desagregaci_n_regional_y": "ALGODON",
        "a_o": "2007",
        "periodo": "2007B",
        "rea_sembrada_ha": "16",
        "rea_cosechada_ha": "16",
        "producci_n_t": "44",
        "rendimiento_t_ha": "2.82",
        "estado_fisico_produccion": "SEMILLA",
        "nombre_cientifico": "GOSSYPIUM HIRSTIUM",
        "ciclo_de_cultivo": "TRANSITORIO",
    },
]


def _normalize_series(
    rows: list[dict[str, Any]], column_map: dict[str, str | None], serie_fuente: str
) -> tuple[pl.DataFrame, int]:
    """Renombra las columnas de una serie a un esquema común y castea tipos.

    Devuelve (df, filas_descartadas_por_parseo). Vectorizado con Polars,
    igual criterio que rethus_extractor._normalize: una fila a la que le
    falta un campo indispensable o no parsea se cuenta en `skipped`, nunca
    se fabrica ni revienta el build."""
    if not rows:
        return pl.DataFrame(schema=_SCHEMA), 0

    source_columns = [col for col in column_map.values() if col is not None]
    raw = pl.DataFrame(rows, schema=dict.fromkeys(source_columns, pl.Utf8))

    renamed = raw.select(
        [
            (pl.col(source_col).alias(target) if source_col else pl.lit(None).alias(target))
            for target, source_col in column_map.items()
        ]
    ).with_columns(pl.lit(serie_fuente).alias("serie_fuente"))

    parsed = renamed.with_columns(
        pl.col("cod_dpto").cast(pl.Utf8).str.strip_chars().str.zfill(2),
        pl.col("cod_mpio").cast(pl.Utf8).str.strip_chars().str.zfill(5),
        pl.col("nombre_dpto").cast(pl.Utf8).str.strip_chars(),
        pl.col("nombre_mpio").cast(pl.Utf8).str.strip_chars(),
        pl.col("grupo_cultivo").cast(pl.Utf8).str.strip_chars(),
        pl.col("subgrupo_cultivo").cast(pl.Utf8).str.strip_chars(),
        pl.col("cultivo").cast(pl.Utf8).str.strip_chars(),
        pl.col("desagregacion_cultivo").cast(pl.Utf8).str.strip_chars(),
        pl.col("anio").cast(pl.Int32, strict=False),
        pl.col("periodo").cast(pl.Utf8).str.strip_chars(),
        pl.col("area_sembrada_ha").cast(pl.Float64, strict=False),
        pl.col("area_cosechada_ha").cast(pl.Float64, strict=False),
        pl.col("produccion_t").cast(pl.Float64, strict=False),
        pl.col("rendimiento_t_ha").cast(pl.Float64, strict=False),
        pl.col("ciclo_cultivo").cast(pl.Utf8).str.strip_chars(),
        pl.col("estado_fisico_cultivo").cast(pl.Utf8).str.strip_chars(),
        pl.col("codigo_cultivo").cast(pl.Utf8).str.strip_chars(),
        pl.col("nombre_cientifico_cultivo").cast(pl.Utf8).str.strip_chars(),
    )

    required = (
        pl.col("cod_dpto").is_not_null()
        & pl.col("cod_mpio").is_not_null()
        & pl.col("cultivo").is_not_null()
        & pl.col("periodo").is_not_null()
        & pl.col("anio").is_not_null()
        & pl.col("area_sembrada_ha").is_not_null()
        & pl.col("area_cosechada_ha").is_not_null()
        & pl.col("produccion_t").is_not_null()
    )
    skipped = parsed.filter(~required).height
    valid = parsed.filter(required).select(list(_SCHEMA.keys())).cast(_SCHEMA)  # type: ignore[arg-type]
    return valid, skipped


def _normalize(
    rows_upra: list[dict[str, Any]], rows_minagricultura: list[dict[str, Any]]
) -> tuple[pl.DataFrame, int, int]:
    """Normaliza y une las dos series. Devuelve (df, skipped_upra, skipped_minagricultura)."""
    df_upra, skipped_upra = _normalize_series(rows_upra, UPRA_COLUMN_MAP, SERIE_UPRA)
    df_minagricultura, skipped_minagricultura = _normalize_series(
        rows_minagricultura, MINAGRICULTURA_COLUMN_MAP, SERIE_MINAGRICULTURA
    )
    combined = pl.concat([df_upra, df_minagricultura]).sort(
        ["cod_mpio", "anio", "cultivo", "periodo"]
    )
    return combined, skipped_upra, skipped_minagricultura


def _fetch_all_rows(source_url: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        page = get_json(
            source_url,
            params={"$limit": PAGE_SIZE, "$offset": offset, "$order": ":id"},
            timeout=PAGE_TIMEOUT_SECONDS,
        )
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return rows


def _normalization_notes(skipped_upra: int, skipped_minagricultura: int) -> list[str]:
    notes: list[str] = []
    if skipped_upra > 0:
        notes.append(
            f"{skipped_upra} filas de la serie UPRA (2019-2025) se descartaron durante "
            "la normalización por faltarles un campo indispensable o no parsear."
        )
    if skipped_minagricultura > 0:
        notes.append(
            f"{skipped_minagricultura} filas de la serie MinAgricultura (2006-2018) se "
            "descartaron durante la normalización por faltarles un campo indispensable "
            "o no parsear."
        )
    return notes


class AgroEvaExtractor(BaseExtractor):
    @property
    def dataset_name(self) -> str:
        return DATASET_NAME

    def fetch(self, **kwargs: Any) -> ExtractionResult:
        notes: list[str] = [
            "Dataset combinado de dos fuentes con esquemas distintos: UPRA "
            "(2019-2025) y MinAgricultura (2006-2018), sin solape de años. "
            "Ver columna `serie_fuente` para auditar el origen de cada fila."
        ]
        try:
            rows_upra = _fetch_all_rows(SOURCE_URL_UPRA)
            rows_minagricultura = _fetch_all_rows(SOURCE_URL_MINAGRICULTURA)

            if len(rows_upra) < EXPECTED_MIN_ROWS_UPRA:
                notes.append(
                    f"La serie UPRA devolvió solo {len(rows_upra)} filas, menos de las "
                    f"{EXPECTED_MIN_ROWS_UPRA} esperadas como mínimo."
                )
            if len(rows_minagricultura) < EXPECTED_MIN_ROWS_MINAGRICULTURA:
                notes.append(
                    f"La serie MinAgricultura devolvió solo {len(rows_minagricultura)} filas, "
                    f"menos de las {EXPECTED_MIN_ROWS_MINAGRICULTURA} esperadas como mínimo."
                )

            df, skipped_upra, skipped_minagricultura = _normalize(rows_upra, rows_minagricultura)
            notes.extend(_normalization_notes(skipped_upra, skipped_minagricultura))

            ensure_staging_directories()
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            raw_path = RAW_DIR / f"agro_eva_{timestamp}.json"
            # Un solo snapshot crudo que embebe las dos respuestas de API
            # completas, separadas por clave — ambas son el insumo exacto de
            # esta extracción. Compacto (sin indent): ~370k filas combinadas.
            raw_payload = {
                SERIE_UPRA: rows_upra,
                SERIE_MINAGRICULTURA: rows_minagricultura,
            }
            raw_bytes = json.dumps(raw_payload, ensure_ascii=False).encode("utf-8")
            write_raw_snapshot_atomic(raw_path, raw_bytes)

            return ExtractionResult(
                dataset=DATASET_NAME,
                dataframe=df,
                source_name=SOURCE_NAME,
                source_url=SOURCE_URL,
                source_mode="live",
                source_detail=(
                    f"Socrata API, datasets uejq-wxrr (UPRA) y 2pnw-mmge (MinAgricultura), "
                    f"cada uno paginado en bloques de {PAGE_SIZE} ordenado por :id"
                ),
                reuse_policy=REUSE_POLICY,
                raw_snapshot_path=str(raw_path.relative_to(ROOT_DIR)),
                snapshot_hash=compute_sha256(raw_bytes),
                notes=notes,
            )
        except EXPECTED_FETCH_FAILURES as exc:
            df, _skipped_upra, _skipped_minagricultura = _normalize(
                AGRO_EVA_UPRA_FALLBACK_DATA, AGRO_EVA_MINAGRICULTURA_FALLBACK_DATA
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
                    "NO se publica."
                ],
            )

    def write_staging(self, result: ExtractionResult) -> Path:
        ensure_staging_directories()
        csv_path = STAGING_DIR / "agro_eva.csv"
        metadata_path = STAGING_DIR / "agro_eva.metadata.json"
        return write_staging_csv_atomic(
            result.dataframe, csv_path, metadata_path, result.to_staging_metadata()
        )


if __name__ == "__main__":
    extractor = AgroEvaExtractor()
    outcome = extractor.run()
    print(f"[{DATASET_NAME}] source_mode={outcome.source_mode} rows={outcome.dataframe.height}")
