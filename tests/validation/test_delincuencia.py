import datetime

import polars as pl

from src.validation import validate_delincuencia_hurto_personas


def _hurto_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "fecha": [
                datetime.date(2025, 3, 14),
                datetime.date(2025, 3, 14),
                datetime.date(2025, 3, 15),
            ],
            "anio": [2025, 2025, 2025],
            "cod_dpto": ["05", "11", "05"],
            "nombre_dpto": ["ANTIOQUIA", "BOGOTA D.C.", "ANTIOQUIA"],
            "cod_mpio": ["05001", "11001", "05001"],
            "nombre_mpio": ["MEDELLIN", "BOGOTA D.C.", "MEDELLIN"],
            "cantidad": [74, 482, 60],
        }
    )


def _coverage_df(mpios_per_year: dict[int, int]) -> pl.DataFrame:
    rows = []
    for anio, n in mpios_per_year.items():
        for i in range(n):
            rows.append(
                {
                    "fecha": datetime.date(anio, 1, 1),
                    "anio": anio,
                    "cod_dpto": "05",
                    "cod_mpio": f"05{i:03d}",
                    "cantidad": 1,
                }
            )
    return pl.DataFrame(rows)


def test_validate_hurto_ok():
    result = validate_delincuencia_hurto_personas(
        _hurto_df(), references={"cod_mpio": {"05001", "11001"}}
    )
    assert result.status == "ok"
    assert result.record_count == 3
    assert result.errors == []
    assert result.warnings == []


def test_validate_hurto_detects_duplicate_primary_key():
    df = _hurto_df().with_columns(
        pl.Series("fecha", [datetime.date(2025, 3, 14)] * 3),
    )
    result = validate_delincuencia_hurto_personas(df)
    assert result.status == "error"
    assert any("duplicada" in e for e in result.errors)


def test_validate_hurto_detects_bad_code_width():
    df = _hurto_df().with_columns(pl.Series("cod_mpio", ["5001", "11001", "05001"]))
    result = validate_delincuencia_hurto_personas(df)
    assert result.status == "error"
    assert any("5 dígitos" in e for e in result.errors)


def test_validate_hurto_detects_mpio_not_matching_dpto():
    df = _hurto_df().with_columns(pl.Series("cod_mpio", ["05001", "05001", "05001"]))
    df = df.with_columns(pl.Series("fecha", [datetime.date(2025, 3, d) for d in (13, 14, 15)]))
    result = validate_delincuencia_hurto_personas(df)
    assert result.status == "error"
    assert any("no empieza por su cod_dpto" in e for e in result.errors)


def test_validate_hurto_detects_non_positive_cantidad():
    df = _hurto_df().with_columns(pl.Series("cantidad", [74, 0, -1]))
    result = validate_delincuencia_hurto_personas(df)
    assert result.status == "error"
    assert any("> 0" in e for e in result.errors)


def test_validate_hurto_orphan_mpio_is_warning_not_error():
    result = validate_delincuencia_hurto_personas(_hurto_df(), references={"cod_mpio": {"05001"}})
    assert result.status == "ok"
    assert any("no existe en el municipios vigente" in w for w in result.warnings)


def test_validate_hurto_low_mpio_coverage_year_is_warning():
    # Reproduce el patrón real de 2008 (76 municipios vs. ~850 de mediana).
    df = _coverage_df({2007: 40, 2008: 3, 2009: 40})
    result = validate_delincuencia_hurto_personas(df)
    assert result.status == "ok"
    assert any("año 2008" in w for w in result.warnings)
    assert not any("año 2007" in w for w in result.warnings)


def test_validate_hurto_empty_dataframe_is_error_not_traceback():
    result = validate_delincuencia_hurto_personas(_hurto_df().clear())
    assert result.status == "error"
    assert any("vacío" in e for e in result.errors)


def test_validate_hurto_missing_columns_is_error_not_traceback():
    result = validate_delincuencia_hurto_personas(pl.DataFrame({"fecha": []}))
    assert result.status == "error"
    assert any("faltan columnas" in e for e in result.errors)


def test_validate_hurto_live_with_too_few_rows_is_error():
    result = validate_delincuencia_hurto_personas(_hurto_df(), {"source_mode": "live"})
    assert result.status == "error"
    assert any("incompleto" in e for e in result.errors)


def test_validate_hurto_fallback_adds_warning():
    result = validate_delincuencia_hurto_personas(_hurto_df(), {"source_mode": "fallback"})
    assert result.status == "ok"
    assert any("fallback" in w for w in result.warnings)
