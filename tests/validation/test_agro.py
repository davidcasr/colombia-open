import polars as pl

from src.validation import validate_agro_eva


def _agro_df() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "cod_dpto": ["05", "25", "76"],
            "nombre_dpto": ["Antioquia", "CUNDINAMARCA", "Valle del Cauca"],
            "cod_mpio": ["05001", "25754", "76001"],
            "nombre_mpio": ["Medellín", "SOACHA", "Santiago de Cali"],
            "cultivo": ["Apio", "ACELGA", "Acelga"],
            "cultivo_clean": ["apio", "acelga", "acelga"],
            "desagregacion_cultivo": ["Apio", "ACELGA", "Acelga"],
            "anio": pl.Series([2021, 2006, 2019], dtype=pl.Int32),
            "periodo": ["2021A", "2006B", "2019A"],
            "area_sembrada_ha": [8.0, 82.0, 3.0],
            "area_cosechada_ha": [8.0, 80.0, 3.0],
            "produccion_t": [128.0, 1440.0, 12.0],
            "rendimiento_t_ha": [16.0, 18.0, 4.0],
            "serie_fuente": ["upra_2019_2025", "minagricultura_2006_2018", "upra_2019_2025"],
        }
    )


def test_validate_agro_eva_ok():
    result = validate_agro_eva(_agro_df())
    assert result.status == "ok"
    assert result.record_count == 3
    assert result.errors == []
    assert result.warnings == []


def test_validate_agro_eva_detects_duplicate_primary_key():
    result = validate_agro_eva(pl.concat([_agro_df(), _agro_df().head(1)]))
    assert result.status == "error"
    assert any("clave primaria" in e for e in result.errors)


def test_validate_agro_eva_detects_bad_cod_dpto_width():
    df = _agro_df().with_columns(pl.Series("cod_dpto", ["5", "25", "76"]))
    result = validate_agro_eva(df)
    assert result.status == "error"
    assert any("cod_dpto debe tener 2 dígitos" in e for e in result.errors)


def test_validate_agro_eva_detects_bad_cod_mpio_width():
    df = _agro_df().with_columns(pl.Series("cod_mpio", ["5001", "25754", "76001"]))
    result = validate_agro_eva(df)
    assert result.status == "error"
    assert any("cod_mpio debe tener 5 dígitos" in e for e in result.errors)


def test_validate_agro_eva_detects_cod_mpio_not_matching_cod_dpto():
    df = _agro_df().with_columns(pl.Series("cod_dpto", ["99", "25", "76"]))
    result = validate_agro_eva(df)
    assert result.status == "error"
    assert any("no empieza por su cod_dpto" in e for e in result.errors)


def test_validate_agro_eva_detects_negative_measure():
    df = _agro_df().with_columns(pl.Series("produccion_t", [128.0, -1.0, 12.0]))
    result = validate_agro_eva(df)
    assert result.status == "error"
    assert any("produccion_t debe ser >= 0" in e for e in result.errors)


def test_validate_agro_eva_detects_null_measure():
    df = _agro_df().with_columns(pl.Series("produccion_t", [128.0, None, 12.0]))
    result = validate_agro_eva(df)
    assert result.status == "error"
    assert any("produccion_t es nulo" in e for e in result.errors)


def test_validate_agro_eva_null_yield_with_harvest_is_error():
    df = _agro_df().with_columns(pl.Series("rendimiento_t_ha", [16.0, None, 4.0]))
    result = validate_agro_eva(df)
    assert result.status == "error"
    assert any("rendimiento_t_ha es nulo" in e for e in result.errors)


def test_validate_agro_eva_null_yield_without_harvest_is_ok():
    # Convención MinAgricultura: nada cosechado -> rendimiento ausente (0/0).
    df = _agro_df().with_columns(
        pl.Series("area_cosechada_ha", [8.0, 0.0, 3.0]),
        pl.Series("produccion_t", [128.0, 0.0, 12.0]),
        pl.Series("rendimiento_t_ha", [16.0, None, 4.0]),
    )
    result = validate_agro_eva(df)
    assert result.status == "ok"
    assert result.warnings == []


def test_validate_agro_eva_warns_on_yield_without_harvested_area():
    df = _agro_df().with_columns(
        pl.Series("area_cosechada_ha", [8.0, 0.0, 3.0]),
        pl.Series("produccion_t", [128.0, 0.0, 12.0]),
    )
    result = validate_agro_eva(df)
    assert result.status == "ok"
    assert any("area_cosechada_ha = 0" in w for w in result.warnings)


def test_validate_agro_eva_detects_periodo_not_matching_anio():
    df = _agro_df().with_columns(pl.Series("periodo", ["2020A", "2006B", "2019A"]))
    result = validate_agro_eva(df)
    assert result.status == "error"
    assert any("periodo que no empieza por su anio" in e for e in result.errors)


def test_validate_agro_eva_detects_unknown_serie_fuente():
    df = _agro_df().with_columns(
        pl.Series("serie_fuente", ["upra_2019_2025", "otra_serie", "upra_2019_2025"])
    )
    result = validate_agro_eva(df)
    assert result.status == "error"
    assert any("serie_fuente" in e for e in result.errors)


def test_validate_agro_eva_detects_year_present_in_both_series():
    df = _agro_df().with_columns(
        pl.Series(
            "serie_fuente",
            ["upra_2019_2025", "minagricultura_2006_2018", "minagricultura_2006_2018"],
        )
    )
    # 2019 queda en MinAgricultura y otra fila de 2019 en UPRA -> doble conteo.
    df = pl.concat(
        [
            df,
            df.filter(pl.col("anio") == 2019).with_columns(
                pl.lit("upra_2019_2025").alias("serie_fuente"),
                pl.lit("Apio").alias("cultivo"),
            ),
        ]
    )
    result = validate_agro_eva(df)
    assert result.status == "error"
    assert any("ambas series" in e for e in result.errors)


def test_validate_agro_eva_warns_on_harvested_over_planted_area():
    df = _agro_df().with_columns(pl.Series("area_cosechada_ha", [8.0, 80.0, 30.0]))
    result = validate_agro_eva(df)
    assert result.status == "ok"
    assert any("area_cosechada_ha > area_sembrada_ha" in w for w in result.warnings)


def test_validate_agro_eva_empty_dataframe_is_error_not_traceback():
    result = validate_agro_eva(_agro_df().clear())
    assert result.status == "error"
    assert any("vacío" in e for e in result.errors)


def test_validate_agro_eva_missing_columns_is_error_not_traceback():
    result = validate_agro_eva(pl.DataFrame({"cod_dpto": []}))
    assert result.status == "error"
    assert any("faltan columnas" in e for e in result.errors)


def test_validate_agro_eva_live_with_too_few_rows_is_error():
    result = validate_agro_eva(_agro_df(), {"source_mode": "live"})
    assert result.status == "error"
    assert any("incompleto" in e for e in result.errors)


def test_validate_agro_eva_fallback_adds_warning():
    result = validate_agro_eva(_agro_df(), {"source_mode": "fallback"})
    assert result.status == "ok"
    assert any("fallback" in w for w in result.warnings)


def test_validate_agro_eva_reports_unknown_mpio_as_warning():
    result = validate_agro_eva(_agro_df(), references={"cod_mpio": {"05001", "25754"}})
    assert result.status == "ok"
    assert any("cod_mpio que no existe" in w for w in result.warnings)
