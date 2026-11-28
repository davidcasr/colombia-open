"""Validaciones del dominio agro: Evaluaciones Agropecuarias Municipales
(EVA, UPRA 2019-2025 + MinAgricultura 2006-2018)."""

from __future__ import annotations

from typing import Any

import polars as pl

from ._constants import AGRO_EVA_SERIES_VALIDAS, EXPECTED_AGRO_EVA_MIN_COUNT
from ._helpers import (
    dpto_mpio_mismatch_count,
    duplicate_count_multi,
    invalid_fixed_length_count,
    missing_columns,
    unknown_codes_count,
)
from .result import ValidationResult

_PRIMARY_KEY = ["cod_mpio", "cultivo", "desagregacion_cultivo", "periodo"]
_MEASURES = ["area_sembrada_ha", "area_cosechada_ha", "produccion_t", "rendimiento_t_ha"]
_REQUIRED_COLUMNS = [
    "cod_dpto",
    "nombre_dpto",
    "nombre_mpio",
    "cultivo_clean",
    "anio",
    "serie_fuente",
    *_PRIMARY_KEY,
    *_MEASURES,
]


def validate_agro_eva(
    df: pl.DataFrame,
    metadata: dict[str, Any] | None = None,
    *,
    references: dict[str, set[str]] | None = None,
) -> ValidationResult:
    missing = missing_columns(df, _REQUIRED_COLUMNS)
    if missing:
        return ValidationResult(
            dataset="agro_eva",
            status="error",
            record_count=df.height,
            errors=[f"faltan columnas requeridas: {missing}"],
            warnings=[],
        )

    errors: list[str] = []
    warnings: list[str] = []

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

    inconsistent = dpto_mpio_mismatch_count(df)
    if inconsistent > 0:
        errors.append(f"{inconsistent} filas con cod_mpio que no empieza por su cod_dpto")

    for measure in _MEASURES:
        negatives = int((df[measure].fill_null(0) < 0).sum())
        if negatives > 0:
            errors.append(f"{measure} debe ser >= 0, {negatives} filas no cumplen")
        if measure == "rendimiento_t_ha":
            continue
        nulls = int(df[measure].null_count())
        if nulls > 0:
            errors.append(f"{measure} es nulo en {nulls} filas")

    # Rendimiento nulo solo es legítimo si no se cosechó nada (t/ha = 0/0):
    # convención de la serie MinAgricultura, ver docs/datasets/agro_eva.md.
    null_yield_with_harvest = int(
        (df["rendimiento_t_ha"].is_null() & (df["area_cosechada_ha"].fill_null(0) > 0)).sum()
    )
    if null_yield_with_harvest > 0:
        errors.append(
            f"rendimiento_t_ha es nulo en {null_yield_with_harvest} filas con area_cosechada_ha > 0"
        )

    yield_without_harvest = int(
        ((df["area_cosechada_ha"] == 0) & (df["rendimiento_t_ha"].fill_null(0) > 0)).sum()
    )
    if yield_without_harvest > 0:
        warnings.append(
            f"{yield_without_harvest} filas con rendimiento_t_ha > 0 pero "
            "area_cosechada_ha = 0 — ver docs/datasets/agro_eva.md (Limitaciones)"
        )

    # `periodo` es "2021", "2021A" o "2021B": siempre empieza por su año.
    period_mismatch = int(
        (df["periodo"].cast(pl.Utf8).str.slice(0, 4) != df["anio"].cast(pl.Utf8)).sum()
    )
    if period_mismatch > 0:
        errors.append(f"{period_mismatch} filas con periodo que no empieza por su anio")

    unknown_series = sorted(
        set(df["serie_fuente"].drop_nulls().unique().to_list()) - AGRO_EVA_SERIES_VALIDAS
    )
    if unknown_series or df["serie_fuente"].null_count() > 0:
        errors.append(
            f"serie_fuente con valores no reconocidos: {unknown_series or ['<nulo>']} "
            f"(válidos: {sorted(AGRO_EVA_SERIES_VALIDAS)})"
        )

    # Las dos series no se solapan en años (2006-2018 vs. 2019-2025). Un año
    # presente en ambas significaría contar dos veces la misma cosecha.
    series_per_year = df.group_by("anio").agg(pl.col("serie_fuente").n_unique().alias("n"))
    overlapping_years = sorted(series_per_year.filter(pl.col("n") > 1)["anio"].to_list())
    if overlapping_years:
        errors.append(f"años presentes en ambas series (doble conteo): {overlapping_years}")

    # Defecto (o metodología) de la fuente, no del extractor: área cosechada
    # mayor que la sembrada, casi siempre en cultivos transitorios — ver
    # docs/datasets/agro_eva.md. Se reporta, nunca se corrige ni se excluye.
    over_harvested = int((df["area_cosechada_ha"] > df["area_sembrada_ha"]).sum())
    if over_harvested > 0:
        warnings.append(
            f"{over_harvested} filas con area_cosechada_ha > area_sembrada_ha — "
            "ver docs/datasets/agro_eva.md (Limitaciones)"
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
        and df.height < EXPECTED_AGRO_EVA_MIN_COUNT
    ):
        errors.append(
            f"dataset en vivo luce incompleto: {df.height} filas, se esperaban "
            f"al menos {EXPECTED_AGRO_EVA_MIN_COUNT}"
        )

    if metadata and metadata.get("source_mode") == "fallback":
        warnings.append("source_mode=fallback: cobertura limitada por diseño, no se publica")

    return ValidationResult(
        dataset="agro_eva",
        status="error" if errors else "ok",
        record_count=df.height,
        errors=errors,
        warnings=warnings,
    )
