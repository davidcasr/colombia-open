"""Validaciones del dominio demografía: proyecciones de población municipal."""

from __future__ import annotations

from typing import Any

import polars as pl

from ._constants import DEMOGRAFIA_AREA_GEOGRAFICA_VALUES, EXPECTED_DEMOGRAFIA_MIN_COUNT
from ._helpers import (
    duplicate_count_multi,
    invalid_fixed_length_count,
    missing_columns,
    unknown_codes_count,
)
from .result import ValidationResult

_REQUIRED_COLUMNS = [
    "cod_dpto",
    "nombre_dpto",
    "cod_mpio",
    "nombre_mpio",
    "anio",
    "area_geografica",
    "poblacion",
]
_KEY_COLUMNS = ["cod_mpio", "anio", "area_geografica"]


def validate_demografia(
    df: pl.DataFrame,
    metadata: dict[str, Any] | None = None,
    *,
    references: dict[str, set[str]] | None = None,
) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    missing = missing_columns(df, _REQUIRED_COLUMNS)
    if missing:
        errors.append(f"faltan columnas requeridas: {missing}")
        return ValidationResult(
            dataset="demografia",
            status="error",
            record_count=df.height,
            errors=errors,
            warnings=warnings,
        )

    dupes = duplicate_count_multi(df, _KEY_COLUMNS)
    if dupes > 0:
        errors.append(
            f"la clave (cod_mpio, anio, area_geografica) debe ser única, "
            f"se encontraron {dupes} duplicados"
        )

    bad_dpto = invalid_fixed_length_count(df, "cod_dpto", 2)
    if bad_dpto > 0:
        errors.append(f"cod_dpto debe tener 2 dígitos, {bad_dpto} filas no cumplen")

    bad_mpio = invalid_fixed_length_count(df, "cod_mpio", 5)
    if bad_mpio > 0:
        errors.append(f"cod_mpio debe tener 5 dígitos, {bad_mpio} filas no cumplen")

    bad_area = int(
        df.filter(~pl.col("area_geografica").is_in(list(DEMOGRAFIA_AREA_GEOGRAFICA_VALUES))).height
    )
    if bad_area > 0:
        errors.append(
            f"area_geografica tiene {bad_area} filas con un valor fuera de "
            f"{sorted(DEMOGRAFIA_AREA_GEOGRAFICA_VALUES)}"
        )

    negative_population = int((df["poblacion"] < 0).sum())
    if negative_population > 0:
        errors.append(f"poblacion tiene {negative_population} filas negativas")

    valid_mpio_codes = references.get("cod_mpio") if references else None
    if valid_mpio_codes:
        orphans = unknown_codes_count(df, "cod_mpio", valid_mpio_codes)
        if orphans > 0:
            # A diferencia de municipios -> departamentos (mismo fetch,
            # mismo momento), demografia y municipios son DOS productos del
            # DANE con ciclos de actualización distintos: es warning, no
            # error, porque el propio archivo DANE documenta un caso real
            # de esto (94663 Mapiripana, absorbido por Barrancominas/94343
            # desde 2019, pero conservado en la serie histórica). Ver nota
            # en `src/extractors/demografia_extractor.py`.
            warnings.append(
                f"{orphans} filas referencian un cod_mpio que no existe en el "
                "municipios vigente (posible municipio histórico/absorbido — "
                "ver docs/datasets/demografia.md)"
            )

    if (
        metadata
        and metadata.get("source_mode") == "live"
        and df.height < EXPECTED_DEMOGRAFIA_MIN_COUNT
    ):
        errors.append(
            f"dataset en vivo luce incompleto: {df.height} filas, se esperaban "
            f"al menos {EXPECTED_DEMOGRAFIA_MIN_COUNT}"
        )

    if metadata and metadata.get("source_mode") == "fallback":
        warnings.append("source_mode=fallback: cobertura limitada por diseño, no se publica")

    return ValidationResult(
        dataset="demografia",
        status="error" if errors else "ok",
        record_count=df.height,
        errors=errors,
        warnings=warnings,
    )
