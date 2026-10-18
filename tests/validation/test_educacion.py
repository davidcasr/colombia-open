import polars as pl

from src.validation import validate_educacion_establecimientos


def _educacion_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "anio": [2015, 2015, 2020],
            "cod_dpto": ["05", "05", "11"],
            "nombre_dpto": ["ANTIOQUIA", "ANTIOQUIA", "BOGOTÁ, D.C."],
            "cod_mpio": ["05001", "05002", "11001"],
            "nombre_mpio": ["MEDELLÍN", "ABEJORRAL", "BOGOTÁ, D.C."],
            "codigo_dane_establecimiento": ["305001000001", "305002000001", "311001000001"],
            "nombre_establecimiento": ["COLEGIO A", "COLEGIO B", "COLEGIO C"],
            "total_matricula": [500, 120, 900],
        }
    )


def test_validate_educacion_ok():
    result = validate_educacion_establecimientos(
        _educacion_df(), references={"cod_mpio": {"05001", "05002", "11001"}}
    )
    assert result.status == "ok"
    assert result.record_count == 3
    assert result.errors == []


def test_validate_educacion_detects_bad_code_width():
    df = _educacion_df().with_columns(pl.Series("cod_mpio", ["5001", "05002", "11001"]))
    result = validate_educacion_establecimientos(df)
    assert result.status == "error"
    assert any("5 dígitos" in e for e in result.errors)


def test_validate_educacion_detects_bad_codigo_dane_width():
    df = _educacion_df().with_columns(
        pl.Series("codigo_dane_establecimiento", ["1", "305002000001", "311001000001"])
    )
    result = validate_educacion_establecimientos(df)
    assert result.status == "error"
    assert any("12 dígitos" in e for e in result.errors)


def test_validate_educacion_high_cardinality_duplicates_are_warnings_not_errors():
    # La fuente no garantiza unicidad de codigo_dane ni siquiera en años
    # "limpios" — confirmado en vivo el 2026-10-18 (ej. 2015 real: 11
    # duplicados sobre 19610 filas). Un solo duplicado real en un año de
    # alta cardinalidad general es warning, no error — a diferencia de
    # cod_mpio en `municipios`, que sí es una clave primaria garantizada.
    df = pl.DataFrame(
        {
            "anio": [2015] * 10,
            "cod_dpto": ["05"] * 10,
            "cod_mpio": ["05001"] * 10,
            "codigo_dane_establecimiento": [f"30500100000{i}" for i in range(9)] + ["305001000000"],
            "nombre_establecimiento": [f"COLEGIO {i}" for i in range(10)],
        }
    )
    result = validate_educacion_establecimientos(df)
    assert result.status == "ok"
    assert any("duplicado" in w for w in result.warnings)


def test_validate_educacion_low_cardinality_year_is_warning_not_error():
    # Reproduce el defecto conocido del año 2023: muchas filas, pocos
    # codigo_dane distintos -> warning, no error.
    df = pl.DataFrame(
        {
            "anio": [2023] * 10,
            "cod_dpto": ["05"] * 10,
            "cod_mpio": ["05001"] * 10,
            "codigo_dane_establecimiento": ["305001000000"] * 10,
            "nombre_establecimiento": [f"COLEGIO {i}" for i in range(10)],
        }
    )
    result = validate_educacion_establecimientos(df)
    assert result.status == "ok"
    assert any("baja" in w and "2023" in w for w in result.warnings)


def test_validate_educacion_warns_on_null_cod_mpio_instead_of_error():
    df = _educacion_df().with_columns(pl.Series("cod_mpio", ["05001", None, "11001"]))
    result = validate_educacion_establecimientos(df)
    assert result.status == "ok"
    assert any("sin cod_mpio" in w for w in result.warnings)


def test_validate_educacion_detects_negative_matricula():
    df = _educacion_df().with_columns(pl.Series("total_matricula", [500, -5, 900]))
    result = validate_educacion_establecimientos(df)
    assert result.status == "error"
    assert any("negativas" in e for e in result.errors)


def test_validate_educacion_empty_dataframe_missing_columns():
    df = pl.DataFrame({"cod_dpto": [], "cod_mpio": []})
    result = validate_educacion_establecimientos(df)
    assert result.status == "error"
    assert "faltan columnas" in result.errors[0]


def test_validate_educacion_warns_on_unknown_mpio():
    result = validate_educacion_establecimientos(
        _educacion_df(), references={"cod_mpio": {"05001"}}
    )
    assert result.status == "ok"
    assert any("no existe en el" in w for w in result.warnings)


def test_validate_educacion_warns_on_fallback_mode():
    result = validate_educacion_establecimientos(
        _educacion_df(),
        {"source_mode": "fallback"},
        references={"cod_mpio": {"05001", "05002", "11001"}},
    )
    assert any("fallback" in w for w in result.warnings)
