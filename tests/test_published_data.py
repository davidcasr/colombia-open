"""Spot-checks de calidad sobre datos REALES (no fixtures).

Corre contra:
- `COLOMBIA_OPEN_DATA_DIR` si está definido (p. ej. un bundle publicado
  descargado y descomprimido), o
- `data/normalized/` del repo si existe (después de `make build`; así
  corre solo en `pipeline-check.yml` y `release.yml`, que construyen antes
  de testear).

Si no hay ninguno de los dos, se salta: los tests unitarios no dependen de
la red ni del pipeline.

    COLOMBIA_OPEN_DATA_DIR=/ruta/al/bundle python -m pytest tests/test_published_data.py
"""

from __future__ import annotations

import json
import os
from functools import cache
from pathlib import Path
from typing import Any

import polars as pl
import pytest

_REPO_NORMALIZED = Path(__file__).resolve().parents[1] / "data" / "normalized"


def _data_dir() -> Path | None:
    env = os.environ.get("COLOMBIA_OPEN_DATA_DIR")
    if env:
        return Path(env)
    if (_REPO_NORMALIZED / "dataset_catalog.json").exists():
        return _REPO_NORMALIZED
    return None


DATA_DIR = _data_dir()
pytestmark = pytest.mark.skipif(
    DATA_DIR is None,
    reason="sin datos reales: define COLOMBIA_OPEN_DATA_DIR o corre `make build`",
)

# Tolerancia de filas huérfanas (cod_mpio fuera de `municipios` vigente).
# Hoy el peor caso es <0.1%; un salto a >1% indica un cambio de
# codificación en la fuente, no municipios históricos sueltos.
_MAX_ORPHAN_FRACTION = 0.01


@cache
def _catalog() -> dict[str, Any]:
    assert DATA_DIR is not None
    data: dict[str, Any] = json.loads(
        (DATA_DIR / "dataset_catalog.json").read_text(encoding="utf-8")
    )
    return data


def _entries() -> list[dict[str, Any]]:
    return list(_catalog()["datasets"]) if DATA_DIR else []


def _parquet(entry: dict[str, Any]) -> Path:
    assert DATA_DIR is not None
    return DATA_DIR / Path(entry["outputs"]["parquet"]).name


def _code_columns(entry: dict[str, Any]) -> list[str]:
    schema = pl.read_parquet_schema(_parquet(entry))
    return [c for c in ("cod_dpto", "cod_mpio") if c in schema]


def _ids(entries: list[dict[str, Any]]) -> list[str]:
    return [e["dataset"] for e in entries]


_ENTRIES = _entries()
_WITH_CODES = [e for e in _ENTRIES if DATA_DIR and _code_columns(e)]


@cache
def _load(name: str, columns: tuple[str, ...] | None = None) -> pl.DataFrame:
    entry = next(e for e in _ENTRIES if e["dataset"] == name)
    return pl.read_parquet(_parquet(entry), columns=list(columns) if columns else None)


@pytest.mark.parametrize("entry", _WITH_CODES, ids=_ids(_WITH_CODES))
def test_admin_codes_are_fixed_width_digit_strings(entry):
    """cod_dpto: 2 dígitos, cod_mpio: 5 dígitos, siempre string (nunca int
    — el bug del cero inicial perdido)."""
    schema = pl.read_parquet_schema(_parquet(entry))
    for column, width in (("cod_dpto", 2), ("cod_mpio", 5)):
        if column not in schema:
            continue
        assert schema[column] == pl.Utf8, f"{column} es {schema[column]}, no string"
        values = _load(entry["dataset"], (column,))[column].drop_nulls()
        bad = values.filter(~values.str.contains(rf"^\d{{{width}}}$"))
        assert bad.len() == 0, f"{column} con ancho != {width}: {bad.unique().head(5).to_list()}"


def test_departamentos_has_33_unique():
    df = _load("departamentos")
    assert df.height == 33
    assert df["cod_dpto"].n_unique() == 33


def test_municipios_counts_are_coherent():
    municipios = _load("municipios")
    departamentos = set(_load("departamentos")["cod_dpto"].to_list())
    assert municipios.height >= 1100
    assert municipios["cod_mpio"].n_unique() == municipios.height
    # Todo municipio pertenece a un departamento existente, su código
    # empieza por el del departamento, y ningún departamento queda vacío.
    assert set(municipios["cod_dpto"].to_list()) == departamentos
    assert (municipios["cod_mpio"].str.slice(0, 2) == municipios["cod_dpto"]).all()
    per_dpto = municipios.group_by("cod_dpto").len()
    assert per_dpto["len"].min() >= 1


_WITH_MPIO = [
    e for e in _WITH_CODES if "cod_mpio" in _code_columns(e) and e["dataset"] != "municipios"
]


@pytest.mark.parametrize("entry", _WITH_MPIO, ids=_ids(_WITH_MPIO))
def test_join_with_municipios_orphans_are_rare_and_reported(entry):
    """Huérfanos permitidos (municipios históricos, códigos centinela de
    la fuente) solo si son pocos Y el catálogo los reporta en `warnings`
    — nunca huérfanos silenciosos."""
    valid = set(_load("municipios")["cod_mpio"].to_list())
    codes = _load(entry["dataset"], ("cod_mpio",))["cod_mpio"].drop_nulls()
    orphans = codes.filter(~codes.is_in(list(valid)))
    if orphans.len() == 0:
        return
    fraction = orphans.len() / max(codes.len(), 1)
    assert fraction <= _MAX_ORPHAN_FRACTION, (
        f"{orphans.len()} filas huérfanas ({fraction:.2%}): {orphans.unique().head(5).to_list()}"
    )
    assert any("cod_mpio que no existe" in w for w in entry.get("warnings", [])), (
        f"{orphans.len()} filas huérfanas sin warning en el catálogo"
    )


@pytest.mark.parametrize("entry", _ENTRIES, ids=_ids(_ENTRIES))
def test_every_dataset_keeps_source_link_and_license(entry):
    """Regla dura #4: nunca se publica un dataset sin fuente oficial."""
    assert entry.get("source_url", "").startswith("https://")
    assert entry.get("source_name")
    assert (entry.get("reuse_policy") or {}).get("license")
