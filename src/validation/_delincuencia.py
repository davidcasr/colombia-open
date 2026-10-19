"""Validaciones del dominio delincuencia: hurto a personas y lesiones
personales por municipio y día (Policía Nacional)."""

from __future__ import annotations

from typing import Any

import polars as pl

from ._constants import (
    DELINCUENCIA_LOW_MPIO_COVERAGE_RATIO,
    EXPECTED_DELINCUENCIA_HURTO_PERSONAS_MIN_COUNT,
    EXPECTED_DELINCUENCIA_LESIONES_PERSONALES_MIN_COUNT,
)
from ._helpers import (
    duplicate_count_multi,
    invalid_fixed_length_count,
    missing_columns,
    unknown_codes_count,
)
from .result import ValidationResult

_HURTO_REQUIRED_COLUMNS = ["fecha", "anio", "cod_dpto", "cod_mpio", "cantidad"]
_HURTO_PRIMARY_KEY = ["fecha", "cod_mpio"]

_LESIONES_PRIMARY_KEY = ["fecha", "cod_mpio", "conducta", "arma_medio", "genero", "grupo_etario"]
_LESIONES_REQUIRED_COLUMNS = ["anio", "cod_dpto", "tipo_lesion", "cantidad", *_LESIONES_PRIMARY_KEY]


def _check_mpio_coverage_per_year(df: pl.DataFrame, doc: str) -> list[str]:
    """Detecta años con cobertura municipal anómalamente baja frente a la
    mediana de todos los años — el síntoma de que la fuente reportó ese año
    casi sin desagregar por municipio. Confirmado en vivo el 2026-10-19 en
    hurto a personas: 2008 tiene 76 municipios con código (el resto de
    víctimas viene como "SIN ESTABLECER" y el extractor las excluye), contra
    ~630-1050 cualquier otro año. Warning, nunca error: el dato que sí trae
    es real. Se detecta dinámicamente, no hardcodea "2008"."""
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
                f"en la fuente para ese año (ver {doc})"
            )
    return warnings


def _check_common(
    df: pl.DataFrame,
    metadata: dict[str, Any] | None,
    references: dict[str, set[str]] | None,
    *,
    primary_key: list[str],
    min_live_count: int,
    doc: str,
) -> tuple[list[str], list[str]]:
    """Reglas compartidas por todo dataset de delincuencia por municipio y
    día: clave primaria, códigos DIVIPOLA, `cantidad`, cobertura por año,
    integridad referencial y conteo mínimo en vivo. Asume que las columnas
    requeridas ya se verificaron."""
    errors: list[str] = []
    warnings: list[str] = []

    if df.height == 0:
        errors.append("dataset vacío")

    dupes = duplicate_count_multi(df, primary_key)
    if dupes > 0:
        errors.append(f"clave primaria ({', '.join(primary_key)}) duplicada en {dupes} filas")

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

    warnings.extend(_check_mpio_coverage_per_year(df, doc))

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

    if metadata and metadata.get("source_mode") == "live" and df.height < min_live_count:
        errors.append(
            f"dataset en vivo luce incompleto: {df.height} filas, se esperaban "
            f"al menos {min_live_count}"
        )

    if metadata and metadata.get("source_mode") == "fallback":
        warnings.append("source_mode=fallback: cobertura limitada por diseño, no se publica")

    return errors, warnings


def validate_delincuencia_hurto_personas(
    df: pl.DataFrame,
    metadata: dict[str, Any] | None = None,
    *,
    references: dict[str, set[str]] | None = None,
) -> ValidationResult:
    missing = missing_columns(df, _HURTO_REQUIRED_COLUMNS)
    if missing:
        return ValidationResult(
            dataset="delincuencia_hurto_personas",
            status="error",
            record_count=df.height,
            errors=[f"faltan columnas requeridas: {missing}"],
            warnings=[],
        )

    errors, warnings = _check_common(
        df,
        metadata,
        references,
        primary_key=_HURTO_PRIMARY_KEY,
        min_live_count=EXPECTED_DELINCUENCIA_HURTO_PERSONAS_MIN_COUNT,
        doc="docs/datasets/delincuencia_hurto_personas.md",
    )
    return ValidationResult(
        dataset="delincuencia_hurto_personas",
        status="error" if errors else "ok",
        record_count=df.height,
        errors=errors,
        warnings=warnings,
    )


def validate_delincuencia_lesiones_personales(
    df: pl.DataFrame,
    metadata: dict[str, Any] | None = None,
    *,
    references: dict[str, set[str]] | None = None,
) -> ValidationResult:
    missing = missing_columns(df, _LESIONES_REQUIRED_COLUMNS)
    if missing:
        return ValidationResult(
            dataset="delincuencia_lesiones_personales",
            status="error",
            record_count=df.height,
            errors=[f"faltan columnas requeridas: {missing}"],
            warnings=[],
        )

    errors, warnings = _check_common(
        df,
        metadata,
        references,
        primary_key=_LESIONES_PRIMARY_KEY,
        min_live_count=EXPECTED_DELINCUENCIA_LESIONES_PERSONALES_MIN_COUNT,
        doc="docs/datasets/delincuencia_lesiones_personales.md",
    )

    # tipo_lesion se deriva del artículo del Código Penal en `conducta`; un
    # nulo significa que la fuente empezó a reportar un artículo que el
    # extractor no clasifica. Warning: el dato es real, solo falta mapearlo.
    unclassified = df.filter(pl.col("tipo_lesion").is_null())
    if unclassified.height > 0:
        conductas = sorted(unclassified["conducta"].drop_nulls().unique().to_list())
        warnings.append(
            f"tipo_lesion sin clasificar en {unclassified.height} filas — conducta(s) "
            f"no mapeada(s) en el extractor: {conductas}"
        )

    return ValidationResult(
        dataset="delincuencia_lesiones_personales",
        status="error" if errors else "ok",
        record_count=df.height,
        errors=errors,
        warnings=warnings,
    )
