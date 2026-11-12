import datetime

import polars as pl
import pytest

import src.extractors.base as base_module
import src.extractors.delincuencia_homicidios_extractor as homicidios_module
from src.extractors.delincuencia_homicidios_extractor import (
    DELINCUENCIA_HOMICIDIOS_FALLBACK_DATA,
    PRIMARY_KEY,
    DelincuenciaHomicidiosExtractor,
    _normalize,
)


def _row(**overrides: str | None) -> dict[str, str | None]:
    row: dict[str, str | None] = {
        "fecha_hecho": "2025-03-14T00:00:00.000",
        "cod_depto": "05",
        "departamento": "ANTIOQUIA",
        "cod_muni": "05001",
        "municipio": "MEDELLIN",
        "zona": "URBANA",
        "sexo": "MASCULINO",
        "arma_medio": "ARMA DE FUEGO",
        "_modalidad_presunta": "SICARIATO",
        "spoa_caracterizacion": "HOMICIDIO INTENCIONAL O CON DOLO",
        "cantidad": "1",
    }
    row.update(overrides)
    return row


def test_normalize_fallback_rows_have_fixed_width_codes():
    df, _excluded, _victims, skipped = _normalize(DELINCUENCIA_HOMICIDIOS_FALLBACK_DATA)
    assert skipped == 0
    assert all(len(c) == 2 for c in df["cod_dpto"].to_list())
    assert all(len(c) == 5 for c in df["cod_mpio"].to_list())


def test_normalize_pads_codes_that_lost_leading_zero():
    df, _excluded, _victims, _skipped = _normalize([_row(cod_depto="5", cod_muni="5001")])
    assert df["cod_dpto"].to_list() == ["05"]
    assert df["cod_mpio"].to_list() == ["05001"]


def test_normalize_sums_rows_repeated_in_every_dimension():
    # La fuente repite filas idénticas (una por víctima): se suman, no se pierden.
    df, _excluded, _victims, _skipped = _normalize([_row(), _row(cantidad="2")])
    assert df.height == 1
    assert df["cantidad"].to_list() == [3]


def test_normalize_keeps_rows_that_differ_in_one_dimension():
    df, _excluded, _victims, _skipped = _normalize([_row(), _row(sexo="FEMENINO")])
    assert df.height == 2


def test_normalize_primary_key_is_unique_and_victims_preserved():
    df, excluded, victims, _skipped = _normalize(DELINCUENCIA_HOMICIDIOS_FALLBACK_DATA)
    assert df.select(PRIMARY_KEY).unique().height == df.height
    total = sum(int(r["cantidad"]) for r in DELINCUENCIA_HOMICIDIOS_FALLBACK_DATA)
    assert df["cantidad"].sum() + victims == total
    assert excluded == 1


def test_normalize_excludes_rows_without_municipio_and_counts_victims():
    df, excluded, victims, skipped = _normalize(
        [_row(), _row(cod_muni="SIN ESTABLECER", cantidad="3"), _row(cod_muni=None)]
    )
    assert excluded == 2
    assert victims == 4
    assert skipped == 0
    assert df["cod_mpio"].to_list() == ["05001"]


def test_normalize_strips_capital_suffix_from_nombre_mpio():
    df, _excluded, _victims, _skipped = _normalize([_row(municipio="MEDELLÍN (CT)")])
    assert df["nombre_mpio"].to_list() == ["MEDELLÍN"]


def test_normalize_uses_most_frequent_name_per_code():
    rows = [
        _row(municipio="MEDELLIN"),
        _row(municipio="MEDELLIN", fecha_hecho="2025-03-15T00:00:00.000"),
        _row(municipio="MEDELLÍN (CT)", fecha_hecho="2025-03-16T00:00:00.000"),
    ]
    df, _excluded, _victims, _skipped = _normalize(rows)
    assert set(df["nombre_mpio"].to_list()) == {"MEDELLIN"}


def test_normalize_parses_fecha_anio_and_cantidad():
    df, _excluded, _victims, _skipped = _normalize([_row(cantidad="4")])
    row = df.row(0, named=True)
    assert row["fecha"] == datetime.date(2025, 3, 14)
    assert row["anio"] == 2025
    assert row["cantidad"] == 4


def test_normalize_renames_source_dimensions():
    df, _excluded, _victims, _skipped = _normalize([_row(spoa_caracterizacion="FEMINICIDIO")])
    row = df.row(0, named=True)
    assert row["modalidad_presunta"] == "SICARIATO"
    assert row["caracterizacion"] == "FEMINICIDIO"


@pytest.mark.parametrize("value", [None, "", "   "])
def test_normalize_keeps_missing_arma_and_modalidad_as_null(value):
    df, _excluded, _victims, _skipped = _normalize(
        [_row(arma_medio=value, _modalidad_presunta=value)]
    )
    assert df["arma_medio"].to_list() == [None]
    assert df["modalidad_presunta"].to_list() == [None]


def test_normalize_skips_unparseable_rows_instead_of_raising():
    df, _excluded, _victims, skipped = _normalize(
        [_row(), _row(fecha_hecho="no-es-fecha"), _row(cantidad=None), _row(cod_depto=None)]
    )
    assert skipped == 3
    assert df.height == 1


def test_normalize_empty_input_returns_empty_frame_with_schema():
    df, excluded, victims, skipped = _normalize([])
    assert df.height == 0
    assert (excluded, victims, skipped) == (0, 0, 0)
    assert df.schema["cod_mpio"] == pl.Utf8


def test_extractor_dry_run_never_writes(tmp_path, monkeypatch):
    # Ver test_divipola_extractor.py: hay que parchear los paths tanto en
    # base.py como en el módulo del extractor.
    monkeypatch.setattr(base_module, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(base_module, "STAGING_DIR", tmp_path / "staging")
    monkeypatch.setattr(homicidios_module, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(homicidios_module, "STAGING_DIR", tmp_path / "staging")
    monkeypatch.setattr(homicidios_module, "ROOT_DIR", tmp_path)

    monkeypatch.setattr(
        homicidios_module,
        "_fetch_all_rows",
        lambda: DELINCUENCIA_HOMICIDIOS_FALLBACK_DATA,
    )

    result = DelincuenciaHomicidiosExtractor().run(dry_run=True)

    assert result.dataset == "delincuencia_homicidios"
    assert result.source_mode == "live"
    assert any("sin municipio" in note or "no tener municipio" in note for note in result.notes)
    assert not (tmp_path / "staging" / "delincuencia_homicidios.csv").exists()
    assert not (tmp_path / "staging" / "delincuencia_homicidios.metadata.json").exists()


def test_fetch_falls_back_on_expected_source_failure(monkeypatch):
    def _bad_payload() -> None:
        raise ValueError("JSON con forma inesperada")

    monkeypatch.setattr(homicidios_module, "_fetch_all_rows", _bad_payload)

    result = DelincuenciaHomicidiosExtractor().fetch()
    assert result.source_mode == "fallback"
    assert result.dataframe.height > 0


def test_fetch_propagates_unexpected_bugs_instead_of_hiding_as_fallback(monkeypatch):
    def _broken_fetch_all_rows() -> None:
        raise AttributeError("bug de programación simulado, no una falla de red")

    monkeypatch.setattr(homicidios_module, "_fetch_all_rows", _broken_fetch_all_rows)

    with pytest.raises(AttributeError):
        DelincuenciaHomicidiosExtractor().fetch()
