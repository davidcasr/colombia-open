"""Normalización de texto para joins/búsqueda determinística por nombre."""

from __future__ import annotations

import re
import unicodedata


def clean_name(value: str) -> str:
    """minúsculas, sin tildes, sin caracteres especiales — mismo algoritmo
    usado al construir las columnas `*_clean` en el pipeline (ver
    `src/builders/datasets.py`), para que buscar por nombre aquí y en los
    datos ya publicados dé el mismo resultado."""
    normalized = unicodedata.normalize("NFKD", value)
    without_accents = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    cleaned = without_accents.lower()
    cleaned = re.sub(r"[^a-z0-9]+", "_", cleaned).strip("_")
    return cleaned
