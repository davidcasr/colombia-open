import pytest

import src.extractors.base as base_module
import src.extractors.rethus_extractor as rethus_module
from src.extractors.rethus_extractor import (
    RETHUS_FALLBACK_DATA,
    SIN_INFORMACION,
    RethusExtractor,
    _normalize,
)


def _row(**overrides: str) -> dict[str, str]:
    row: dict[str, str] = {
        "origentitulo": "1 - LOCAL",
        "tipoinstitucion": "2 - EDUCACIÓN PARA EL TRABAJO Y EL DESARROLLO HUMANO",
        "tipoprograma": "AUXILIAR",
        "perfilprofesional": "A02 - AUXILIAR EN ENFERMERÍA",
        "a_oactoadministrativo": "2014",
        "departamentoresidencia": "05 - ANTIOQUIA",
        "municipioresidencia": "05120 - CÁCERES",
        "numeroregistros": "1",
    }
    row.update(overrides)
    return row


def test_normalize_parses_department_and_municipio_codes():
    df, excluded, skipped = _normalize([_row()])
    assert excluded == 0
    assert skipped == 0
    record = df.row(0, named=True)
    assert record["cod_dpto"] == "05"
    assert record["nombre_dpto"] == "ANTIOQUIA"
    assert record["cod_mpio"] == "05120"
    assert record["nombre_mpio"] == "CÁCERES"
    assert record["anio_registro"] == 2014
    assert record["numero_registros"] == 1


def test_normalize_excludes_sin_informacion_rows():
    rows = [
        _row(),
        _row(departamentoresidencia=SIN_INFORMACION, municipioresidencia=SIN_INFORMACION),
    ]
    df, excluded, skipped = _normalize(rows)
    assert excluded == 1
    assert skipped == 0
    assert df.height == 1


def test_normalize_fallback_rows_parse_correctly():
    df, excluded, skipped = _normalize(RETHUS_FALLBACK_DATA)
    assert skipped == 0
    # el fallback incluye una fila SIN INFORMACION a propósito, excluida.
    assert excluded == 1
    assert df.height == len(RETHUS_FALLBACK_DATA) - 1
    assert df["cod_dpto"].str.len_chars().eq(2).all()
    assert df["cod_mpio"].str.len_chars().eq(5).all()


def test_normalize_primary_key_is_unique_in_fallback_sample():
    df, _excluded, _skipped = _normalize(RETHUS_FALLBACK_DATA)
    key_columns = [
        "cod_mpio",
        "origen_titulo",
        "tipo_institucion",
        "tipo_programa",
        "perfil_profesional",
        "anio_registro",
    ]
    assert df.select(key_columns).unique().height == df.height


def test_normalize_skips_rows_missing_required_field_instead_of_raising():
    rows = [_row(), {"origentitulo": "1 - LOCAL"}]
    df, excluded, skipped = _normalize(rows)
    assert excluded == 0
    assert skipped == 1
    assert df.height == 1


def test_normalize_empty_input_returns_empty_frame_with_schema():
    import polars as pl

    df, excluded, skipped = _normalize([])
    assert df.height == 0
    assert excluded == 0
    assert skipped == 0
    assert df.schema["numero_registros"] == pl.Int64


def test_extractor_dry_run_never_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(base_module, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(base_module, "STAGING_DIR", tmp_path / "staging")
    monkeypatch.setattr(rethus_module, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(rethus_module, "STAGING_DIR", tmp_path / "staging")
    monkeypatch.setattr(rethus_module, "ROOT_DIR", tmp_path)

    monkeypatch.setattr(rethus_module, "_fetch_all_rows", lambda: RETHUS_FALLBACK_DATA)

    result = RethusExtractor().run(dry_run=True)

    assert result.dataset == "rethus"
    assert result.source_mode == "live"
    assert not (tmp_path / "staging" / "rethus.csv").exists()
    assert not (tmp_path / "staging" / "rethus.metadata.json").exists()


def test_fetch_falls_back_on_expected_source_failure(monkeypatch):
    def _bad_payload() -> None:
        raise ValueError("JSON con forma inesperada")

    monkeypatch.setattr(rethus_module, "_fetch_all_rows", _bad_payload)

    result = RethusExtractor().fetch()
    assert result.source_mode == "fallback"
    assert result.dataframe.height > 0


def test_fetch_propagates_unexpected_bugs_instead_of_hiding_as_fallback(monkeypatch):
    def _broken_fetch_all_rows() -> None:
        raise AttributeError("bug de programación simulado, no una falla de red")

    monkeypatch.setattr(rethus_module, "_fetch_all_rows", _broken_fetch_all_rows)

    with pytest.raises(AttributeError):
        RethusExtractor().fetch()
