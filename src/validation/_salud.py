"""Validaciones del dominio salud: RETHUS (talento humano en salud,
MinSalud)."""

from __future__ import annotations

from typing import Any

import polars as pl

from ._constants import EXPECTED_RETHUS_MIN_COUNT, RETHUS_SNAPSHOT_MAX_PLAUSIBLE_YEAR
from ._helpers import duplicate_count_multi, invalid_fixed_length_count, missing_columns
from .result import ValidationResult

_PRIMARY_KEY = [
    "cod_mpio",
    "origen_titulo",
    "tipo_institucion",
    "tipo_programa",
    "perfil_profesional",
    "anio_registro",
]
_REQUIRED_COLUMNS = ["cod_dpto", "nombre_dpto", "nombre_mpio", "numero_registros", *_PRIMARY_KEY]


def validate_rethus(
    df: pl.DataFrame,
    metadata: dict[str, Any] | None = None,
    *,
    references: dict[str, set[str]] | None = None,
) -> ValidationResult:
    missing = missing_columns(df, _REQUIRED_COLUMNS)
    if missing:
        return ValidationResult(
            dataset="rethus",
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

    # cod_mpio empieza siempre por su cod_dpto en DIVIPOLA: una fila que lo
    # contradiga es un código corrupto, no una divergencia entre catálogos.
    if "cod_dpto" in df.columns and "cod_mpio" in df.columns and df.height > 0:
        inconsistent = int(
            (df["cod_mpio"].cast(pl.Utf8).str.slice(0, 2) != df["cod_dpto"].cast(pl.Utf8)).sum()
        )
        if inconsistent > 0:
            errors.append(f"{inconsistent} filas con cod_mpio que no empieza por su cod_dpto")

    null_num = int(df["numero_registros"].null_count())
    if null_num > 0:
        errors.append(f"numero_registros es nulo en {null_num} filas")
    non_positive = int((df["numero_registros"].fill_null(1) <= 0).sum())
    if non_positive > 0:
        errors.append(f"numero_registros debe ser > 0, {non_positive} filas no cumplen")

    # Defecto conocido de la fuente: filas con año de acto administrativo
    # posterior al corte real del snapshot (2022) — ver docstring del
    # extractor. El dato no se fabrica ni se excluye, solo se señala.
    future_years = df.filter(pl.col("anio_registro") > RETHUS_SNAPSHOT_MAX_PLAUSIBLE_YEAR)
    if future_years.height > 0:
        warnings.append(
            f"{future_years.height} filas con anio_registro posterior a "
            f"{RETHUS_SNAPSHOT_MAX_PLAUSIBLE_YEAR} (corte real del snapshot) — "
            "defecto de captura conocido de la fuente, ver docs/datasets/rethus.md"
        )

    valid_mpio_codes = references.get("cod_mpio") if references else None
    if valid_mpio_codes:
        orphans = int(df["cod_mpio"].cast(pl.Utf8).is_in(list(valid_mpio_codes)).not_().sum())
        if orphans > 0:
            warnings.append(
                f"{orphans} filas referencian un cod_mpio que no existe en el municipios vigente"
            )

    if metadata and metadata.get("source_mode") == "live" and df.height < EXPECTED_RETHUS_MIN_COUNT:
        errors.append(
            f"dataset en vivo luce incompleto: {df.height} filas, se esperaban "
            f"al menos {EXPECTED_RETHUS_MIN_COUNT}"
        )

    if metadata and metadata.get("source_mode") == "fallback":
        warnings.append("source_mode=fallback: cobertura limitada por diseño, no se publica")

    return ValidationResult(
        dataset="rethus",
        status="error" if errors else "ok",
        record_count=df.height,
        errors=errors,
        warnings=warnings,
    )
