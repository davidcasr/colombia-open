"""Validaciones del dominio macroeconomía: TRM (Superintendencia Financiera)."""

from __future__ import annotations

from typing import Any

import polars as pl

from ._constants import EXPECTED_MACROECONOMIA_TRM_MIN_COUNT
from ._helpers import duplicate_count, missing_columns
from .result import ValidationResult

_REQUIRED_COLUMNS = ["fecha", "vigente_hasta", "trm"]


def validate_macroeconomia_trm(
    df: pl.DataFrame,
    metadata: dict[str, Any] | None = None,
    *,
    references: dict[str, set[str]] | None = None,
) -> ValidationResult:
    # `references` no aplica (serie nacional, sin dimensión territorial) —
    # se acepta solo para que el dispatch genérico de core.py llame a todo
    # validador con la misma firma.
    del references
    errors: list[str] = []
    warnings: list[str] = []

    missing = missing_columns(df, _REQUIRED_COLUMNS)
    if missing:
        return ValidationResult(
            dataset="macroeconomia_trm",
            status="error",
            record_count=df.height,
            errors=[f"faltan columnas requeridas: {missing}"],
            warnings=[],
        )

    if df.height == 0:
        errors.append("dataset vacío")

    dupes = duplicate_count(df, "fecha")
    if dupes > 0:
        errors.append(f"fecha debe ser única, se encontraron {dupes} duplicados")

    null_trm = int(df["trm"].null_count())
    if null_trm > 0:
        errors.append(f"trm es nulo en {null_trm} filas")
    non_positive = int((df["trm"].fill_null(1) <= 0).sum())
    if non_positive > 0:
        errors.append(f"trm debe ser > 0, {non_positive} filas no cumplen")

    inverted = int((df["vigente_hasta"] < df["fecha"]).sum())
    if inverted > 0:
        errors.append(f"vigente_hasta es anterior a fecha en {inverted} filas")

    if (
        metadata
        and metadata.get("source_mode") == "live"
        and df.height < EXPECTED_MACROECONOMIA_TRM_MIN_COUNT
    ):
        errors.append(
            f"dataset en vivo luce incompleto: {df.height} filas, se esperaban "
            f"al menos {EXPECTED_MACROECONOMIA_TRM_MIN_COUNT}"
        )

    if metadata and metadata.get("source_mode") == "fallback":
        warnings.append("source_mode=fallback: cobertura limitada por diseño, no se publica")

    return ValidationResult(
        dataset="macroeconomia_trm",
        status="error" if errors else "ok",
        record_count=df.height,
        errors=errors,
        warnings=warnings,
    )
