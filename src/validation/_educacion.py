"""Validaciones del dominio educación: directorio de establecimientos educativos."""

from __future__ import annotations

from typing import Any

import polars as pl

from ._constants import (
    EDUCACION_CODIGO_DANE_LOW_CARDINALITY_RATIO,
    EXPECTED_EDUCACION_ESTABLECIMIENTOS_MIN_COUNT,
    EXPECTED_EDUCACION_SABER11_MIN_COUNT,
)
from ._helpers import (
    duplicate_count_multi,
    invalid_fixed_length_count,
    missing_columns,
    unknown_codes_count,
)
from .result import ValidationResult

_REQUIRED_COLUMNS = [
    "anio",
    "cod_dpto",
    "cod_mpio",
    "codigo_dane_establecimiento",
    "nombre_establecimiento",
]

_SABER11_PRIMARY_KEY = ["codigo_dane_establecimiento", "periodo"]
_SABER11_REQUIRED_COLUMNS = [
    "anio",
    "cod_dpto",
    "cod_mpio",
    "naturaleza",
    "n_estudiantes",
    *_SABER11_PRIMARY_KEY,
]
_SABER11_PROM_COLUMNS = [
    "prom_matematicas",
    "prom_ingles",
    "prom_lectura_critica",
    "prom_sociales_ciudadanas",
    "prom_c_naturales",
    "prom_global",
]


def _check_codigo_dane_cardinality_per_year(df: pl.DataFrame) -> list[str]:
    """`codigo_dane_establecimiento` NO es una clave primaria garantizada
    por la fuente — confirmado en vivo el 2026-10-18: incluso los años
    "limpios" tienen un puñado de duplicados genuinos (ej. 2015: 11/19610,
    2024: 79/18076), y 2023 tiene un defecto sistémico mucho más severo
    (3043/416716 valores únicos). Por eso esto siempre es warning, nunca
    error — a diferencia de municipios (cod_mpio sí es único de verdad en
    su fuente) — con el mensaje diferenciando ruido normal de un posible
    defecto sistémico por año, detectado dinámicamente (no hardcodea
    "2023")."""
    warnings: list[str] = []

    per_year = df.group_by("anio").agg(
        [
            pl.len().alias("n_rows"),
            pl.col("codigo_dane_establecimiento").n_unique().alias("n_distinct"),
        ]
    )
    for row in per_year.iter_rows(named=True):
        n_rows, n_distinct = row["n_rows"], row["n_distinct"]
        dupes = n_rows - n_distinct
        if dupes <= 0:
            continue
        ratio = n_distinct / n_rows if n_rows else 1.0
        if ratio < EDUCACION_CODIGO_DANE_LOW_CARDINALITY_RATIO:
            warnings.append(
                f"año {row['anio']}: codigo_dane_establecimiento tiene baja "
                f"cardinalidad ({n_distinct}/{n_rows} valores únicos) — posible "
                "defecto sistémico de la fuente para ese año, no se trata como "
                "clave primaria duplicada (ver docs/datasets/educacion_establecimientos.md)"
            )
        else:
            warnings.append(
                f"año {row['anio']}: {dupes} filas con codigo_dane_establecimiento "
                "duplicado (la fuente no garantiza unicidad de este campo — ver "
                "docs/datasets/educacion_establecimientos.md)"
            )
    return warnings


def validate_educacion_establecimientos(
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
            dataset="educacion_establecimientos",
            status="error",
            record_count=df.height,
            errors=errors,
            warnings=warnings,
        )

    bad_dpto = invalid_fixed_length_count(df, "cod_dpto", 2)
    if bad_dpto > 0:
        errors.append(f"cod_dpto debe tener 2 dígitos, {bad_dpto} filas no cumplen")

    bad_mpio = invalid_fixed_length_count(df, "cod_mpio", 5)
    if bad_mpio > 0:
        errors.append(f"cod_mpio debe tener 5 dígitos, {bad_mpio} filas no cumplen")

    if "cod_mpio" in df.columns:
        null_mpio = int(df["cod_mpio"].null_count())
        if null_mpio > 0:
            # Defecto conocido de la fuente (25/606206 filas en 2023,
            # confirmado en vivo 2026-10-18): Socrata omite el campo
            # cod_dane_municipio en vez de mandarlo null. Warning, no
            # error — ver docs/datasets/educacion_establecimientos.md.
            warnings.append(
                f"{null_mpio} filas sin cod_mpio (campo ausente en la fuente, "
                "no se fabrica un valor de reemplazo)"
            )

    bad_codigo = invalid_fixed_length_count(df, "codigo_dane_establecimiento", 12)
    if bad_codigo > 0:
        errors.append(
            f"codigo_dane_establecimiento debe tener 12 dígitos, {bad_codigo} filas no cumplen"
        )

    warnings.extend(_check_codigo_dane_cardinality_per_year(df))

    if "total_matricula" in df.columns:
        negative_matricula = int((df["total_matricula"].fill_null(0) < 0).sum())
        if negative_matricula > 0:
            errors.append(f"total_matricula tiene {negative_matricula} filas negativas")

    valid_mpio_codes = references.get("cod_mpio") if references else None
    if valid_mpio_codes:
        orphans = unknown_codes_count(df, "cod_mpio", valid_mpio_codes)
        if orphans > 0:
            # Mismo criterio que demografia: dos productos distintos del
            # Estado (MEN vs. DANE/DIVIPOLA) con ciclos de actualización
            # propios pueden divergir en códigos de municipio sin que sea
            # un error de esta fuente — ver .claude/rules/validation.md.
            warnings.append(
                f"{orphans} filas referencian un cod_mpio que no existe en el municipios vigente"
            )

    if (
        metadata
        and metadata.get("source_mode") == "live"
        and df.height < EXPECTED_EDUCACION_ESTABLECIMIENTOS_MIN_COUNT
    ):
        errors.append(
            f"dataset en vivo luce incompleto: {df.height} filas, se esperaban "
            f"al menos {EXPECTED_EDUCACION_ESTABLECIMIENTOS_MIN_COUNT}"
        )

    if metadata and metadata.get("source_mode") == "fallback":
        warnings.append("source_mode=fallback: cobertura limitada por diseño, no se publica")

    return ValidationResult(
        dataset="educacion_establecimientos",
        status="error" if errors else "ok",
        record_count=df.height,
        errors=errors,
        warnings=warnings,
    )


def validate_educacion_saber11(
    df: pl.DataFrame,
    metadata: dict[str, Any] | None = None,
    *,
    references: dict[str, set[str]] | None = None,
) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []

    missing = missing_columns(df, _SABER11_REQUIRED_COLUMNS)
    if missing:
        return ValidationResult(
            dataset="educacion_saber11",
            status="error",
            record_count=df.height,
            errors=[f"faltan columnas requeridas: {missing}"],
            warnings=[],
        )

    if df.height == 0:
        errors.append("dataset vacío")

    dupes = duplicate_count_multi(df, _SABER11_PRIMARY_KEY)
    if dupes > 0:
        errors.append(
            f"clave primaria ({', '.join(_SABER11_PRIMARY_KEY)}) duplicada en {dupes} filas"
        )

    bad_dpto = invalid_fixed_length_count(df, "cod_dpto", 2)
    if bad_dpto > 0:
        errors.append(f"cod_dpto debe tener 2 dígitos, {bad_dpto} filas no cumplen")

    bad_mpio = invalid_fixed_length_count(df, "cod_mpio", 5)
    if bad_mpio > 0:
        errors.append(f"cod_mpio debe tener 5 dígitos, {bad_mpio} filas no cumplen")

    bad_codigo = invalid_fixed_length_count(df, "codigo_dane_establecimiento", 12)
    if bad_codigo > 0:
        errors.append(
            f"codigo_dane_establecimiento debe tener 12 dígitos, {bad_codigo} filas no cumplen"
        )

    null_n = int(df["n_estudiantes"].null_count())
    if null_n > 0:
        errors.append(f"n_estudiantes es nulo en {null_n} filas")
    non_positive_n = int((df["n_estudiantes"].fill_null(1) <= 0).sum())
    if non_positive_n > 0:
        errors.append(f"n_estudiantes debe ser > 0, {non_positive_n} filas no cumplen")

    # Los 6 promedios son nulos por diseño antes del periodo 20142 (4 de
    # ellos) o si la fuente no trae el puntaje para ningún estudiante del
    # grupo — nunca error. Solo un promedio negativo sería un bug real
    # (puntaje ICFES no puede ser negativo).
    for col in _SABER11_PROM_COLUMNS:
        if col not in df.columns:
            continue
        negative = int((df[col].fill_null(0) < 0).sum())
        if negative > 0:
            errors.append(f"{col} tiene {negative} filas negativas")

    unclassified_naturaleza = df.filter(pl.col("naturaleza").is_null()).height
    if unclassified_naturaleza > 0:
        warnings.append(
            f"naturaleza nula en {unclassified_naturaleza} filas (la fuente no la "
            "reportó para ningún estudiante de ese establecimiento-periodo)"
        )

    valid_mpio_codes = references.get("cod_mpio") if references else None
    if valid_mpio_codes:
        orphans = unknown_codes_count(df, "cod_mpio", valid_mpio_codes)
        if orphans > 0:
            # Mismo criterio que educacion_establecimientos: ICFES y DANE/
            # DIVIPOLA son productos de entidades distintas con ciclos de
            # actualización propios.
            warnings.append(
                f"{orphans} filas referencian un cod_mpio que no existe en el municipios vigente"
            )

    if (
        metadata
        and metadata.get("source_mode") == "live"
        and df.height < EXPECTED_EDUCACION_SABER11_MIN_COUNT
    ):
        errors.append(
            f"dataset en vivo luce incompleto: {df.height} filas, se esperaban "
            f"al menos {EXPECTED_EDUCACION_SABER11_MIN_COUNT}"
        )

    if metadata and metadata.get("source_mode") == "fallback":
        warnings.append("source_mode=fallback: cobertura limitada por diseño, no se publica")

    return ValidationResult(
        dataset="educacion_saber11",
        status="error" if errors else "ok",
        record_count=df.height,
        errors=errors,
        warnings=warnings,
    )
