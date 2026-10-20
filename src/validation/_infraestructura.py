"""Validaciones del dominio infraestructura: puntos de interés urbanos
(OpenStreetMap vía Geofabrik)."""

from __future__ import annotations

from typing import Any

import polars as pl

from ._constants import (
    CATEGORIAS_POI_VALIDAS,
    COLOMBIA_LAT_MAX,
    COLOMBIA_LAT_MIN,
    COLOMBIA_LON_MAX,
    COLOMBIA_LON_MIN,
    EXPECTED_INFRAESTRUCTURA_POI_MIN_COUNT,
)
from ._helpers import (
    duplicate_count,
    invalid_fixed_length_count,
    missing_columns,
    out_of_bounds_count,
    unknown_codes_count,
)
from .result import ValidationResult

_REQUIRED_COLUMNS = [
    "osm_id",
    "categoria",
    "subcategoria",
    "cod_dpto",
    "cod_mpio",
    "longitud",
    "latitud",
]


def validate_infraestructura_poi(
    df: pl.DataFrame,
    metadata: dict[str, Any] | None = None,
    *,
    references: dict[str, set[str]] | None = None,
) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    missing = missing_columns(df, _REQUIRED_COLUMNS)
    if missing:
        return ValidationResult(
            dataset="infraestructura_poi",
            status="error",
            record_count=df.height,
            errors=[f"faltan columnas requeridas: {missing}"],
            warnings=[],
        )

    if df.height == 0:
        errors.append("dataset vacío")

    dupes = duplicate_count(df, "osm_id")
    if dupes > 0:
        errors.append(f"osm_id debe ser único, se encontraron {dupes} duplicados")

    bad_dpto = invalid_fixed_length_count(df, "cod_dpto", 2)
    if bad_dpto > 0:
        errors.append(f"cod_dpto debe tener 2 dígitos, {bad_dpto} filas no cumplen")

    bad_mpio = invalid_fixed_length_count(df, "cod_mpio", 5)
    if bad_mpio > 0:
        errors.append(f"cod_mpio debe tener 5 dígitos, {bad_mpio} filas no cumplen")

    bad_categoria = df.filter(~pl.col("categoria").is_in(CATEGORIAS_POI_VALIDAS)).height
    if bad_categoria > 0:
        errors.append(
            f"categoria debe ser una de {sorted(CATEGORIAS_POI_VALIDAS)}, "
            f"{bad_categoria} filas no cumplen"
        )

    lon_out = out_of_bounds_count(df, "longitud", COLOMBIA_LON_MIN, COLOMBIA_LON_MAX)
    lat_out = out_of_bounds_count(df, "latitud", COLOMBIA_LAT_MIN, COLOMBIA_LAT_MAX)
    if lon_out > 0 or lat_out > 0:
        warnings.append(
            f"{lon_out} longitudes y {lat_out} latitudes fuera del bounding box de Colombia"
        )

    valid_mpio_codes = references.get("cod_mpio") if references else None
    if valid_mpio_codes:
        orphans = unknown_codes_count(df, "cod_mpio", valid_mpio_codes)
        if orphans > 0:
            warnings.append(
                f"{orphans} filas referencian un cod_mpio que no existe en el municipios vigente"
            )

    if (
        metadata
        and metadata.get("source_mode") == "live"
        and df.height < EXPECTED_INFRAESTRUCTURA_POI_MIN_COUNT
    ):
        errors.append(
            f"dataset en vivo luce incompleto: {df.height} filas, se esperaban "
            f"al menos {EXPECTED_INFRAESTRUCTURA_POI_MIN_COUNT}"
        )

    if metadata and metadata.get("source_mode") == "fallback":
        warnings.append("source_mode=fallback: cobertura limitada por diseño, no se publica")

    return ValidationResult(
        dataset="infraestructura_poi",
        status="error" if errors else "ok",
        record_count=df.height,
        errors=errors,
        warnings=warnings,
    )
