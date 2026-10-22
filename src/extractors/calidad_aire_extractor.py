"""Extractor de calidad del aire por estación de monitoreo, fuente IDEAM.

Fuente primaria: API Socrata de datos.gov.co, dataset "Calidad del Aire en
Colombia (Promedio Anual)" (id `kekd-7v7h`), publicado por el Instituto de
Hidrología, Meteorología y Estudios Ambientales (IDEAM), licencia CC BY-SA
4.0. Confirmado en vivo el 2026-10-22: 30665 filas, 2011-2025, 513
estaciones, 344 municipios — reemplaza la pista vieja de SISAIRE (sin API
pública encontrada, ver `docs/roadmap/roadmap.md`).

https://www.datos.gov.co/resource/kekd-7v7h.json

Decisión de alcance: la fuente mezcla 20 "variable" distintas — 6
contaminantes reales (los que usa el Índice de Calidad del Aire (ICA) de
Colombia, Resolución 2254 de 2017: PM10, PM2.5, SO2, O3, NO2, CO) y 14
variables meteorológicas (temperatura, humedad, viento, lluvia,
radiación) más PST (partículas suspendidas totales, métrica legacy
superada por PM10/PM2.5) y NO (precursor de NO2, no es un contaminante ICA
por sí mismo). **Se publican solo los 6 contaminantes ICA** — las
meteorológicas y PST/NO quedan fuera de esta primera iteración
(documentado, no implementado especulativamente).

Granularidad: una fila por estación + contaminante + ventana de exposición
(`tiempo_exposicion_horas` — la fuente trae más de una ventana por
contaminante, ej. PM10 a 1h y a 24h) + año. **No se colapsa a una sola
ventana por contaminante** — se publican todas tal como la fuente las
reporta; quien necesite el valor "oficial" ICA filtra por la ventana
estándar de ese contaminante (24h para PM10/PM2.5/SO2, 8h para O3/CO, 1h
para NO2).

Nota de calidad de dato — la fuente trae la MISMA fila publicada dos
veces para ~6300 de las ~15600 combinaciones estación+contaminante+
ventana+año (confirmado en vivo el 2026-10-22 contra la respuesta HTTP
cruda, no es un artefacto de este extractor): casi siempre con el mismo
valor pero formateado distinto (ej. `c_digo_del_municipio` "68001" en una
copia y "68001.0" en la otra — de ahí también la inconsistencia de
mayúsculas en los nombres, ver abajo). En ~1% de esos pares (56 de 6306)
el `promedio` reportado en cada copia además DIFIERE genuinamente, no solo
el formato. Se colapsa a una fila por `PRIMARY_KEY` con el promedio de las
copias (nunca se descarta el dato ni se fabrica un tercer valor) y se
reporta el conteo de grupos colapsados en las notas de staging.

Se invoca siempre como módulo, nunca como script suelto:
`python -m src.extractors.calidad_aire_extractor` desde la raíz del repo.
Ver `.claude/rules/extractors.md` §6.
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

DATASET_NAME = "calidad_aire"
SOURCE_URL = "https://www.datos.gov.co/resource/kekd-7v7h.json"
SOURCE_NAME = "IDEAM — Calidad del Aire en Colombia (Promedio Anual), vía datos.gov.co"

# Los 6 contaminantes del Índice de Calidad del Aire (ICA) colombiano —
# ver docstring del módulo. El filtro se aplica server-side (`$where`) para
# no descargar las 14 variables meteorológicas que no se publican.
CONTAMINANTES_ICA = ["PM10", "PM2.5", "SO2", "O3", "NO2", "CO"]

# 15625 filas conocidas tras filtrar a los 6 contaminantes (2026-10-22) —
# caben en un solo request, sin necesidad de paginar.
FETCH_LIMIT = 30_000
FETCH_TIMEOUT_SECONDS = 60
EXPECTED_MIN_ROWS = 14_000

PRIMARY_KEY = ["id_estacion", "contaminante", "tiempo_exposicion_horas", "anio"]

REUSE_POLICY = ReusePolicy(
    status="open-attribution",
    license="CC BY-SA 4.0",
    license_url="https://www.datos.gov.co/resource/kekd-7v7h",
    attribution_required=True,
    redistribution_ok=True,
    summary=(
        "Datos oficiales del Instituto de Hidrología, Meteorología y "
        "Estudios Ambientales (IDEAM) publicados en datos.gov.co bajo CC "
        "BY-SA 4.0 (share-alike): redistribuir con atribución al IDEAM y "
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
# Fila real observada en la fuente (2026-10-22) más 3 variantes reales de
# otras estaciones/contaminantes/ventanas, y una sin cod_mpio (defecto real
# de la fuente, 2 de 15625 filas) para ejercitar la exclusión.
CALIDAD_AIRE_FALLBACK_DATA: list[dict[str, Any]] = [
    {
        "id_estacion": "9049",
        "estaci_n": "ZM11 MINGUILLO",
        "autoridad_ambiental": "CORPOCESAR",
        "tipo_de_estaci_n": "Fija",
        "latitud": "9.940778",
        "longitud": "-73.500592",
        "variable": "PM10",
        "unidades": "ugm3",
        "tiempo_de_exposici_n_horas": "24",
        "a_o": "2011",
        "promedio": "17.5",
        "mediana": "17.9",
        "m_ximo": "37.5",
        "no_de_datos": "65",
        "representatividad_temporal": "53.0",
        "d_as_de_excedencias": "0",
        "porcentaje_excedencias_limite": "0.0",
        "c_digo_del_departamento": "20",
        "nombre_del_departamento": "CESAR",
        "c_digo_del_municipio": "20621.0",
        "nombre_del_municipio": "LA PAZ",
    },
    {
        "id_estacion": "9020",
        "estaci_n": "I.E. COL. COLOMBIA",
        "autoridad_ambiental": "AMVA",
        "tipo_de_estaci_n": "Fija",
        "latitud": "6.378517",
        "longitud": "-75.443986",
        "variable": "PM2.5",
        "unidades": "ugm3",
        "tiempo_de_exposici_n_horas": "24",
        "a_o": "2022",
        "promedio": "14.2",
        "mediana": "13.8",
        "m_ximo": "41.0",
        "no_de_datos": "312",
        "representatividad_temporal": "85.0",
        "d_as_de_excedencias": "3",
        "porcentaje_excedencias_limite": "1.0",
        "c_digo_del_departamento": "5",
        "nombre_del_departamento": "ANTIOQUIA",
        "c_digo_del_municipio": "5308.0",
        "nombre_del_municipio": "GIRARDOTA",
    },
    {
        "id_estacion": "9020",
        "estaci_n": "I.E. COL. COLOMBIA",
        "autoridad_ambiental": "AMVA",
        "tipo_de_estaci_n": "Fija",
        "latitud": "6.378517",
        "longitud": "-75.443986",
        "variable": "O3",
        "unidades": "ugm3",
        "tiempo_de_exposici_n_horas": "8",
        "a_o": "2022",
        "promedio": "28.4",
        "mediana": "27.1",
        "m_ximo": "95.3",
        "no_de_datos": "298",
        "representatividad_temporal": "81.0",
        "d_as_de_excedencias": "0",
        "porcentaje_excedencias_limite": "0.0",
        "c_digo_del_departamento": "5",
        "nombre_del_departamento": "ANTIOQUIA",
        "c_digo_del_municipio": "5001",
        "nombre_del_municipio": "MEDELLIN",
    },
    {
        # Defecto real de la fuente: 2 de 15625 filas no traen código de
        # municipio — se excluye, no se fabrica un valor de reemplazo.
        "id_estacion": "9999",
        "estaci_n": "ESTACION SIN MUNICIPIO ASIGNADO",
        "autoridad_ambiental": "DESCONOCIDA",
        "tipo_de_estaci_n": "Fija",
        "latitud": "4.0",
        "longitud": "-74.0",
        "variable": "NO2",
        "unidades": "ugm3",
        "tiempo_de_exposici_n_horas": "1",
        "a_o": "2020",
        "promedio": "10.0",
        "no_de_datos": "10",
    },
]

_OUTPUT_COLUMNS = [
    "id_estacion",
    "nombre_estacion",
    "autoridad_ambiental",
    "tipo_estacion",
    "cod_dpto",
    "nombre_dpto",
    "cod_mpio",
    "nombre_mpio",
    "latitud",
    "longitud",
    "anio",
    "contaminante",
    "tiempo_exposicion_horas",
    "unidad",
    "promedio",
    "mediana",
    "maximo",
    "no_de_datos",
    "representatividad_temporal",
    "dias_excedencia",
    "porcentaje_excedencia",
]

_SCHEMA = {
    "id_estacion": pl.Utf8,
    "nombre_estacion": pl.Utf8,
    "autoridad_ambiental": pl.Utf8,
    "tipo_estacion": pl.Utf8,
    "cod_dpto": pl.Utf8,
    "nombre_dpto": pl.Utf8,
    "cod_mpio": pl.Utf8,
    "nombre_mpio": pl.Utf8,
    "latitud": pl.Float64,
    "longitud": pl.Float64,
    "anio": pl.Int64,
    "contaminante": pl.Utf8,
    "tiempo_exposicion_horas": pl.Int64,
    "unidad": pl.Utf8,
    "promedio": pl.Float64,
    "mediana": pl.Float64,
    "maximo": pl.Float64,
    "no_de_datos": pl.Int64,
    "representatividad_temporal": pl.Float64,
    "dias_excedencia": pl.Int64,
    "porcentaje_excedencia": pl.Float64,
}


def _parse_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _parse_int(value: Any) -> int | None:
    parsed = _parse_float(value)
    return None if parsed is None else int(parsed)


def _parse_cod(value: Any, width: int) -> str | None:
    """Socrata entrega el código a veces como '5308.0' y a veces como
    '5308' — nunca lanza, devuelve None si no es parseable."""
    parsed = _parse_int(value)
    return None if parsed is None else str(parsed).zfill(width)


def _build_record(row: dict[str, Any]) -> dict[str, Any]:
    """Puede lanzar (KeyError/ValueError/TypeError) si a esta fila le falta
    `variable`/`a_o`/`id_estacion`. `_normalize()` lo atrapa por fila."""
    return {
        "id_estacion": str(row["id_estacion"]),
        "nombre_estacion": row.get("estaci_n"),
        "autoridad_ambiental": row.get("autoridad_ambiental"),
        "tipo_estacion": row.get("tipo_de_estaci_n"),
        "cod_dpto": _parse_cod(row.get("c_digo_del_departamento"), 2),
        "nombre_dpto": row.get("nombre_del_departamento"),
        "cod_mpio": _parse_cod(row.get("c_digo_del_municipio"), 5),
        "nombre_mpio": row.get("nombre_del_municipio"),
        "latitud": _parse_float(row.get("latitud")),
        "longitud": _parse_float(row.get("longitud")),
        "anio": int(row["a_o"]),
        "contaminante": row["variable"],
        "tiempo_exposicion_horas": _parse_int(row.get("tiempo_de_exposici_n_horas")),
        "unidad": row.get("unidades"),
        "promedio": _parse_float(row.get("promedio")),
        "mediana": _parse_float(row.get("mediana")),
        "maximo": _parse_float(row.get("m_ximo")),
        "no_de_datos": _parse_int(row.get("no_de_datos")),
        "representatividad_temporal": _parse_float(row.get("representatividad_temporal")),
        "dias_excedencia": _parse_int(row.get("d_as_de_excedencias")),
        "porcentaje_excedencia": _parse_float(row.get("porcentaje_excedencias_limite")),
    }


def _most_frequent(values: pl.Expr) -> pl.Expr:
    """Valor más frecuente de un grupo; desempata por orden alfabético para
    que el resultado sea determinista entre builds. Confirmado en vivo el
    2026-10-22: `nombre_del_departamento`/`nombre_del_municipio` traen
    mayúsculas inconsistentes para el MISMO código (ej. "ANTIOQUIA" en 207
    filas y "Antioquia" en 73 — 20 de 33 departamentos y 103 municipios
    afectados). Sin esto, agrupar por nombre (en vez de por código) separa
    el mismo departamento/municipio en varias filas — mismo patrón que los
    extractores de delincuencia."""
    return values.drop_nulls().mode().sort().first()


def _normalize(rows: list[dict[str, Any]]) -> tuple[pl.DataFrame, int, int, int]:
    """Devuelve (df, filas_sin_municipio, filas_descartadas_por_parseo,
    grupos_de_primary_key_colapsados). Ver docstring del módulo: la fuente
    publica la misma fila dos veces para buena parte de las combinaciones
    estación+contaminante+ventana+año — se colapsa a una fila por
    `PRIMARY_KEY` con el promedio de las copias, nunca se fabrica un
    tercer valor ni se descarta el grupo."""
    records: list[dict[str, Any]] = []
    excluded = 0
    skipped = 0
    for row in rows:
        try:
            record = _build_record(row)
        except (KeyError, ValueError, TypeError):
            skipped += 1
            continue
        if record["cod_mpio"] is None:
            excluded += 1
            continue
        records.append(record)
    raw = pl.DataFrame(records, schema=_SCHEMA)
    total_rows = raw.height

    # Paso 1: colapsar la fila duplicada (misma PRIMARY_KEY publicada dos
    # veces, ver docstring del módulo). cod_dpto/cod_mpio/nombre_estacion/
    # autoridad_ambiental/tipo_estacion deberían ser constantes por
    # estación — most_frequent es solo defensivo contra ruido puntual.
    collapsed = (
        raw.group_by(PRIMARY_KEY)
        .agg(
            _most_frequent(pl.col("nombre_estacion")).alias("nombre_estacion"),
            _most_frequent(pl.col("autoridad_ambiental")).alias("autoridad_ambiental"),
            _most_frequent(pl.col("tipo_estacion")).alias("tipo_estacion"),
            _most_frequent(pl.col("cod_dpto")).alias("cod_dpto"),
            _most_frequent(pl.col("cod_mpio")).alias("cod_mpio"),
            pl.col("latitud").mean(),
            pl.col("longitud").mean(),
            pl.col("unidad").first(),
            pl.col("promedio").mean(),
            pl.col("mediana").mean(),
            pl.col("maximo").mean(),
            pl.col("no_de_datos").mean().round(0).cast(pl.Int64),
            pl.col("representatividad_temporal").mean(),
            pl.col("dias_excedencia").mean().round(0).cast(pl.Int64),
            pl.col("porcentaje_excedencia").mean(),
        )
        .sort(PRIMARY_KEY)
    )
    duplicate_groups = total_rows - collapsed.height

    # Paso 2: resolver nombre_dpto/nombre_mpio por el valor más frecuente
    # para ese código EN TODO EL DATASET (no solo dentro de cada grupo de
    # PRIMARY_KEY) — la inconsistencia de mayúsculas de la fuente no está
    # confinada a las filas duplicadas del paso 1, aparece entre
    # estaciones/años distintos del mismo departamento/municipio.
    nombres_dpto = raw.group_by("cod_dpto").agg(_most_frequent(pl.col("nombre_dpto")))
    nombres_mpio = raw.group_by("cod_mpio").agg(_most_frequent(pl.col("nombre_mpio")))
    df = (
        collapsed.join(nombres_dpto, on="cod_dpto", how="left")
        .join(nombres_mpio, on="cod_mpio", how="left")
        .select(_OUTPUT_COLUMNS)
        .cast(_SCHEMA)  # type: ignore[arg-type]
        .sort(PRIMARY_KEY)
    )
    return df, excluded, skipped, duplicate_groups


def _fetch_all_rows() -> list[dict[str, Any]]:
    where = "variable in(" + ",".join(f"'{c}'" for c in CONTAMINANTES_ICA) + ")"
    rows: list[dict[str, Any]] = get_json(
        SOURCE_URL,
        params={"$limit": FETCH_LIMIT, "$where": where, "$order": "id_estacion,a_o"},
        timeout=FETCH_TIMEOUT_SECONDS,
    )
    return rows


def _normalization_notes(excluded: int, skipped: int, duplicate_groups: int) -> list[str]:
    notes: list[str] = []
    if excluded > 0:
        notes.append(
            f"{excluded} filas excluidas por no traer código de municipio en la "
            "fuente; ver docs/datasets/calidad_aire.md."
        )
    if skipped > 0:
        notes.append(
            f"{skipped} filas se descartaron durante la normalización por faltarles "
            "un campo indispensable (variable/a_o/id_estacion)."
        )
    if duplicate_groups > 0:
        notes.append(
            f"{duplicate_groups} combinaciones estación+contaminante+ventana+año "
            "venían duplicadas en la fuente (misma fila publicada más de una vez) — "
            "colapsadas al promedio de las copias; ver docs/datasets/calidad_aire.md."
        )
    return notes


class CalidadAireExtractor(BaseExtractor):
    @property
    def dataset_name(self) -> str:
        return DATASET_NAME

    def fetch(self, **kwargs: Any) -> ExtractionResult:
        try:
            rows = _fetch_all_rows()
            if len(rows) < EXPECTED_MIN_ROWS:
                notes = [
                    f"La fuente devolvió solo {len(rows)} filas, menos de las "
                    f"{EXPECTED_MIN_ROWS} esperadas como mínimo."
                ]
            else:
                notes = []
            df, excluded, skipped, duplicate_groups = _normalize(rows)
            notes.extend(_normalization_notes(excluded, skipped, duplicate_groups))

            ensure_staging_directories()
            timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            raw_path = RAW_DIR / f"calidad_aire_{timestamp}.json"
            raw_bytes = json.dumps(rows, ensure_ascii=False).encode("utf-8")
            write_raw_snapshot_atomic(raw_path, raw_bytes)

            return ExtractionResult(
                dataset=DATASET_NAME,
                dataframe=df,
                source_name=SOURCE_NAME,
                source_url=SOURCE_URL,
                source_mode="live",
                source_detail=(
                    "Socrata API, dataset kekd-7v7h, filtrado server-side a los 6 "
                    "contaminantes ICA, sin paginación (dataset pequeño)"
                ),
                reuse_policy=REUSE_POLICY,
                raw_snapshot_path=str(raw_path.relative_to(ROOT_DIR)),
                snapshot_hash=compute_sha256(raw_bytes),
                notes=notes,
            )
        except EXPECTED_FETCH_FAILURES as exc:
            df, excluded, skipped, duplicate_groups = _normalize(CALIDAD_AIRE_FALLBACK_DATA)
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
                    *_normalization_notes(excluded, skipped, duplicate_groups),
                ],
            )

    def write_staging(self, result: ExtractionResult) -> Path:
        ensure_staging_directories()
        csv_path = STAGING_DIR / "calidad_aire.csv"
        metadata_path = STAGING_DIR / "calidad_aire.metadata.json"
        return write_staging_csv_atomic(
            result.dataframe, csv_path, metadata_path, result.to_staging_metadata()
        )


if __name__ == "__main__":
    extractor = CalidadAireExtractor()
    outcome = extractor.run()
    print(f"[{DATASET_NAME}] source_mode={outcome.source_mode} rows={outcome.dataframe.height}")
