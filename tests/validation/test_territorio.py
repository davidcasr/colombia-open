import polars as pl

from src.validation import (
    validate_departamentos,
    validate_municipios,
    validate_municipios_geometria,
)


def _departamentos_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "cod_dpto": ["05", "11", "76"],
            "nombre_dpto": ["ANTIOQUIA", "BOGOTÁ, D.C.", "VALLE DEL CAUCA"],
        }
    )


def _municipios_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "cod_dpto": ["05", "11", "76"],
            "nombre_dpto": ["ANTIOQUIA", "BOGOTÁ, D.C.", "VALLE DEL CAUCA"],
            "cod_mpio": ["05001", "11001", "76001"],
            "nombre_mpio": ["MEDELLÍN", "BOGOTÁ, D.C.", "CALI"],
            "tipo_municipio": ["Municipio", "Capital", "Municipio"],
            "longitud": [-75.58, -74.08, -76.53],
            "latitud": [6.25, 4.61, 3.42],
        }
    )


def test_validate_departamentos_ok():
    result = validate_departamentos(_departamentos_df())
    assert result.status == "ok"
    assert result.record_count == 3
    assert result.errors == []


def test_validate_departamentos_detects_duplicates():
    df = pl.concat([_departamentos_df(), _departamentos_df().head(1)])
    result = validate_departamentos(df)
    assert result.status == "error"
    assert any("duplicado" in e for e in result.errors)


def test_validate_departamentos_detects_bad_code_width():
    df = _departamentos_df().with_columns(pl.Series("cod_dpto", ["5", "11", "76"]))
    result = validate_departamentos(df)
    assert result.status == "error"
    assert any("2 dígitos" in e for e in result.errors)


def test_validate_municipios_ok():
    result = validate_municipios(_municipios_df(), references={"cod_dpto": {"05", "11", "76"}})
    assert result.status == "ok"
    assert result.record_count == 3


def test_validate_municipios_detects_orphan_department():
    result = validate_municipios(_municipios_df(), references={"cod_dpto": {"05", "11"}})
    assert result.status == "error"
    assert any("no existe en departamentos" in e for e in result.errors)


def test_validate_municipios_empty_dataframe_missing_columns():
    df = pl.DataFrame({"cod_dpto": [], "cod_mpio": []})
    result = validate_municipios(df)
    assert result.status == "error"
    assert "faltan columnas" in result.errors[0]


def test_validate_municipios_warns_on_fallback_mode():
    result = validate_municipios(
        _municipios_df(),
        {"source_mode": "fallback"},
        references={"cod_dpto": {"05", "11", "76"}},
    )
    assert any("fallback" in w for w in result.warnings)


# --- municipios_geometria ---


def _geometria_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "cod_dpto": ["05", "11", "76"],
            "cod_mpio": ["05001", "11001", "76001"],
            "geom_type": ["Polygon", "Polygon", "MultiPolygon"],
            "area_km2": [374.5, 1622.8, 1.2],
            "geometry_wkt": [
                "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
                "MULTIPOLYGON (((0 0, 0 1, 1 1, 1 0, 0 0)))",
            ],
        }
    )


def test_validate_geometria_ok():
    result = validate_municipios_geometria(
        _geometria_df(), references={"cod_mpio": {"05001", "11001", "76001"}}
    )
    assert result.status == "ok"
    assert result.record_count == 3
    assert result.errors == []
    assert result.warnings == []


def test_validate_geometria_detects_duplicate_cod_mpio():
    df = pl.concat([_geometria_df(), _geometria_df().head(1)])
    result = validate_municipios_geometria(df)
    assert result.status == "error"
    assert any("duplicados" in e for e in result.errors)


def test_validate_geometria_detects_bad_code_width():
    df = _geometria_df().with_columns(pl.Series("cod_mpio", ["5001", "11001", "76001"]))
    result = validate_municipios_geometria(df)
    assert result.status == "error"
    assert any("5 dígitos" in e for e in result.errors)


def test_validate_geometria_detects_invalid_geom_type():
    df = _geometria_df().with_columns(pl.Series("geom_type", ["Polygon", "Point", "Polygon"]))
    result = validate_municipios_geometria(df)
    assert result.status == "error"
    assert any("geom_type" in e for e in result.errors)


def test_validate_geometria_detects_empty_wkt():
    df = _geometria_df().with_columns(pl.Series("geometry_wkt", ["", "POLYGON ((0 0))", "x"]))
    result = validate_municipios_geometria(df)
    assert result.status == "error"
    assert any("geometry_wkt" in e for e in result.errors)


def test_validate_geometria_detects_non_positive_area():
    df = _geometria_df().with_columns(pl.Series("area_km2", [374.5, 0.0, -1.0]))
    result = validate_municipios_geometria(df)
    assert result.status == "error"
    assert any("area_km2 debe ser > 0" in e for e in result.errors)


def test_validate_geometria_orphan_mpio_is_warning_not_error():
    result = validate_municipios_geometria(_geometria_df(), references={"cod_mpio": {"05001"}})
    assert result.status == "ok"
    assert any("no existe en el municipios vigente" in w for w in result.warnings)


def test_validate_geometria_empty_dataframe_missing_columns():
    df = pl.DataFrame({"cod_dpto": [], "cod_mpio": []})
    result = validate_municipios_geometria(df)
    assert result.status == "error"
    assert "faltan columnas" in result.errors[0]


def test_validate_geometria_live_with_too_few_rows_is_error():
    result = validate_municipios_geometria(_geometria_df(), {"source_mode": "live"})
    assert result.status == "error"
    assert any("incompleto" in e for e in result.errors)


def test_validate_geometria_fallback_adds_warning():
    result = validate_municipios_geometria(_geometria_df(), {"source_mode": "fallback"})
    assert result.status == "ok"
    assert any("fallback" in w for w in result.warnings)
