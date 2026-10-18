import json

import polars as pl
import pytest

from colombia_open import ColombiaOpen
from colombia_open.exceptions import ColombiaOpenDatasetError
from colombia_open.mcp_server import (
    DEFAULT_LIMIT,
    McpQueryError,
    _describe_dataset_impl,
    _list_datasets_impl,
    _query_impl,
)


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
    # Reusa el nombre real "educacion_establecimientos" (no uno inventado):
    # ColombiaOpen.get_dataset()/get_output_path() validan el nombre contra
    # el enum Dataset real, no solo contra lo que haya en el catálogo del
    # fixture — un nombre inventado como "grande" falla esa validación.
    # Los datos en sí son sintéticos (1500 filas), solo para poder probar
    # el cap/truncamiento — con 2 filas (como departamentos/municipios) no
    # se puede demostrar nada sobre el límite.
    educacion_establecimientos = pl.DataFrame({"n": list(range(1500))})

    departamentos.write_parquet(normalized / "departamentos.parquet")
    municipios.write_parquet(normalized / "municipios.parquet")
    educacion_establecimientos.write_parquet(normalized / "educacion_establecimientos.parquet")

    catalog = {
        "generated_at_utc": "2026-10-17T00:00:00Z",
        "datasets": [
            {
                "dataset": "departamentos",
                "description": "test departamentos",
                "source_name": "DANE",
                "source_url": "https://example.test",
                "source_mode": "live",
                "record_count": 2,
                "join_keys": ["cod_dpto"],
                "reuse_policy": {"status": "open-attribution", "license": "CC BY-SA 4.0"},
                "validation_status": "ok",
                "warnings": [],
                "usage_examples": {"python": "..."},
                "outputs": {"parquet": "data/normalized/departamentos.parquet"},
                "documentation": "docs/datasets/departamentos.md",
            },
            {
                "dataset": "municipios",
                "description": "test municipios",
                "source_name": "DANE",
                "source_url": "https://example.test",
                "source_mode": "live",
                "record_count": 2,
                "join_keys": ["cod_mpio", "cod_dpto"],
                "reuse_policy": {"status": "open-attribution", "license": "CC BY-SA 4.0"},
                "validation_status": "ok",
                "warnings": ["aviso de prueba"],
                "usage_examples": {"python": "..."},
                "outputs": {"parquet": "data/normalized/municipios.parquet"},
                "documentation": "docs/datasets/municipios.md",
            },
            {
                "dataset": "educacion_establecimientos",
                "description": "test dataset educacion_establecimientos para probar el cap de filas",
                "source_name": "test",
                "source_url": "https://example.test",
                "source_mode": "live",
                "record_count": 1500,
                "join_keys": [],
                "reuse_policy": {"status": "open-attribution", "license": "CC0"},
                "validation_status": "ok",
                "warnings": [],
                "usage_examples": {"python": "..."},
                "outputs": {"parquet": "data/normalized/educacion_establecimientos.parquet"},
                "documentation": "docs/datasets/educacion_establecimientos.md",
            },
        ],
    }
    (normalized / "dataset_catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    return normalized


@pytest.fixture
def hub(catalog_dir):
    return ColombiaOpen(data_dir=catalog_dir)


def test_list_datasets_impl(hub):
    result = _list_datasets_impl(hub)
    names = [d["dataset"] for d in result]
    assert names == ["departamentos", "municipios", "educacion_establecimientos"]
    assert result[0]["license"] == "CC BY-SA 4.0"
    assert result[0]["record_count"] == 2


def test_describe_dataset_impl_includes_columns_and_warnings(hub):
    entry = _describe_dataset_impl(hub, "municipios")
    assert entry["columns"] == {
        "cod_dpto": "String",
        "cod_mpio": "String",
        "nombre_mpio": "String",
    }
    assert entry["warnings"] == ["aviso de prueba"]
    assert entry["validation_status"] == "ok"


def test_describe_dataset_impl_unknown_dataset_raises(hub):
    with pytest.raises(ColombiaOpenDatasetError):
        _describe_dataset_impl(hub, "no_existe")


def test_query_impl_simple_select(hub):
    result = _query_impl(
        hub, "SELECT cod_dpto, nombre_dpto FROM departamentos WHERE cod_dpto = '05'"
    )
    assert result["rows"] == [{"cod_dpto": "05", "nombre_dpto": "ANTIOQUIA"}]
    assert result["row_count"] == 1
    assert result["truncated"] is False


def test_query_impl_join_across_datasets(hub):
    result = _query_impl(
        hub,
        """
        SELECT d.nombre_dpto, m.nombre_mpio
        FROM municipios m
        JOIN departamentos d ON m.cod_dpto = d.cod_dpto
        ORDER BY m.nombre_mpio
        """,
    )
    assert result["rows"] == [
        {"nombre_dpto": "BOGOTÁ", "nombre_mpio": "BOGOTÁ, D.C."},
        {"nombre_dpto": "ANTIOQUIA", "nombre_mpio": "MEDELLÍN"},
    ]


def test_query_impl_default_limit_truncates_large_result(hub):
    result = _query_impl(hub, "SELECT n FROM educacion_establecimientos ORDER BY n")
    assert result["row_count"] == DEFAULT_LIMIT
    assert result["truncated"] is True
    assert result["limit"] == DEFAULT_LIMIT
    assert result["rows"][0]["n"] == 0
    assert result["rows"][-1]["n"] == DEFAULT_LIMIT - 1


def test_query_impl_under_cap_not_truncated(hub):
    result = _query_impl(hub, "SELECT n FROM educacion_establecimientos WHERE n < 5")
    assert result["row_count"] == 5
    assert result["truncated"] is False


def test_query_impl_explicit_limit_is_clamped_to_max(hub):
    result = _query_impl(hub, "SELECT n FROM educacion_establecimientos", limit=10_000)
    assert result["limit"] == 1000  # MAX_LIMIT
    assert result["row_count"] == 1000
    assert result["truncated"] is True


def test_query_impl_trailing_semicolon_is_tolerated(hub):
    result = _query_impl(hub, "SELECT cod_dpto FROM departamentos; ")
    assert result["row_count"] == 2


@pytest.mark.parametrize(
    "bad_sql",
    [
        "SELECT * FROM read_parquet('data/normalized/departamentos.parquet')",
        "SELECT * FROM read_csv('C:/Windows/win.ini')",
        "SELECT * FROM scan_parquet('anything')",
        "SELECT 1; DROP TABLE departamentos",
        "SELECT 1; SELECT 2",
        "DROP TABLE departamentos",
        "INSERT INTO departamentos VALUES ('99', 'FAKE')",
        "",
        "   ",
        "not even sql",
    ],
)
def test_query_impl_rejects_unsafe_sql(hub, bad_sql):
    with pytest.raises(McpQueryError):
        _query_impl(hub, bad_sql)


def test_query_impl_rejects_sql_over_length_cap(hub):
    huge = "SELECT " + "1" * 20_000
    with pytest.raises(McpQueryError):
        _query_impl(hub, huge)
