"""Resolución de nombres de municipio a código DIVIPOLA.

Reglas (en este orden, sobre el nombre normalizado con `clean_name`):

1. **Coincidencia exacta** contra `nombre_mpio` oficial.
2. **Alias curado** (`MUNICIPIO_ALIASES`): nombres de uso común que no son
   el nombre oficial DIVIPOLA ("Cali" -> "SANTIAGO DE CALI").
3. Si el nombre existe en más de un departamento (Rionegro, La Unión,
   Buenavista…) y no se indicó departamento: **ambiguo**. Nunca se escoge
   uno en silencio — se devuelve `matched=False` con la lista de
   candidatos.
4. Si no hay coincidencia: `matched=False`, con sugerencias aproximadas en
   `candidates`. Las sugerencias son solo una pista para el usuario,
   nunca un match automático.

Los alias apuntan a un `cod_mpio`, no a un nombre: si un código deja de
existir en el `municipios` publicado, el alias simplemente se ignora (no
inventa un municipio que el dataset no tiene).
"""

from __future__ import annotations

from collections.abc import Sequence
from difflib import get_close_matches
from typing import Any

import polars as pl

from .exceptions import ColombiaOpenDatasetError
from .text import clean_name

# Nombre de uso común (ya normalizado con clean_name) -> cod_mpio DIVIPOLA.
# Solo para nombres que NO coinciden con el oficial. Si agregas uno,
# verifica el código contra `hub.load_polars("municipios")` y agrega un
# caso a tests/test_resolve_municipios.py.
MUNICIPIO_ALIASES: dict[str, str] = {
    "cali": "76001",  # SANTIAGO DE CALI
    "bogota": "11001",  # BOGOTÁ, D.C.
    "bogota_dc": "11001",
    "santafe_de_bogota": "11001",
    "cartagena": "13001",  # CARTAGENA DE INDIAS (no Cartagena del Chairá, 18150)
    "cucuta": "54001",  # SAN JOSÉ DE CÚCUTA
    "mompox": "13468",  # SANTA CRUZ DE MOMPOX
    "mompos": "13468",
    "ubate": "25843",  # VILLA DE SAN DIEGO DE UBATÉ
    "buga": "76111",  # GUADALAJARA DE BUGA
    "tolu": "70820",  # SANTIAGO DE TOLÚ
    "toluviejo": "70823",  # SAN JOSÉ DE TOLUVIEJO
    "tumaco": "52835",  # SAN ANDRÉS DE TUMACO
    "san_juan_de_pasto": "52001",  # PASTO
}

# Nombre corto de departamento (normalizado) -> cod_dpto, para el filtro
# `departamento=`. El nombre oficial y el código siempre funcionan además
# de estos.
DEPARTAMENTO_ALIASES: dict[str, str] = {
    "bogota": "11",
    "bogota_dc": "11",
    "valle": "76",
    "san_andres": "88",
    "san_andres_y_providencia": "88",
    "guajira": "44",
    "norte_santander": "54",
}

_MAX_SUGGESTIONS = 3

NameQuery = str | tuple[str, str]


def _label(row: dict[str, Any]) -> str:
    dpto = row.get("nombre_dpto") or row["cod_dpto"]
    return f"{row['cod_mpio']} {row['nombre_mpio']} ({dpto})"


def _resolve_departamento(value: str, municipios: pl.DataFrame) -> str:
    codes = set(municipios["cod_dpto"].to_list())
    stripped = value.strip()
    if stripped.isdigit() and stripped.zfill(2) in codes:
        return stripped.zfill(2)
    key = clean_name(stripped)
    if "nombre_dpto" in municipios.columns:
        by_name: dict[str, str] = {
            clean_name(n): str(c)
            for n, c in municipios.select("nombre_dpto", "cod_dpto").unique().iter_rows()
        }
        if key in by_name:
            return by_name[key]
    alias = DEPARTAMENTO_ALIASES.get(key)
    if alias is not None and alias in codes:
        return alias
    raise ColombiaOpenDatasetError(
        f"Departamento '{value}' no reconocido. Usa el código DIVIPOLA de 2 dígitos "
        "(p. ej. '05') o el nombre oficial (ver hub.load_polars('departamentos'))."
    )


def resolve_municipio_names(
    municipios: pl.DataFrame,
    names: Sequence[NameQuery],
    *,
    departamento: str | None = None,
) -> pl.DataFrame:
    """Ver el docstring del módulo. `names` acepta strings o tuplas
    `(municipio, departamento)`; `departamento=` aplica a todos los
    strings que no traigan el suyo."""
    rows_all = municipios.to_dicts()
    by_name: dict[str, list[dict[str, Any]]] = {}
    for row in rows_all:
        by_name.setdefault(clean_name(row["nombre_mpio"]), []).append(row)
    by_code = {row["cod_mpio"]: row for row in rows_all}

    default_dpto = (
        _resolve_departamento(departamento, municipios) if departamento is not None else None
    )

    out = []
    for item in names:
        dpto_query: str | None
        dpto: str | None
        if isinstance(item, tuple):
            query, dpto_query = item
            dpto = _resolve_departamento(dpto_query, municipios)
        else:
            query, dpto_query, dpto = item, departamento, default_dpto
        key = clean_name(query)

        match_type = "exact"
        candidates = list(by_name.get(key, []))
        if not candidates and key in MUNICIPIO_ALIASES and MUNICIPIO_ALIASES[key] in by_code:
            match_type = "alias"
            candidates = [by_code[MUNICIPIO_ALIASES[key]]]
        if dpto is not None:
            candidates = [r for r in candidates if r["cod_dpto"] == dpto]

        match: dict[str, Any] | None = None
        listed: list[str] = []
        if len(candidates) == 1:
            match = candidates[0]
        elif len(candidates) > 1:
            match_type = "ambiguous"
            listed = [_label(r) for r in candidates]
        else:
            match_type = "not_found"
            pool = (
                by_name
                if dpto is None
                else {k: [r for r in v if r["cod_dpto"] == dpto] for k, v in by_name.items()}
            )
            close = get_close_matches(key, [k for k, v in pool.items() if v], n=_MAX_SUGGESTIONS)
            listed = [_label(r) for k in close for r in pool[k]]

        out.append(
            {
                "query": query,
                "departamento": dpto_query,
                "matched": match is not None,
                "match_type": match_type,
                "cod_mpio": match["cod_mpio"] if match else None,
                "nombre_mpio": match["nombre_mpio"] if match else None,
                "cod_dpto": match["cod_dpto"] if match else None,
                "candidates": listed,
            }
        )
    return pl.DataFrame(
        out,
        schema={
            "query": pl.Utf8,
            "departamento": pl.Utf8,
            "matched": pl.Boolean,
            "match_type": pl.Utf8,
            "cod_mpio": pl.Utf8,
            "nombre_mpio": pl.Utf8,
            "cod_dpto": pl.Utf8,
            "candidates": pl.List(pl.Utf8),
        },
    )
