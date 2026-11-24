import polars as pl

from src.validation import validate_rethus


def _rethus_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "cod_dpto": ["05", "11", "76"],
            "nombre_dpto": ["ANTIOQUIA", "BOGOTÁ, D.C.", "VALLE DEL CAUCA"],
            "cod_mpio": ["05001", "11001", "76001"],
            "nombre_mpio": ["MEDELLÍN", "BOGOTÁ, D.C.", "CALI"],
            "origen_titulo": ["1 - LOCAL", "1 - LOCAL", "2 - EXTRANJERO"],
            "tipo_institucion": [
                "1 - EDUCACIÓN SUPERIOR",
                "1 - EDUCACIÓN SUPERIOR",
                "1 - EDUCACIÓN SUPERIOR",
            ],
            "tipo_programa": ["UNIVERSITARIA", "UNIVERSITARIA", "ESPECIALIZACIÓN"],
            "perfil_profesional": ["P07 - MEDICINA", "P11 - PSICOLOGÍA", "M03 - DERMATOLOGÍA"],
            "anio_registro": [2016, 2020, 2017],
            "numero_registros": [3188, 2647, 7],
        }
    )


def test_validate_rethus_ok():
    result = validate_rethus(_rethus_df())
    assert result.status == "ok"
    assert result.record_count == 3
    assert result.errors == []
    assert result.warnings == []


def test_validate_rethus_detects_duplicate_primary_key():
    df = pl.concat([_rethus_df(), _rethus_df().head(1)])
    result = validate_rethus(df)
    assert result.status == "error"
    assert any("clave primaria" in e for e in result.errors)


def test_validate_rethus_detects_bad_cod_dpto_width():
    df = _rethus_df().with_columns(pl.Series("cod_dpto", ["5", "11", "76"]))
    result = validate_rethus(df)
    assert result.status == "error"
    assert any("cod_dpto debe tener 2 dígitos" in e for e in result.errors)


def test_validate_rethus_detects_bad_cod_mpio_width():
    df = _rethus_df().with_columns(pl.Series("cod_mpio", ["5001", "11001", "76001"]))
    result = validate_rethus(df)
    assert result.status == "error"
    assert any("cod_mpio debe tener 5 dígitos" in e for e in result.errors)


def test_validate_rethus_detects_cod_mpio_not_matching_cod_dpto():
    df = _rethus_df().with_columns(pl.Series("cod_dpto", ["99", "11", "76"]))
    result = validate_rethus(df)
    assert result.status == "error"
    assert any("no empieza por su cod_dpto" in e for e in result.errors)


def test_validate_rethus_detects_non_positive_numero_registros():
    df = _rethus_df().with_columns(pl.Series("numero_registros", [3188, 0, -1]))
    result = validate_rethus(df)
    assert result.status == "error"
    assert any("> 0" in e for e in result.errors)


def test_validate_rethus_warns_on_implausible_future_year():
    df = _rethus_df().with_columns(pl.Series("anio_registro", [2016, 2020, 2028]))
    result = validate_rethus(df)
    assert result.status == "ok"
    assert any("anio_registro posterior a" in w for w in result.warnings)


def test_validate_rethus_empty_dataframe_is_error_not_traceback():
    result = validate_rethus(_rethus_df().clear())
    assert result.status == "error"
    assert any("vacío" in e for e in result.errors)


def test_validate_rethus_missing_columns_is_error_not_traceback():
    result = validate_rethus(pl.DataFrame({"cod_dpto": []}))
    assert result.status == "error"
    assert any("faltan columnas" in e for e in result.errors)


def test_validate_rethus_live_with_too_few_rows_is_error():
    result = validate_rethus(_rethus_df(), {"source_mode": "live"})
    assert result.status == "error"
    assert any("incompleto" in e for e in result.errors)


def test_validate_rethus_fallback_adds_warning():
    result = validate_rethus(_rethus_df(), {"source_mode": "fallback"})
    assert result.status == "ok"
    assert any("fallback" in w for w in result.warnings)


def test_validate_rethus_reports_unknown_mpio_as_warning():
    result = validate_rethus(_rethus_df(), references={"cod_mpio": {"05001", "11001"}})
    assert result.status == "ok"
    assert any("cod_mpio que no existe" in w for w in result.warnings)
