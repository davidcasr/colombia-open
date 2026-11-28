import polars as pl
import pytest

import src.extractors.agro_eva_extractor as agro_module
import src.extractors.base as base_module
from src.extractors.agro_eva_extractor import (
    AGRO_EVA_MINAGRICULTURA_FALLBACK_DATA,
    AGRO_EVA_UPRA_FALLBACK_DATA,
    SERIE_MINAGRICULTURA,
    SERIE_UPRA,
    SOURCE_URL_MINAGRICULTURA,
    SOURCE_URL_UPRA,
    AgroEvaExtractor,
    _normalize,
)


def _minagri_row(**overrides: str) -> dict[str, str]:
    row = dict(AGRO_EVA_MINAGRICULTURA_FALLBACK_DATA[0])
    row.update(overrides)
    return row


def test_normalize_restores_leading_zero_lost_by_minagricultura_numeric_codes():
    # La fuente tipa c_d_dep/c_d_mun como number: Antioquia llega como "5".
    df, _, skipped = _normalize([], [_minagri_row(c_d_dep="5", c_d_mun="5440")])
    assert skipped == 0
    record = df.row(0, named=True)
    assert record["cod_dpto"] == "05"
    assert record["cod_mpio"] == "05440"


def test_normalize_maps_both_schemas_to_the_same_columns():
    df, skipped_upra, skipped_min = _normalize(
        AGRO_EVA_UPRA_FALLBACK_DATA, AGRO_EVA_MINAGRICULTURA_FALLBACK_DATA
    )
    assert skipped_upra == 0
    assert skipped_min == 0
    assert df.height == len(AGRO_EVA_UPRA_FALLBACK_DATA) + len(
        AGRO_EVA_MINAGRICULTURA_FALLBACK_DATA
    )
    assert set(df["serie_fuente"].to_list()) == {SERIE_UPRA, SERIE_MINAGRICULTURA}
    assert df["cod_dpto"].str.len_chars().eq(2).all()
    assert df["cod_mpio"].str.len_chars().eq(5).all()
    assert df.schema["anio"] == pl.Int32
    assert df.schema["area_sembrada_ha"] == pl.Float64


def test_normalize_leaves_codigo_cultivo_null_only_for_minagricultura():
    df, _, _ = _normalize(AGRO_EVA_UPRA_FALLBACK_DATA, AGRO_EVA_MINAGRICULTURA_FALLBACK_DATA)
    upra = df.filter(pl.col("serie_fuente") == SERIE_UPRA)
    minagri = df.filter(pl.col("serie_fuente") == SERIE_MINAGRICULTURA)
    assert upra["codigo_cultivo"].null_count() == 0
    assert minagri["codigo_cultivo"].null_count() == minagri.height


def test_normalize_primary_key_is_unique_in_fallback_sample():
    df, _, _ = _normalize(AGRO_EVA_UPRA_FALLBACK_DATA, AGRO_EVA_MINAGRICULTURA_FALLBACK_DATA)
    key = ["cod_mpio", "cultivo", "desagregacion_cultivo", "periodo"]
    assert df.select(key).unique().height == df.height


def test_normalize_skips_unparseable_rows_instead_of_raising():
    rows = [_minagri_row(), _minagri_row(rea_sembrada_ha="no-es-numero", periodo="2016B")]
    df, _, skipped = _normalize([], rows)
    assert skipped == 1
    assert df.height == 1


def test_normalize_keeps_unharvested_rows_with_missing_yield():
    # Socrata omite la clave cuando el rendimiento es nulo (nada cosechado).
    row = _minagri_row(rea_cosechada_ha="0", producci_n_t="0")
    del row["rendimiento_t_ha"]
    df, _, skipped = _normalize([], [row])
    assert skipped == 0
    assert df.height == 1
    assert df["rendimiento_t_ha"].item() is None


def test_normalize_empty_input_returns_empty_frame_with_schema():
    df, skipped_upra, skipped_min = _normalize([], [])
    assert df.height == 0
    assert skipped_upra == 0
    assert skipped_min == 0
    assert df.schema["cod_mpio"] == pl.Utf8


def _fake_fetch(source_url: str) -> list[dict[str, str]]:
    return {
        SOURCE_URL_UPRA: AGRO_EVA_UPRA_FALLBACK_DATA,
        SOURCE_URL_MINAGRICULTURA: AGRO_EVA_MINAGRICULTURA_FALLBACK_DATA,
    }[source_url]


def test_extractor_dry_run_never_writes_staging(tmp_path, monkeypatch):
    monkeypatch.setattr(base_module, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(base_module, "STAGING_DIR", tmp_path / "staging")
    monkeypatch.setattr(agro_module, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(agro_module, "STAGING_DIR", tmp_path / "staging")
    monkeypatch.setattr(agro_module, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(agro_module, "_fetch_all_rows", _fake_fetch)

    result = AgroEvaExtractor().run(dry_run=True)

    assert result.dataset == "agro_eva"
    assert result.source_mode == "live"
    assert not (tmp_path / "staging" / "agro_eva.csv").exists()
    assert not (tmp_path / "staging" / "agro_eva.metadata.json").exists()


def test_live_raw_snapshot_embeds_both_series(tmp_path, monkeypatch):
    import json

    monkeypatch.setattr(agro_module, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(agro_module, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(agro_module, "ensure_staging_directories", lambda: None)
    monkeypatch.setattr(agro_module, "_fetch_all_rows", _fake_fetch)

    result = AgroEvaExtractor().fetch()

    assert result.raw_snapshot_path is not None
    payload = json.loads((tmp_path / result.raw_snapshot_path).read_text(encoding="utf-8"))
    assert payload[SERIE_UPRA] == AGRO_EVA_UPRA_FALLBACK_DATA
    assert payload[SERIE_MINAGRICULTURA] == AGRO_EVA_MINAGRICULTURA_FALLBACK_DATA
    assert result.snapshot_hash is not None


def test_fetch_falls_back_when_either_series_fails(monkeypatch):
    def _second_series_down(source_url: str) -> list[dict[str, str]]:
        if source_url == SOURCE_URL_MINAGRICULTURA:
            raise ValueError("JSON con forma inesperada")
        return AGRO_EVA_UPRA_FALLBACK_DATA

    monkeypatch.setattr(agro_module, "_fetch_all_rows", _second_series_down)

    result = AgroEvaExtractor().fetch()
    assert result.source_mode == "fallback"
    assert result.dataframe.height > 0


def test_fetch_propagates_unexpected_bugs_instead_of_hiding_as_fallback(monkeypatch):
    def _broken(source_url: str) -> None:
        raise AttributeError("bug de programación simulado, no una falla de red")

    monkeypatch.setattr(agro_module, "_fetch_all_rows", _broken)

    with pytest.raises(AttributeError):
        AgroEvaExtractor().fetch()
