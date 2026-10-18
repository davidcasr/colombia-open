"""Primitivas de validación compartidas entre dominios.

Cada función devuelve un valor simple (conteo, lista) que el validador de
dominio interpreta — estas funciones nunca lanzan ni deciden status.
"""

from __future__ import annotations

import polars as pl


def missing_columns(df: pl.DataFrame, required: list[str]) -> list[str]:
    return [col for col in required if col not in df.columns]


def duplicate_count(df: pl.DataFrame, key_column: str) -> int:
    if key_column not in df.columns:
        return 0
    return df.height - df[key_column].n_unique()


def invalid_fixed_length_count(df: pl.DataFrame, column: str, length: int) -> int:
    """Cuenta valores que no son exactamente `length` caracteres (códigos admin
    como cod_dpto/cod_mpio deben ser string de ancho fijo, nunca int — ver
    invariante en `.claude/rules/validation.md`)."""
    if column not in df.columns:
        return 0
    series = df[column].cast(pl.Utf8, strict=False)
    return int((series.str.len_chars() != length).sum())


def duplicate_count_multi(df: pl.DataFrame, key_columns: list[str]) -> int:
    """Como `duplicate_count`, pero para una clave primaria compuesta (ej.
    cod_mpio + anio + area_geografica en series de tiempo por municipio)."""
    missing = [col for col in key_columns if col not in df.columns]
    if missing:
        return 0
    return df.height - df.select(key_columns).unique().height


def unknown_codes_count(df: pl.DataFrame, column: str, valid_codes: set[str]) -> int:
    """Integridad referencial: cuenta valores de `column` que no están en
    `valid_codes` (p. ej. cod_dpto de municipios contra departamentos)."""
    if column not in df.columns:
        return 0
    series = df[column].cast(pl.Utf8, strict=False)
    return int(series.is_in(list(valid_codes)).not_().sum())


def out_of_bounds_count(df: pl.DataFrame, column: str, low: float, high: float) -> int:
    if column not in df.columns:
        return 0
    series = df[column].drop_nulls()
    return int(((series < low) | (series > high)).sum())
