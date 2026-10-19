import json

import polars as pl
import pytest

import colombia_open.core as core_module
from colombia_open import ColombiaOpen
from colombia_open.exceptions import ColombiaOpenDatasetError, ColombiaOpenOutputError


@pytest.fixture
def catalog_dir(tmp_path):
    normalized = tmp_path / "data" / "normalized"
    normalized.mkdir(parents=True)

    departamentos = pl.DataFrame({"cod_dpto": ["05", "11"], "nombre_dpto": ["ANTIOQUIA", "BOGOTÁ"]})
    municipios = pl.DataFrame(
        {
            "cod_dpto": ["05", "11"],
            "cod_mpio": ["05001", "11001"],
            "nombre_mpio": ["MEDELLÍN", "BOGOTÁ, D.C."],
        }
    )
    departamentos.write_parquet(normalized / "departamentos.parquet")
    municipios.write_parquet(normalized / "municipios.parquet")

    catalog = {
        "generated_at_utc": "2026-10-17T00:00:00Z",
        "datasets": [
            {
                "dataset": "departamentos",
                "description": "test",
                "source_name": "DANE",
                "source_url": "https://example.test",
                "source_mode": "live",
                "record_count": 2,
                "join_keys": ["cod_dpto"],
                "reuse_policy": {"status": "open-attribution"},
                "validation_status": "ok",
                "warnings": [],
                "usage_examples": {"python": "..."},
                "outputs": {"parquet": "data/normalized/departamentos.parquet"},
                "documentation": "docs/datasets/departamentos.md",
            },
            {
                "dataset": "municipios",
                "description": "test",
                "source_name": "DANE",
                "source_url": "https://example.test",
                "source_mode": "live",
                "record_count": 2,
                "join_keys": ["cod_mpio", "cod_dpto"],
                "reuse_policy": {"status": "open-attribution"},
                "validation_status": "ok",
                "warnings": [],
                "usage_examples": {"python": "..."},
                "outputs": {"parquet": "data/normalized/municipios.parquet"},
                "documentation": "docs/datasets/municipios.md",
            },
        ],
    }
    (normalized / "dataset_catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    return normalized


def test_list_datasets(catalog_dir):
    hub = ColombiaOpen(data_dir=catalog_dir)
    assert hub.list_datasets() == ["departamentos", "municipios"]


def test_load_polars_returns_dataframe(catalog_dir):
    hub = ColombiaOpen(data_dir=catalog_dir)
    df = hub.load_polars("municipios")
    assert df.height == 2
    assert "cod_mpio" in df.columns


def test_load_polars_caches_dataframe(catalog_dir):
    hub = ColombiaOpen(data_dir=catalog_dir)
    first = hub.load_polars("departamentos")
    second = hub.load_polars("departamentos")
    assert first is second


def test_unknown_dataset_raises_with_suggestion(catalog_dir):
    hub = ColombiaOpen(data_dir=catalog_dir)
    with pytest.raises(ColombiaOpenDatasetError):
        hub.get_dataset("municipio")  # typo


def test_unknown_output_type_raises(catalog_dir):
    hub = ColombiaOpen(data_dir=catalog_dir)
    with pytest.raises(ColombiaOpenOutputError):
        hub.get_output_path("departamentos", "duckdb_table")


def test_cross_view_joins_on_shared_key(catalog_dir):
    hub = ColombiaOpen(data_dir=catalog_dir)
    joined = hub.cross_view(["municipios", "departamentos"], on="cod_dpto")
    assert "nombre_dpto" in joined.columns
    assert "nombre_mpio" in joined.columns


def test_find_dev_catalog_does_not_walk_past_editable_install_depth(tmp_path, monkeypatch):
    """`_find_dev_catalog()` solo debe chequear la profundidad exacta de un
    install editable (src/colombia_open/core.py -> repo root), no caminar
    hacia arriba indefinidamente. Si camina indefinidamente, un venv creado
    DENTRO del repo (el flujo normal de `make bootstrap`) haría que
    cualquier wheel instalado de verdad encuentre por accidente los datos
    del repo en vez de caer al bundle de GitHub Releases."""
    fake_repo_root = tmp_path / "unrelated_repo"
    fake_core_dir = fake_repo_root / "src" / "colombia_open"
    fake_core_dir.mkdir(parents=True)
    (fake_core_dir / "core.py").touch()

    # Decoy: un ancestro MÁS ARRIBA del fake "repo root" también tiene datos
    # — si el walk no estuviera acotado, los encontraría primero.
    decoy_normalized = tmp_path / "data" / "normalized"
    decoy_normalized.mkdir(parents=True)
    (decoy_normalized / "dataset_catalog.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(core_module, "__file__", str(fake_core_dir / "core.py"))
    assert core_module._find_dev_catalog() is None

    # Ahora sí existe exactamente en la profundidad esperada (repo root real).
    real_normalized = fake_repo_root / "data" / "normalized"
    real_normalized.mkdir(parents=True)
    (real_normalized / "dataset_catalog.json").write_text("{}", encoding="utf-8")
    found = core_module._find_dev_catalog()
    assert found == real_normalized / "dataset_catalog.json"


def test_provenance_exposes_source_fields(catalog_dir):
    hub = ColombiaOpen(data_dir=catalog_dir)
    info = hub.provenance("departamentos")
    assert info["source_name"] == "DANE"
    assert info["source_mode"] == "live"


@pytest.fixture
def catalog_dir_with_orphan_municipio(tmp_path):
    """Como `catalog_dir`, pero un municipio referencia un cod_dpto que no
    existe en departamentos — para probar que `validate_dataset()` resuelve
    `references` desde el registro REAL (`data/registry/datasets.json`,
    que declara `municipios.cod_dpto -> departamentos`), no solo desde un
    kwarg que alguien se acuerde de pasar a mano."""
    normalized = tmp_path / "data" / "normalized"
    normalized.mkdir(parents=True)

    departamentos = pl.DataFrame({"cod_dpto": ["05", "11"], "nombre_dpto": ["ANTIOQUIA", "BOGOTÁ"]})
    municipios = pl.DataFrame(
        {
            "cod_dpto": ["05", "99"],  # "99" no existe en departamentos
            "cod_mpio": ["05001", "99001"],
            "nombre_mpio": ["MEDELLÍN", "MUNICIPIO FANTASMA"],
        }
    )
    departamentos.write_parquet(normalized / "departamentos.parquet")
    municipios.write_parquet(normalized / "municipios.parquet")

    catalog = {
        "generated_at_utc": "2026-10-17T00:00:00Z",
        "datasets": [
            {
                "dataset": "departamentos",
                "description": "test",
                "source_name": "DANE",
                "source_url": "https://example.test",
                "source_mode": "live",
                "record_count": 2,
                "join_keys": ["cod_dpto"],
                "reuse_policy": {"status": "open-attribution"},
                "validation_status": "ok",
                "warnings": [],
                "usage_examples": {"python": "..."},
                "outputs": {"parquet": "data/normalized/departamentos.parquet"},
                "documentation": "docs/datasets/departamentos.md",
            },
            {
                "dataset": "municipios",
                "description": "test",
                "source_name": "DANE",
                "source_url": "https://example.test",
                "source_mode": "live",
                "record_count": 2,
                "join_keys": ["cod_mpio", "cod_dpto"],
                "reuse_policy": {"status": "open-attribution"},
                "validation_status": "ok",
                "warnings": [],
                "usage_examples": {"python": "..."},
                "outputs": {"parquet": "data/normalized/municipios.parquet"},
                "documentation": "docs/datasets/municipios.md",
            },
        ],
    }
    (normalized / "dataset_catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    return normalized


def test_validate_dataset_catches_orphan_department_via_registry_references(
    catalog_dir_with_orphan_municipio,
):
    hub = ColombiaOpen(data_dir=catalog_dir_with_orphan_municipio)
    result = hub.validate_dataset("municipios")
    assert result["status"] == "error"
    assert any("no existe en departamentos" in e for e in result["errors"])


def test_validate_dataset_departamentos_unaffected_by_references(
    catalog_dir_with_orphan_municipio,
):
    # departamentos no declara `references` en el registro — confirma que
    # pasarle `references=None` no la rompe (y que el error de municipios
    # no se filtra aquí). Con solo 2 filas sí dispara el aviso de "dataset
    # en vivo luce incompleto" (espera >= 33), que es un error distinto y
    # esperado dado el tamaño mínimo del fixture — no el que probamos acá.
    hub = ColombiaOpen(data_dir=catalog_dir_with_orphan_municipio)
    result = hub.validate_dataset("departamentos")
    assert not any("no existe en departamentos" in e for e in result["errors"])


def test_version_matches_pyproject():
    import tomllib
    from pathlib import Path

    import colombia_open

    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    expected = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]
    assert colombia_open.__version__ == expected
