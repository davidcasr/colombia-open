import polars as pl

from src.validation import validate_calidad_aire


def _aire_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "id_estacion": ["9020", "9020", "9049"],
            "contaminante": ["PM10", "O3", "PM10"],
            "tiempo_exposicion_horas": [24, 8, 24],
            "anio": [2022, 2022, 2011],
            "cod_dpto": ["05", "05", "20"],
            "cod_mpio": ["05001", "05001", "20621"],
            "promedio": [17.5, 28.4, 17.5],
            "representatividad_temporal": [85.0, 81.0, 53.0],
        }
    )


def test_validate_aire_ok():
    result = validate_calidad_aire(_aire_df(), references={"cod_mpio": {"05001", "20621"}})
    assert result.status == "ok"
    assert result.record_count == 3
    assert result.errors == []
    assert result.warnings == []


def test_validate_aire_detects_duplicate_primary_key():
    df = pl.concat([_aire_df(), _aire_df().head(1)])
    result = validate_calidad_aire(df)
    assert result.status == "error"
    assert any("duplicada" in e for e in result.errors)


def test_validate_aire_detects_bad_code_width():
    df = _aire_df().with_columns(pl.Series("cod_mpio", ["5001", "05001", "20621"]))
    result = validate_calidad_aire(df)
    assert result.status == "error"
    assert any("5 dígitos" in e for e in result.errors)


def test_validate_aire_detects_invalid_contaminante():
    df = _aire_df().with_columns(pl.Series("contaminante", ["PM10", "RUVb", "PM10"]))
    result = validate_calidad_aire(df)
    assert result.status == "error"
    assert any("contaminante" in e for e in result.errors)


def test_validate_aire_detects_negative_promedio():
    df = _aire_df().with_columns(pl.Series("promedio", [17.5, -1.0, 17.5]))
    result = validate_calidad_aire(df)
    assert result.status == "error"
    assert any("negativas" in e for e in result.errors)


def test_validate_aire_representatividad_out_of_range_is_warning():
    df = _aire_df().with_columns(pl.Series("representatividad_temporal", [85.0, 150.0, 53.0]))
    result = validate_calidad_aire(df)
    assert result.status == "ok"
    assert any("representatividad_temporal" in w for w in result.warnings)


def test_validate_aire_orphan_mpio_is_warning_not_error():
    result = validate_calidad_aire(_aire_df(), references={"cod_mpio": {"05001"}})
    assert result.status == "ok"
    assert any("no existe en el municipios vigente" in w for w in result.warnings)


def test_validate_aire_empty_dataframe_is_error_not_traceback():
    result = validate_calidad_aire(_aire_df().clear())
    assert result.status == "error"
    assert any("vacío" in e for e in result.errors)


def test_validate_aire_missing_columns_is_error_not_traceback():
    result = validate_calidad_aire(pl.DataFrame({"id_estacion": []}))
    assert result.status == "error"
    assert any("faltan columnas" in e for e in result.errors)


def test_validate_aire_live_with_too_few_rows_is_error():
    result = validate_calidad_aire(_aire_df(), {"source_mode": "live"})
    assert result.status == "error"
    assert any("incompleto" in e for e in result.errors)


def test_validate_aire_fallback_adds_warning():
    result = validate_calidad_aire(_aire_df(), {"source_mode": "fallback"})
    assert result.status == "ok"
    assert any("fallback" in w for w in result.warnings)
