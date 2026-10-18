import pytest

import src.extractors.base as base_module
import src.extractors.educacion_establecimientos_extractor as educacion_module
from src.extractors.educacion_establecimientos_extractor import (
    EDUCACION_ESTABLECIMIENTOS_FALLBACK_DATA,
    EducacionEstablecimientosExtractor,
    _normalize,
    _parse_int,
)


def test_normalize_fallback_rows_have_fixed_width_codes():
    df, skipped = _normalize(EDUCACION_ESTABLECIMIENTOS_FALLBACK_DATA)
    assert skipped == 0
    assert all(len(c) == 2 for c in df["cod_dpto"].to_list())
    # cod_mpio puede ser null (ver nota sobre cod_dane_municipio ausente en
    # 2023) — se valida ancho fijo solo sobre los valores no nulos.
    assert all(len(c) == 5 for c in df["cod_mpio"].drop_nulls().to_list())
    assert df["cod_mpio"].null_count() == 1
    assert all(len(c) == 12 for c in df["codigo_dane_establecimiento"].to_list())


def test_normalize_fallback_keeps_all_rows():
    df, skipped = _normalize(EDUCACION_ESTABLECIMIENTOS_FALLBACK_DATA)
    assert skipped == 0
    assert df.height == len(EDUCACION_ESTABLECIMIENTOS_FALLBACK_DATA)


def test_normalize_fallback_reproduces_known_2023_low_cardinality_defect():
    df, _skipped = _normalize(EDUCACION_ESTABLECIMIENTOS_FALLBACK_DATA)
    rows_2023 = df.filter(df["anio"] == 2023)
    assert rows_2023.height > rows_2023["codigo_dane_establecimiento"].n_unique()


def test_normalize_skips_row_missing_required_field_instead_of_raising():
    rows = [*EDUCACION_ESTABLECIMIENTOS_FALLBACK_DATA, {"a_o": "2024"}]
    df, skipped = _normalize(rows)
    assert skipped == 1
    assert df.height == len(EDUCACION_ESTABLECIMIENTOS_FALLBACK_DATA)


def test_parse_int_handles_float_strings_dash_and_missing():
    assert _parse_int("817.000000") == 817
    assert _parse_int("187") == 187
    assert _parse_int("-") is None
    assert _parse_int("") is None
    assert _parse_int(None) is None


def test_extractor_dry_run_never_writes(tmp_path, monkeypatch):
    # Mismo motivo que en test_divipola_extractor.py: hay que parchear
    # RAW_DIR/STAGING_DIR/ROOT_DIR tanto en base.py como en el módulo del
    # extractor, porque cada uno tiene su propio nombre apuntando al Path
    # original.
    monkeypatch.setattr(base_module, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(base_module, "STAGING_DIR", tmp_path / "staging")
    monkeypatch.setattr(educacion_module, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(educacion_module, "STAGING_DIR", tmp_path / "staging")
    monkeypatch.setattr(educacion_module, "ROOT_DIR", tmp_path)

    monkeypatch.setattr(
        educacion_module, "_fetch_all_rows", lambda: EDUCACION_ESTABLECIMIENTOS_FALLBACK_DATA
    )

    extractor = EducacionEstablecimientosExtractor()
    result = extractor.run(dry_run=True)

    assert result.dataset == "educacion_establecimientos"
    assert result.source_mode == "live"
    assert not (tmp_path / "staging" / "educacion_establecimientos.csv").exists()
    assert not (tmp_path / "staging" / "educacion_establecimientos.metadata.json").exists()


def test_fetch_propagates_unexpected_bugs_instead_of_hiding_as_fallback(monkeypatch):
    """Ver el test homólogo en test_divipola_extractor.py: un bug de
    programación real debe reventar, no disfrazarse de
    source_mode='fallback'."""

    def _broken_fetch_all_rows() -> None:
        raise AttributeError("bug de programación simulado, no una falla de red")

    monkeypatch.setattr(educacion_module, "_fetch_all_rows", _broken_fetch_all_rows)

    extractor = EducacionEstablecimientosExtractor()
    with pytest.raises(AttributeError):
        extractor.fetch()
