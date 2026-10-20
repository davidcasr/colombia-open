"""Validaciones del dominio territorio: departamentos y municipios (DIVIPOLA)."""

from __future__ import annotations

from typing import Any

import polars as pl

from ._constants import (
    COLOMBIA_LAT_MAX,
    COLOMBIA_LAT_MIN,
    COLOMBIA_LON_MAX,
    COLOMBIA_LON_MIN,
    EXPECTED_DEPARTAMENTOS_COUNT,
    EXPECTED_MUNICIPIOS_GEOMETRIA_MIN_COUNT,
    EXPECTED_MUNICIPIOS_MIN_COUNT,
    GEOM_TYPES_VALIDOS,
)
from ._helpers import (
    duplicate_count,
    invalid_fixed_length_count,
    missing_columns,
    out_of_bounds_count,
    unknown_codes_count,
)
from .result import ValidationResult


def _result(
    dataset: str, row_count: int, errors: list[str], warnings: list[str]
) -> ValidationResult:
    return ValidationResult(
        dataset=dataset,
        status="error" if errors else "ok",
        record_count=row_count,
        errors=errors,
        warnings=warnings,
    )


def validate_departamentos(
    df: pl.DataFrame,
    metadata: dict[str, Any] | None = None,
    *,
    references: dict[str, set[str]] | None = None,
) -> ValidationResult:
    # `references` no aplica a departamentos (no referencia otro dataset) —
    # se acepta solo para que todo validador en VALIDATORS comparta la
    # misma firma y el dispatch genérico de core.py pueda llamarlos igual.
    del references
    errors: list[str] = []
    warnings: list[str] = []

    missing = missing_columns(df, ["cod_dpto", "nombre_dpto"])
    if missing:
        errors.append(f"faltan columnas requeridas: {missing}")
        return _result("departamentos", df.height, errors, warnings)

    dupes = duplicate_count(df, "cod_dpto")
    if dupes > 0:
        errors.append(f"cod_dpto debe ser único, se encontraron {dupes} duplicados")

    bad_codes = invalid_fixed_length_count(df, "cod_dpto", 2)
    if bad_codes > 0:
        errors.append(f"cod_dpto debe tener 2 dígitos, {bad_codes} filas no cumplen")

    if (
        metadata
        and metadata.get("source_mode") == "live"
        and df.height < EXPECTED_DEPARTAMENTOS_COUNT
    ):
        errors.append(
            f"dataset en vivo luce incompleto: {df.height} filas, se esperaban "
            f"al menos {EXPECTED_DEPARTAMENTOS_COUNT}"
        )

    if metadata and metadata.get("source_mode") == "fallback":
        warnings.append("source_mode=fallback: cobertura limitada por diseño, no se publica")

    return _result("departamentos", df.height, errors, warnings)


def validate_municipios(
    df: pl.DataFrame,
    metadata: dict[str, Any] | None = None,
    *,
    references: dict[str, set[str]] | None = None,
) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    missing = missing_columns(df, ["cod_dpto", "cod_mpio", "nombre_mpio"])
    if missing:
        errors.append(f"faltan columnas requeridas: {missing}")
        return _result("municipios", df.height, errors, warnings)

    dupes = duplicate_count(df, "cod_mpio")
    if dupes > 0:
        errors.append(f"cod_mpio debe ser único, se encontraron {dupes} duplicados")

    bad_dpto = invalid_fixed_length_count(df, "cod_dpto", 2)
    if bad_dpto > 0:
        errors.append(f"cod_dpto debe tener 2 dígitos, {bad_dpto} filas no cumplen")

    bad_mpio = invalid_fixed_length_count(df, "cod_mpio", 5)
    if bad_mpio > 0:
        errors.append(f"cod_mpio debe tener 5 dígitos, {bad_mpio} filas no cumplen")

    valid_dept_codes = references.get("cod_dpto") if references else None
    if valid_dept_codes:
        orphans = unknown_codes_count(df, "cod_dpto", valid_dept_codes)
        if orphans > 0:
            errors.append(
                f"{orphans} municipios referencian un cod_dpto que no existe en departamentos"
            )

    if "longitud" in df.columns and "latitud" in df.columns:
        lon_out = out_of_bounds_count(df, "longitud", COLOMBIA_LON_MIN, COLOMBIA_LON_MAX)
        lat_out = out_of_bounds_count(df, "latitud", COLOMBIA_LAT_MIN, COLOMBIA_LAT_MAX)
        if lon_out > 0 or lat_out > 0:
            warnings.append(
                f"{lon_out} longitudes y {lat_out} latitudes fuera del bounding box de Colombia"
            )

    if (
        metadata
        and metadata.get("source_mode") == "live"
        and df.height < EXPECTED_MUNICIPIOS_MIN_COUNT
    ):
        errors.append(
            f"dataset en vivo luce incompleto: {df.height} filas, se esperaban "
            f"al menos {EXPECTED_MUNICIPIOS_MIN_COUNT}"
        )

    if metadata and metadata.get("source_mode") == "fallback":
        warnings.append("source_mode=fallback: cobertura limitada por diseño, no se publica")

    return _result("municipios", df.height, errors, warnings)


def validate_municipios_geometria(
    df: pl.DataFrame,
    metadata: dict[str, Any] | None = None,
    *,
    references: dict[str, set[str]] | None = None,
) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    missing = missing_columns(df, ["cod_dpto", "cod_mpio", "geom_type", "area_km2", "geometry_wkt"])
    if missing:
        errors.append(f"faltan columnas requeridas: {missing}")
        return _result("municipios_geometria", df.height, errors, warnings)

    dupes = duplicate_count(df, "cod_mpio")
    if dupes > 0:
        errors.append(f"cod_mpio debe ser único, se encontraron {dupes} duplicados")

    bad_dpto = invalid_fixed_length_count(df, "cod_dpto", 2)
    if bad_dpto > 0:
        errors.append(f"cod_dpto debe tener 2 dígitos, {bad_dpto} filas no cumplen")

    bad_mpio = invalid_fixed_length_count(df, "cod_mpio", 5)
    if bad_mpio > 0:
        errors.append(f"cod_mpio debe tener 5 dígitos, {bad_mpio} filas no cumplen")

    bad_geom_type = df.filter(~pl.col("geom_type").is_in(GEOM_TYPES_VALIDOS)).height
    if bad_geom_type > 0:
        errors.append(
            f"geom_type debe ser uno de {sorted(GEOM_TYPES_VALIDOS)}, {bad_geom_type} filas no cumplen"
        )

    null_wkt = int(df["geometry_wkt"].null_count())
    empty_wkt = int((df["geometry_wkt"].fill_null("") == "").sum())
    if null_wkt > 0 or empty_wkt > 0:
        errors.append(f"geometry_wkt nulo o vacío en {max(null_wkt, empty_wkt)} filas")

    null_area = int(df["area_km2"].null_count())
    if null_area > 0:
        errors.append(f"area_km2 es nulo en {null_area} filas")
    non_positive_area = int((df["area_km2"].fill_null(1) <= 0).sum())
    if non_positive_area > 0:
        errors.append(f"area_km2 debe ser > 0, {non_positive_area} filas no cumplen")

    valid_mpio_codes = references.get("cod_mpio") if references else None
    if valid_mpio_codes:
        orphans = unknown_codes_count(df, "cod_mpio", valid_mpio_codes)
        if orphans > 0:
            # Mismo criterio que demografia/educacion/delincuencia: MGN
            # (DANE, vigencia 2020) y municipios (DIVIPOLA, vigencia actual)
            # son productos con ciclos de actualización propios.
            warnings.append(
                f"{orphans} filas referencian un cod_mpio que no existe en el municipios vigente"
            )

    if (
        metadata
        and metadata.get("source_mode") == "live"
        and df.height < EXPECTED_MUNICIPIOS_GEOMETRIA_MIN_COUNT
    ):
        errors.append(
            f"dataset en vivo luce incompleto: {df.height} filas, se esperaban "
            f"al menos {EXPECTED_MUNICIPIOS_GEOMETRIA_MIN_COUNT}"
        )

    if metadata and metadata.get("source_mode") == "fallback":
        warnings.append("source_mode=fallback: cobertura limitada por diseño, no se publica")

    return _result("municipios_geometria", df.height, errors, warnings)
