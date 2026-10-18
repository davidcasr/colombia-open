import polars as pl

from src.validation import validate_demografia


def _demografia_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "cod_dpto": ["05", "05", "11"],
            "nombre_dpto": ["ANTIOQUIA", "ANTIOQUIA", "BOGOTÁ, D.C."],
            "cod_mpio": ["05001", "05001", "11001"],
            "nombre_mpio": ["MEDELLÍN", "MEDELLÍN", "BOGOTÁ, D.C."],
            "anio": [2018, 2019, 2018],
            "area_geografica": ["Total", "Total", "Total"],
            "poblacion": [2427133, 2450000, 7181469],
        }
    )


def test_validate_demografia_ok():
    result = validate_demografia(_demografia_df(), references={"cod_mpio": {"05001", "11001"}})
    assert result.status == "ok"
    assert result.record_count == 3
    assert result.errors == []


def test_validate_demografia_detects_duplicate_composite_key():
    df = pl.concat([_demografia_df(), _demografia_df().head(1)])
    result = validate_demografia(df)
    assert result.status == "error"
    assert any("duplicados" in e for e in result.errors)


def test_validate_demografia_detects_bad_code_width():
    df = _demografia_df().with_columns(pl.Series("cod_mpio", ["5001", "05001", "11001"]))
    result = validate_demografia(df)
    assert result.status == "error"
    assert any("5 dígitos" in e for e in result.errors)


def test_validate_demografia_detects_invalid_area_geografica():
    df = _demografia_df().with_columns(
        pl.Series("area_geografica", ["Total", "Total", "Valor inesperado"])
    )
    result = validate_demografia(df)
    assert result.status == "error"
    assert any("area_geografica" in e for e in result.errors)


def test_validate_demografia_detects_negative_poblacion():
    df = _demografia_df().with_columns(pl.Series("poblacion", [2427133, -1, 7181469]))
    result = validate_demografia(df)
    assert result.status == "error"
    assert any("negativas" in e for e in result.errors)


def test_validate_demografia_empty_dataframe_missing_columns():
    df = pl.DataFrame({"cod_dpto": [], "cod_mpio": []})
    result = validate_demografia(df)
    assert result.status == "error"
    assert "faltan columnas" in result.errors[0]


def test_validate_demografia_warns_on_unknown_mpio_instead_of_error():
    result = validate_demografia(_demografia_df(), references={"cod_mpio": {"05001"}})
    assert result.status == "ok"
    assert any("no existe en el" in w for w in result.warnings)


def test_validate_demografia_warns_on_fallback_mode():
    result = validate_demografia(
        _demografia_df(),
        {"source_mode": "fallback"},
        references={"cod_mpio": {"05001", "11001"}},
    )
    assert any("fallback" in w for w in result.warnings)
