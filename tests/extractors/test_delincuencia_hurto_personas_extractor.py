import datetime

import pytest

import src.extractors.base as base_module
import src.extractors.delincuencia_hurto_personas_extractor as hurto_module
from src.extractors.delincuencia_hurto_personas_extractor import (
    DELINCUENCIA_HURTO_PERSONAS_FALLBACK_DATA,
    DelincuenciaHurtoPersonasExtractor,
    _normalize,
)


def test_normalize_fallback_rows_have_fixed_width_codes():
    df, _excluded, _victims, skipped = _normalize(DELINCUENCIA_HURTO_PERSONAS_FALLBACK_DATA)
    assert skipped == 0
    assert all(len(c) == 2 for c in df["cod_dpto"].to_list())
    assert all(len(c) == 5 for c in df["cod_mpio"].to_list())


def test_normalize_pads_codes_that_lost_leading_zero():
    rows = [
        {
            "fecha_hecho": "2025-03-14T00:00:00.000",
            "cod_depto": "5",
            "departamento": "ANTIOQUIA",
            "cod_muni": "5001",
            "municipio": "MEDELLIN",
            "cantidad": "74",
        }
    ]
    df, _excluded, _victims, _skipped = _normalize(rows)
    assert df["cod_dpto"].to_list() == ["05"]
    assert df["cod_mpio"].to_list() == ["05001"]


def test_normalize_excludes_sin_establecer_and_counts_victims():
    df, excluded, victims, skipped = _normalize(DELINCUENCIA_HURTO_PERSONAS_FALLBACK_DATA)
    assert excluded == 1
    assert victims == 221
    assert skipped == 0
    assert df.height == len(DELINCUENCIA_HURTO_PERSONAS_FALLBACK_DATA) - 1
    assert "SIN ESTABLECER" not in df["cod_mpio"].to_list()


def test_normalize_parses_fecha_anio_and_cantidad():
    df, _excluded, _victims, _skipped = _normalize(DELINCUENCIA_HURTO_PERSONAS_FALLBACK_DATA)
    bogota = df.filter(df["cod_mpio"] == "11001").row(0, named=True)
    assert bogota["fecha"] == datetime.date(2025, 3, 14)
    assert bogota["anio"] == 2025
    assert bogota["cantidad"] == 482


def test_normalize_skips_row_missing_required_field_instead_of_raising():
    rows = [*DELINCUENCIA_HURTO_PERSONAS_FALLBACK_DATA, {"cod_muni": "05001", "cod_depto": "05"}]
    df, _excluded, _victims, skipped = _normalize(rows)
    assert skipped == 1
    assert df.height == len(DELINCUENCIA_HURTO_PERSONAS_FALLBACK_DATA) - 1


def test_extractor_dry_run_never_writes(tmp_path, monkeypatch):
    # Ver test_divipola_extractor.py: hay que parchear los paths tanto en
    # base.py como en el módulo del extractor.
    monkeypatch.setattr(base_module, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(base_module, "STAGING_DIR", tmp_path / "staging")
    monkeypatch.setattr(hurto_module, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(hurto_module, "STAGING_DIR", tmp_path / "staging")
    monkeypatch.setattr(hurto_module, "ROOT_DIR", tmp_path)

    monkeypatch.setattr(
        hurto_module, "_fetch_all_rows", lambda: DELINCUENCIA_HURTO_PERSONAS_FALLBACK_DATA
    )

    result = DelincuenciaHurtoPersonasExtractor().run(dry_run=True)

    assert result.dataset == "delincuencia_hurto_personas"
    assert result.source_mode == "live"
    assert any("SIN ESTABLECER" in note for note in result.notes)
    assert not (tmp_path / "staging" / "delincuencia_hurto_personas.csv").exists()
    assert not (tmp_path / "staging" / "delincuencia_hurto_personas.metadata.json").exists()


def test_fetch_falls_back_on_expected_source_failure(monkeypatch):
    def _bad_payload() -> None:
        raise ValueError("JSON con forma inesperada")

    monkeypatch.setattr(hurto_module, "_fetch_all_rows", _bad_payload)

    result = DelincuenciaHurtoPersonasExtractor().fetch()
    assert result.source_mode == "fallback"
    assert result.dataframe.height == len(DELINCUENCIA_HURTO_PERSONAS_FALLBACK_DATA) - 1


def test_fetch_propagates_unexpected_bugs_instead_of_hiding_as_fallback(monkeypatch):
    def _broken_fetch_all_rows() -> None:
        raise AttributeError("bug de programación simulado, no una falla de red")

    monkeypatch.setattr(hurto_module, "_fetch_all_rows", _broken_fetch_all_rows)

    with pytest.raises(AttributeError):
        DelincuenciaHurtoPersonasExtractor().fetch()
