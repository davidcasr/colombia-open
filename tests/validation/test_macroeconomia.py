import datetime

import polars as pl

from src.validation import validate_macroeconomia_trm


def _trm_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "fecha": [
                datetime.date(2026, 10, 20),
                datetime.date(2026, 10, 21),
                datetime.date(2026, 10, 22),
            ],
            "vigente_hasta": [
                datetime.date(2026, 10, 20),
                datetime.date(2026, 10, 21),
                datetime.date(2026, 10, 22),
            ],
            "trm": [3156.32, 3163.76, 3191.47],
        }
    )


def test_validate_trm_ok():
    result = validate_macroeconomia_trm(_trm_df())
    assert result.status == "ok"
    assert result.record_count == 3
    assert result.errors == []
    assert result.warnings == []


def test_validate_trm_detects_duplicate_fecha():
    df = pl.concat([_trm_df(), _trm_df().head(1)])
    result = validate_macroeconomia_trm(df)
    assert result.status == "error"
    assert any("única" in e for e in result.errors)


def test_validate_trm_detects_non_positive_trm():
    df = _trm_df().with_columns(pl.Series("trm", [3156.32, 0.0, -1.0]))
    result = validate_macroeconomia_trm(df)
    assert result.status == "error"
    assert any("> 0" in e for e in result.errors)


def test_validate_trm_detects_inverted_vigencia_range():
    df = _trm_df().with_columns(
        pl.Series(
            "vigente_hasta",
            [datetime.date(2026, 10, 19), datetime.date(2026, 10, 21), datetime.date(2026, 10, 22)],
        )
    )
    result = validate_macroeconomia_trm(df)
    assert result.status == "error"
    assert any("anterior a fecha" in e for e in result.errors)


def test_validate_trm_empty_dataframe_is_error_not_traceback():
    result = validate_macroeconomia_trm(_trm_df().clear())
    assert result.status == "error"
    assert any("vacío" in e for e in result.errors)


def test_validate_trm_missing_columns_is_error_not_traceback():
    result = validate_macroeconomia_trm(pl.DataFrame({"fecha": []}))
    assert result.status == "error"
    assert any("faltan columnas" in e for e in result.errors)


def test_validate_trm_live_with_too_few_rows_is_error():
    result = validate_macroeconomia_trm(_trm_df(), {"source_mode": "live"})
    assert result.status == "error"
    assert any("incompleto" in e for e in result.errors)


def test_validate_trm_fallback_adds_warning():
    result = validate_macroeconomia_trm(_trm_df(), {"source_mode": "fallback"})
    assert result.status == "ok"
    assert any("fallback" in w for w in result.warnings)
