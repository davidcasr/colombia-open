"""Validaciones del dominio delincuencia: hurto a personas por municipio y día."""

from __future__ import annotations

from typing import Any

import polars as pl

from ._constants import (
    DELINCUENCIA_LOW_MPIO_COVERAGE_RATIO,
    EXPECTED_DELINCUENCIA_HURTO_PERSONAS_MIN_COUNT,
)
from ._helpers import (
    duplicate_count_multi,
    invalid_fixed_length_count,
    missing_columns,
    unknown_codes_count,
)
from .result import ValidationResult

_REQUIRED_COLUMNS = ["fecha", "anio", "cod_dpto", "cod_mpio", "cantidad"]
_PRIMARY_KEY = ["fecha", "cod_mpio"]


def _check_mpio_coverage_per_year(df: pl.DataFrame) -> list[str]:
    """Detecta años con cobertura municipal anómalamente baja frente a la
    mediana de todos los años — el síntoma de que la fuente reportó ese año
    casi sin desagregar por municipio. Confirmado en vivo el 2026-10-19:
    2008 tiene 76 municipios con código (el resto de víctimas viene como
    "SIN ESTABLECER" y el extractor las excluye), contra ~630-1050
    cualquier otro año. Warning, nunca error: el dato que sí trae es real.
    Se detecta dinámicamente, no hardcodea "2008"."""
    per_year = df.group_by("anio").agg(pl.col("cod_mpio").n_unique().alias("n_mpios"))
    if per_year.height < 3:
        return []
    median = float(per_year.select(pl.col("n_mpios").median()).item() or 0)
    warnings: list[str] = []
    for row in per_year.sort("anio").iter_rows(named=True):
        if row["n_mpios"] < median * DELINCUENCIA_LOW_MPIO_COVERAGE_RATIO:
            warnings.append(
                f"año {row['anio']}: solo {row['n_mpios']} municipios con datos "
                f"(mediana {median:.0f}) — posible falta de desagregación municipal "
                "en la fuente para ese año (ver docs/datasets/delincuencia_hurto_personas.md)"
            )
    return warnings


def validate_delincuencia_hurto_personas(
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
            dataset="delincuencia_hurto_personas",
            status="error",
            record_count=df.height,
            errors=errors,
            warnings=warnings,
        )

    if df.height == 0:
        errors.append("dataset vacío")

    dupes = duplicate_count_multi(df, _PRIMARY_KEY)
    if dupes > 0:
        errors.append(f"clave primaria (fecha, cod_mpio) duplicada en {dupes} filas")

    bad_dpto = invalid_fixed_length_count(df, "cod_dpto", 2)
    if bad_dpto > 0:
        errors.append(f"cod_dpto debe tener 2 dígitos, {bad_dpto} filas no cumplen")

    bad_mpio = invalid_fixed_length_count(df, "cod_mpio", 5)
    if bad_mpio > 0:
        errors.append(f"cod_mpio debe tener 5 dígitos, {bad_mpio} filas no cumplen")

    # cod_mpio empieza siempre por su cod_dpto en DIVIPOLA: una fila que lo
    # contradiga es un código corrupto, no una divergencia entre catálogos.
    inconsistent = int(
        (df["cod_mpio"].cast(pl.Utf8).str.slice(0, 2) != df["cod_dpto"].cast(pl.Utf8)).sum()
    )
    if inconsistent > 0:
        errors.append(f"{inconsistent} filas con cod_mpio que no empieza por su cod_dpto")

    null_cantidad = int(df["cantidad"].null_count())
    if null_cantidad > 0:
        errors.append(f"cantidad es nula en {null_cantidad} filas")
    non_positive = int((df["cantidad"].fill_null(1) <= 0).sum())
    if non_positive > 0:
        errors.append(f"cantidad debe ser > 0, {non_positive} filas no cumplen")

    warnings.extend(_check_mpio_coverage_per_year(df))

    valid_mpio_codes = references.get("cod_mpio") if references else None
    if valid_mpio_codes:
        orphans = unknown_codes_count(df, "cod_mpio", valid_mpio_codes)
        if orphans > 0:
            # Mismo criterio que demografia/educacion: productos de entidades
            # distintas (Policía vs. DANE) con ciclos propios pueden divergir
            # en códigos de municipio — ver .claude/rules/validation.md.
            warnings.append(
                f"{orphans} filas referencian un cod_mpio que no existe en el municipios vigente"
            )

    if (
        metadata
        and metadata.get("source_mode") == "live"
        and df.height < EXPECTED_DELINCUENCIA_HURTO_PERSONAS_MIN_COUNT
    ):
        errors.append(
            f"dataset en vivo luce incompleto: {df.height} filas, se esperaban "
            f"al menos {EXPECTED_DELINCUENCIA_HURTO_PERSONAS_MIN_COUNT}"
        )

    if metadata and metadata.get("source_mode") == "fallback":
        warnings.append("source_mode=fallback: cobertura limitada por diseño, no se publica")

    return ValidationResult(
        dataset="delincuencia_hurto_personas",
        status="error" if errors else "ok",
        record_count=df.height,
        errors=errors,
        warnings=warnings,
    )
