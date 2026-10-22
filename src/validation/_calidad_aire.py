"""Validaciones del dominio ambiente: calidad del aire (IDEAM)."""

from __future__ import annotations

from typing import Any

import polars as pl

from ._constants import CONTAMINANTES_ICA_VALIDOS, EXPECTED_CALIDAD_AIRE_MIN_COUNT
from ._helpers import (
    duplicate_count_multi,
    invalid_fixed_length_count,
    missing_columns,
    unknown_codes_count,
)
from .result import ValidationResult

_PRIMARY_KEY = ["id_estacion", "contaminante", "tiempo_exposicion_horas", "anio"]
_REQUIRED_COLUMNS = ["cod_dpto", "cod_mpio", "promedio", *_PRIMARY_KEY]


def validate_calidad_aire(
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
            dataset="calidad_aire",
            status="error",
            record_count=df.height,
            errors=[f"faltan columnas requeridas: {missing}"],
            warnings=[],
        )

    if df.height == 0:
        errors.append("dataset vacío")

    dupes = duplicate_count_multi(df, _PRIMARY_KEY)
    if dupes > 0:
        errors.append(f"clave primaria ({', '.join(_PRIMARY_KEY)}) duplicada en {dupes} filas")

    bad_dpto = invalid_fixed_length_count(df, "cod_dpto", 2)
    if bad_dpto > 0:
        errors.append(f"cod_dpto debe tener 2 dígitos, {bad_dpto} filas no cumplen")

    bad_mpio = invalid_fixed_length_count(df, "cod_mpio", 5)
    if bad_mpio > 0:
        errors.append(f"cod_mpio debe tener 5 dígitos, {bad_mpio} filas no cumplen")

    bad_contaminante = df.filter(~pl.col("contaminante").is_in(CONTAMINANTES_ICA_VALIDOS)).height
    if bad_contaminante > 0:
        errors.append(
            f"contaminante debe ser uno de {sorted(CONTAMINANTES_ICA_VALIDOS)}, "
            f"{bad_contaminante} filas no cumplen"
        )

    null_promedio = int(df["promedio"].null_count())
    if null_promedio > 0:
        errors.append(f"promedio es nulo en {null_promedio} filas")
    negative_promedio = int((df["promedio"].fill_null(0) < 0).sum())
    if negative_promedio > 0:
        errors.append(f"promedio tiene {negative_promedio} filas negativas")

    if "representatividad_temporal" in df.columns:
        out_of_range = int(
            ((df["representatividad_temporal"] < 0) | (df["representatividad_temporal"] > 100))
            .fill_null(False)
            .sum()
        )
        if out_of_range > 0:
            warnings.append(
                f"{out_of_range} filas con representatividad_temporal fuera de [0, 100]"
            )

    valid_mpio_codes = references.get("cod_mpio") if references else None
    if valid_mpio_codes:
        orphans = unknown_codes_count(df, "cod_mpio", valid_mpio_codes)
        if orphans > 0:
            # Mismo criterio que el resto del catálogo: IDEAM y DANE/DIVIPOLA
            # son entidades distintas con ciclos de actualización propios.
            warnings.append(
                f"{orphans} filas referencian un cod_mpio que no existe en el municipios vigente"
            )

    if (
        metadata
        and metadata.get("source_mode") == "live"
        and df.height < EXPECTED_CALIDAD_AIRE_MIN_COUNT
    ):
        errors.append(
            f"dataset en vivo luce incompleto: {df.height} filas, se esperaban "
            f"al menos {EXPECTED_CALIDAD_AIRE_MIN_COUNT}"
        )

    if metadata and metadata.get("source_mode") == "fallback":
        warnings.append("source_mode=fallback: cobertura limitada por diseño, no se publica")

    return ValidationResult(
        dataset="calidad_aire",
        status="error" if errors else "ok",
        record_count=df.height,
        errors=errors,
        warnings=warnings,
    )
