import polars as pl

from src.validation import validate_educacion_establecimientos, validate_educacion_saber11


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


# --- educacion_saber11 ---


def _saber11_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "codigo_dane_establecimiento": ["305001000001", "305002000001", "311001000001"],
            "periodo": ["20194", "20194", "20131"],
            "anio": [2019, 2019, 2013],
            "cod_dpto": ["05", "05", "11"],
            "cod_mpio": ["05001", "05002", "11001"],
            "naturaleza": ["OFICIAL", "NO OFICIAL", "NO OFICIAL"],
            "n_estudiantes": [120, 30, 45],
            "prom_matematicas": [55.2, 48.1, 62.0],
            "prom_ingles": [50.0, 45.0, 58.0],
            "prom_lectura_critica": [52.0, 46.0, None],
            "prom_sociales_ciudadanas": [53.0, 47.0, None],
            "prom_c_naturales": [51.0, 44.0, None],
            "prom_global": [260.0, 230.0, None],
        }
    )


def test_validate_saber11_ok():
    result = validate_educacion_saber11(
        _saber11_df(), references={"cod_mpio": {"05001", "05002", "11001"}}
    )
    assert result.status == "ok"
    assert result.record_count == 3
    assert result.errors == []


def test_validate_saber11_detects_duplicate_primary_key():
    df = pl.concat([_saber11_df(), _saber11_df().head(1)])
    result = validate_educacion_saber11(df)
    assert result.status == "error"
    assert any("duplicada" in e for e in result.errors)


def test_validate_saber11_detects_bad_codigo_dane_width():
    df = _saber11_df().with_columns(
        pl.Series("codigo_dane_establecimiento", ["1", "305002000001", "311001000001"])
    )
    result = validate_educacion_saber11(df)
    assert result.status == "error"
    assert any("12 dígitos" in e for e in result.errors)


def test_validate_saber11_detects_non_positive_n_estudiantes():
    df = _saber11_df().with_columns(pl.Series("n_estudiantes", [120, 0, -1]))
    result = validate_educacion_saber11(df)
    assert result.status == "error"
    assert any("> 0" in e for e in result.errors)


def test_validate_saber11_detects_negative_promedio():
    df = _saber11_df().with_columns(pl.Series("prom_matematicas", [55.2, -1.0, 62.0]))
    result = validate_educacion_saber11(df)
    assert result.status == "error"
    assert any("prom_matematicas" in e and "negativas" in e for e in result.errors)


def test_validate_saber11_null_promedios_pre_reforma_is_ok_not_error():
    # Fila de periodo 20131 (pre-reforma): prom_global y los otros 3 son
    # null por diseño, no es un error — ver docstring del extractor.
    result = validate_educacion_saber11(_saber11_df())
    assert result.status == "ok"


def test_validate_saber11_null_naturaleza_is_warning():
    df = _saber11_df().with_columns(pl.Series("naturaleza", ["OFICIAL", None, "NO OFICIAL"]))
    result = validate_educacion_saber11(df)
    assert result.status == "ok"
    assert any("naturaleza nula" in w for w in result.warnings)


def test_validate_saber11_warns_on_unknown_mpio():
    result = validate_educacion_saber11(_saber11_df(), references={"cod_mpio": {"05001"}})
    assert result.status == "ok"
    assert any("no existe en el" in w for w in result.warnings)


def test_validate_saber11_empty_dataframe_is_error_not_traceback():
    result = validate_educacion_saber11(_saber11_df().clear())
    assert result.status == "error"
    assert any("vacío" in e for e in result.errors)


def test_validate_saber11_missing_columns_is_error_not_traceback():
    result = validate_educacion_saber11(pl.DataFrame({"codigo_dane_establecimiento": []}))
    assert result.status == "error"
    assert "faltan columnas" in result.errors[0]


def test_validate_saber11_live_with_too_few_rows_is_error():
    result = validate_educacion_saber11(_saber11_df(), {"source_mode": "live"})
    assert result.status == "error"
    assert any("incompleto" in e for e in result.errors)


def test_validate_saber11_fallback_adds_warning():
    result = validate_educacion_saber11(_saber11_df(), {"source_mode": "fallback"})
    assert any("fallback" in w for w in result.warnings)
