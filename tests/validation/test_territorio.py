import polars as pl

from src.validation import validate_departamentos, validate_municipios


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
