import polars as pl
import pytest

import src.extractors.base as base_module
import src.extractors.educacion_saber11_extractor as saber11_module
from src.extractors.educacion_saber11_extractor import (
    EDUCACION_SABER11_FALLBACK_DATA,
    PRIMARY_KEY,
    EducacionSaber11Extractor,
    _normalize,
    _parse_float,
)


def _row(**overrides: str | None) -> dict[str, str | None]:
    row: dict[str, str | None] = {
        "periodo": "20194",
        "cole_cod_dane_establecimiento": "141016000305",
        "cole_cod_depto_ubicacion": "41",
        "cole_cod_mcpio_ubicacion": "41016",
        "cole_naturaleza": "OFICIAL",
        "punt_matematicas": "66",
        "punt_ingles": "71",
        "punt_lectura_critica": "69",
        "punt_sociales_ciudadanas": "70",
        "punt_c_naturales": "65",
        "punt_global": "339",
    }
    row.update(overrides)
    return row


def test_parse_float_handles_blank_and_missing():
    assert _parse_float("66") == 66.0
    assert _parse_float("") is None
    assert _parse_float(None) is None


def test_normalize_fallback_rows_have_fixed_width_codes():
    df, _excluded, skipped = _normalize(EDUCACION_SABER11_FALLBACK_DATA)
    assert skipped == 0
    assert all(len(c) == 2 for c in df["cod_dpto"].to_list())
    assert all(len(c) == 5 for c in df["cod_mpio"].to_list())
    assert all(len(c) == 12 for c in df["codigo_dane_establecimiento"].to_list())


def test_normalize_primary_key_is_unique():
    df, _excluded, _skipped = _normalize(EDUCACION_SABER11_FALLBACK_DATA)
    assert df.select(PRIMARY_KEY).unique().height == df.height


def test_normalize_excludes_rows_without_establecimiento_or_municipio():
    df, excluded, _skipped = _normalize(
        [
            _row(),
            _row(cole_cod_dane_establecimiento=None),
            _row(cole_cod_mcpio_ubicacion=None),
        ]
    )
    assert excluded == 2
    assert df.height == 1


def test_normalize_averages_and_counts_students_in_same_establecimiento_periodo():
    rows = [
        _row(punt_matematicas="60", punt_global="300"),
        _row(punt_matematicas="80", punt_global="340"),
    ]
    df, _excluded, _skipped = _normalize(rows)
    assert df.height == 1
    row = df.row(0, named=True)
    assert row["n_estudiantes"] == 2
    assert row["prom_matematicas"] == 70.0
    assert row["prom_global"] == 320.0


def test_normalize_keeps_legacy_scores_null_for_fields_not_reported_pre_reforma():
    df, _excluded, _skipped = _normalize(
        [
            {
                "periodo": "20131",
                "cole_cod_dane_establecimiento": "311848000812",
                "cole_cod_depto_ubicacion": "11",
                "cole_cod_mcpio_ubicacion": "11001",
                "cole_naturaleza": "NO OFICIAL",
                "punt_matematicas": "88",
                "punt_ingles": "94",
            }
        ]
    )
    row = df.row(0, named=True)
    assert row["prom_matematicas"] == 88.0
    assert row["prom_ingles"] == 94.0
    assert row["prom_global"] is None
    assert row["prom_lectura_critica"] is None


def test_normalize_derives_anio_from_periodo():
    df, _excluded, _skipped = _normalize([_row(periodo="20162")])
    assert df["anio"].to_list() == [2016]


def test_normalize_skips_rows_missing_periodo_instead_of_raising():
    rows = [_row(), {"cole_cod_dane_establecimiento": "141016000305"}]
    df, _excluded, skipped = _normalize(rows)
    assert skipped == 1
    assert df.height == 1


def test_normalize_empty_input_returns_empty_frame_with_schema():
    df, excluded, skipped = _normalize([])
    assert df.height == 0
    assert (excluded, skipped) == (0, 0)
    assert df.schema["codigo_dane_establecimiento"] == pl.Utf8


def test_extractor_dry_run_never_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(base_module, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(base_module, "STAGING_DIR", tmp_path / "staging")
    monkeypatch.setattr(saber11_module, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(saber11_module, "STAGING_DIR", tmp_path / "staging")
    monkeypatch.setattr(saber11_module, "ROOT_DIR", tmp_path)

    monkeypatch.setattr(saber11_module, "_fetch_all_rows", lambda: EDUCACION_SABER11_FALLBACK_DATA)

    result = EducacionSaber11Extractor().run(dry_run=True)

    assert result.dataset == "educacion_saber11"
    assert result.source_mode == "live"
    assert not (tmp_path / "staging" / "educacion_saber11.csv").exists()
    assert not (tmp_path / "staging" / "educacion_saber11.metadata.json").exists()


def test_fetch_falls_back_on_expected_source_failure(monkeypatch):
    def _bad_payload() -> None:
        raise ValueError("JSON con forma inesperada")

    monkeypatch.setattr(saber11_module, "_fetch_all_rows", _bad_payload)

    result = EducacionSaber11Extractor().fetch()
    assert result.source_mode == "fallback"
    assert result.dataframe.height > 0


def test_fetch_propagates_unexpected_bugs_instead_of_hiding_as_fallback(monkeypatch):
    def _broken_fetch_all_rows() -> None:
        raise AttributeError("bug de programación simulado, no una falla de red")

    monkeypatch.setattr(saber11_module, "_fetch_all_rows", _broken_fetch_all_rows)

    with pytest.raises(AttributeError):
        EducacionSaber11Extractor().fetch()
