import polars as pl

from src.validation import validate_infraestructura_poi


def _poi_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "osm_id": [1, 2, 3],
            "categoria": ["salud", "educacion", "comercio"],
            "subcategoria": ["hospital", "school", "supermarket"],
            "nombre": ["Clínica El Bosque", None, "Carulla"],
            "cod_dpto": ["11", "05", "11"],
            "cod_mpio": ["11001", "05001", "11001"],
            "longitud": [-74.030771, -75.604613, -74.060183],
            "latitud": [4.711816, 6.242521, 4.726381],
        }
    )


def test_validate_ok():
    result = validate_infraestructura_poi(_poi_df(), references={"cod_mpio": {"11001", "05001"}})
    assert result.status == "ok"
    assert result.record_count == 3
    assert result.errors == []
    assert result.warnings == []


def test_validate_detects_duplicate_osm_id():
    df = pl.concat([_poi_df(), _poi_df().head(1)])
    result = validate_infraestructura_poi(df)
    assert result.status == "error"
    assert any("duplicados" in e for e in result.errors)


def test_validate_detects_bad_code_width():
    df = _poi_df().with_columns(pl.Series("cod_mpio", ["1001", "05001", "11001"]))
    result = validate_infraestructura_poi(df)
    assert result.status == "error"
    assert any("5 dígitos" in e for e in result.errors)


def test_validate_detects_invalid_categoria():
    df = _poi_df().with_columns(pl.Series("categoria", ["salud", "ocio", "comercio"]))
    result = validate_infraestructura_poi(df)
    assert result.status == "error"
    assert any("categoria" in e for e in result.errors)


def test_validate_out_of_bounds_coords_is_warning():
    df = _poi_df().with_columns(pl.Series("longitud", [-74.030771, -75.604613, 10.0]))
    result = validate_infraestructura_poi(df)
    assert result.status == "ok"
    assert any("fuera del bounding box" in w for w in result.warnings)


def test_validate_orphan_mpio_is_warning_not_error():
    result = validate_infraestructura_poi(_poi_df(), references={"cod_mpio": {"11001"}})
    assert result.status == "ok"
    assert any("no existe en el municipios vigente" in w for w in result.warnings)


def test_validate_empty_dataframe_is_error_not_traceback():
    result = validate_infraestructura_poi(_poi_df().clear())
    assert result.status == "error"
    assert any("vacío" in e for e in result.errors)


def test_validate_missing_columns_is_error_not_traceback():
    result = validate_infraestructura_poi(pl.DataFrame({"osm_id": []}))
    assert result.status == "error"
    assert any("faltan columnas" in e for e in result.errors)


def test_validate_live_with_too_few_rows_is_error():
    result = validate_infraestructura_poi(_poi_df(), {"source_mode": "live"})
    assert result.status == "error"
    assert any("incompleto" in e for e in result.errors)


def test_validate_fallback_adds_warning():
    result = validate_infraestructura_poi(_poi_df(), {"source_mode": "fallback"})
    assert result.status == "ok"
    assert any("fallback" in w for w in result.warnings)
