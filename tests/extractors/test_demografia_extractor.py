import pytest

import src.extractors.base as base_module
import src.extractors.demografia_extractor as demografia_module
from src.extractors.demografia_extractor import (
    DEMOGRAFIA_FALLBACK_DATA,
    DemografiaExtractor,
    _is_data_row,
    _normalize,
)


def test_normalize_fallback_rows_have_fixed_width_codes():
    df = _normalize(DEMOGRAFIA_FALLBACK_DATA)
    assert all(len(c) == 2 for c in df["cod_dpto"].to_list())
    assert all(len(c) == 5 for c in df["cod_mpio"].to_list())


def test_normalize_fallback_keeps_all_rows_and_areas():
    df = _normalize(DEMOGRAFIA_FALLBACK_DATA)
    assert df.height == len(DEMOGRAFIA_FALLBACK_DATA)
    assert set(df["area_geografica"].to_list()) == {
        "Cabecera Municipal",
        "Centros Poblados y Rural Disperso",
        "Total",
    }


def test_is_data_row_rejects_header_blank_and_footer_rows():
    header = ("DP", "DPNOM", "MPIO", "DPMP", "AÑO", "ÁREA GEOGRÁFICA", "TOTAL")
    blank = (None, None, None, None, None, None, None)
    footer_note = ("Fuente: DANE", None, None, None, None, None, None)
    data = ("05", "Antioquia", "05001", "Medellín", 2018, "Cabecera Municipal", 2382405)
    assert not _is_data_row(header)
    assert not _is_data_row(blank)
    assert not _is_data_row(footer_note)
    assert _is_data_row(data)


def test_extractor_dry_run_never_writes(tmp_path, monkeypatch):
    # Mismo motivo que en test_divipola_extractor.py: hay que parchear
    # RAW_DIR/STAGING_DIR/ROOT_DIR tanto en base.py como en
    # demografia_extractor.py, porque cada módulo tiene su propio nombre
    # apuntando al Path original.
    monkeypatch.setattr(base_module, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(base_module, "STAGING_DIR", tmp_path / "staging")
    monkeypatch.setattr(demografia_module, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(demografia_module, "STAGING_DIR", tmp_path / "staging")
    monkeypatch.setattr(demografia_module, "ROOT_DIR", tmp_path)

    monkeypatch.setattr(demografia_module, "get_bytes", lambda *_a, **_k: b"fake-bytes")
    monkeypatch.setattr(
        demografia_module, "_parse_workbook_rows", lambda *_a, **_k: DEMOGRAFIA_FALLBACK_DATA
    )

    extractor = DemografiaExtractor()
    result = extractor.run(dry_run=True)

    assert result.dataset == "demografia"
    assert result.source_mode == "live"
    assert not (tmp_path / "staging" / "demografia.csv").exists()
    assert not (tmp_path / "staging" / "demografia.metadata.json").exists()


def test_fetch_propagates_unexpected_bugs_instead_of_hiding_as_fallback(monkeypatch):
    """Ver el test homólogo en test_divipola_extractor.py: un bug de
    programación real debe reventar, no disfrazarse de
    source_mode='fallback'."""

    def _broken_get_bytes(*_args: object, **_kwargs: object) -> None:
        raise AttributeError("bug de programación simulado, no una falla de red")

    monkeypatch.setattr(demografia_module, "get_bytes", _broken_get_bytes)

    extractor = DemografiaExtractor()
    with pytest.raises(AttributeError):
        extractor.fetch()
