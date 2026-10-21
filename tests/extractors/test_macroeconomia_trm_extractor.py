import datetime

import pytest

import src.extractors.base as base_module
import src.extractors.macroeconomia_trm_extractor as trm_module
from src.extractors.macroeconomia_trm_extractor import (
    MACROECONOMIA_TRM_FALLBACK_DATA,
    MacroeconomiaTrmExtractor,
    _normalize,
)


def _row(**overrides: str) -> dict[str, str]:
    row: dict[str, str] = {
        "valor": "3191.47",
        "unidad": "COP",
        "vigenciadesde": "2026-10-22T00:00:00.000",
        "vigenciahasta": "2026-10-22T00:00:00.000",
    }
    row.update(overrides)
    return row


def test_normalize_fallback_rows_parse_correctly():
    df, skipped = _normalize(MACROECONOMIA_TRM_FALLBACK_DATA)
    assert skipped == 0
    assert df.height == len(MACROECONOMIA_TRM_FALLBACK_DATA)
    assert df["trm"].null_count() == 0


def test_normalize_handles_multi_day_vigencia():
    df, _skipped = _normalize(
        [_row(vigenciadesde="2026-10-17T00:00:00.000", vigenciahasta="2026-10-19T00:00:00.000")]
    )
    row = df.row(0, named=True)
    assert row["fecha"] == datetime.date(2026, 10, 17)
    assert row["vigente_hasta"] == datetime.date(2026, 10, 19)


def test_normalize_parses_valor_as_float():
    df, _skipped = _normalize([_row(valor="3156.32")])
    assert df["trm"].to_list() == [3156.32]


def test_normalize_fecha_is_unique_in_fallback_sample():
    df, _skipped = _normalize(MACROECONOMIA_TRM_FALLBACK_DATA)
    assert df["fecha"].n_unique() == df.height


def test_normalize_skips_rows_missing_required_field_instead_of_raising():
    rows = [_row(), {"valor": "100"}]
    df, skipped = _normalize(rows)
    assert skipped == 1
    assert df.height == 1


def test_normalize_empty_input_returns_empty_frame_with_schema():
    import polars as pl

    df, skipped = _normalize([])
    assert df.height == 0
    assert skipped == 0
    assert df.schema["trm"] == pl.Float64


def test_extractor_dry_run_never_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(base_module, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(base_module, "STAGING_DIR", tmp_path / "staging")
    monkeypatch.setattr(trm_module, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(trm_module, "STAGING_DIR", tmp_path / "staging")
    monkeypatch.setattr(trm_module, "ROOT_DIR", tmp_path)

    monkeypatch.setattr(trm_module, "_fetch_all_rows", lambda: MACROECONOMIA_TRM_FALLBACK_DATA)

    result = MacroeconomiaTrmExtractor().run(dry_run=True)

    assert result.dataset == "macroeconomia_trm"
    assert result.source_mode == "live"
    assert not (tmp_path / "staging" / "macroeconomia_trm.csv").exists()
    assert not (tmp_path / "staging" / "macroeconomia_trm.metadata.json").exists()


def test_fetch_falls_back_on_expected_source_failure(monkeypatch):
    def _bad_payload() -> None:
        raise ValueError("JSON con forma inesperada")

    monkeypatch.setattr(trm_module, "_fetch_all_rows", _bad_payload)

    result = MacroeconomiaTrmExtractor().fetch()
    assert result.source_mode == "fallback"
    assert result.dataframe.height > 0


def test_fetch_propagates_unexpected_bugs_instead_of_hiding_as_fallback(monkeypatch):
    def _broken_fetch_all_rows() -> None:
        raise AttributeError("bug de programación simulado, no una falla de red")

    monkeypatch.setattr(trm_module, "_fetch_all_rows", _broken_fetch_all_rows)

    with pytest.raises(AttributeError):
        MacroeconomiaTrmExtractor().fetch()
