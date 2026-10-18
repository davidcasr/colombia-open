"""Derivación de datasets normalizados a partir de staging.

`divipola_extractor` produce UNA tabla de staging (municipios con
departamento embebido). Este builder la parte en dos datasets normalizados:
`departamentos` (único por cod_dpto) y `municipios` (la tabla completa).
"""

from __future__ import annotations

import re
import unicodedata

import polars as pl


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    without_accents = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return without_accents


def clean_name(value: str) -> str:
    """Normaliza un nombre para joins/búsqueda determinística: minúsculas,
    sin tildes, sin caracteres especiales."""
    cleaned = _strip_accents(value).lower()
    cleaned = re.sub(r"[^a-z0-9]+", "_", cleaned).strip("_")
    return cleaned


def derive_departamentos(divipola_df: pl.DataFrame) -> pl.DataFrame:
    df = divipola_df.select(["cod_dpto", "nombre_dpto"]).unique(subset=["cod_dpto"], keep="first")
    df = df.with_columns(
        pl.col("nombre_dpto")
        .map_elements(clean_name, return_dtype=pl.Utf8)
        .alias("nombre_dpto_clean")
    )
    return df.sort("cod_dpto")


def derive_municipios(divipola_df: pl.DataFrame) -> pl.DataFrame:
    df = divipola_df.with_columns(
        pl.col("nombre_mpio")
        .map_elements(clean_name, return_dtype=pl.Utf8)
        .alias("nombre_mpio_clean")
    )
    return df.select(
        [
            "cod_dpto",
            "nombre_dpto",
            "cod_mpio",
            "nombre_mpio",
            "nombre_mpio_clean",
            "tipo_municipio",
            "longitud",
            "latitud",
        ]
    ).sort("cod_mpio")
