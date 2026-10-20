import datetime

import polars as pl
import pytest

import src.extractors.base as base_module
import src.extractors.delincuencia_hurto_modalidades_extractor as modalidades_module
from src.extractors.delincuencia_hurto_modalidades_extractor import (
    DELINCUENCIA_HURTO_MODALIDADES_FALLBACK_DATA,
    PRIMARY_KEY,
    DelincuenciaHurtoModalidadesExtractor,
    _normalize,
)


def _row(**overrides: str | None) -> dict[str, str | None]:
    row: dict[str, str | None] = {
        "departamento": "ANTIOQUIA",
        "municipio": "Medellín (CT)",
        "codigo_dane": "05001000",
        "armas_medios": "CONTUNDENTES",
        "fecha_hecho": "14/03/2025",
        "genero": "MASCULINO",
        "grupo_etario": "ADULTOS",
        "tipo_de_hurto": "ARTÍCULO 239. HURTO RESIDENCIAS",
        "cantidad": "1",
    }
    row.update(overrides)
    return row


def test_normalize_fallback_rows_have_fixed_width_codes():
    df, _excluded, _hechos, skipped = _normalize(DELINCUENCIA_HURTO_MODALIDADES_FALLBACK_DATA)
    assert skipped == 0
    assert all(len(c) == 2 for c in df["cod_dpto"].to_list())
    assert all(len(c) == 5 for c in df["cod_mpio"].to_list())


def test_normalize_derives_codes_from_8_digit_codigo_dane():
    df, _excluded, _hechos, _skipped = _normalize([_row(codigo_dane="5001000")])
    # El 8 dígitos perdió el cero inicial: se rellena antes de cortar.
    assert df["cod_dpto"].to_list() == ["05"]
    assert df["cod_mpio"].to_list() == ["05001"]


def test_normalize_collapses_centro_poblado_into_municipio():
    rows = [_row(codigo_dane="13001000", cantidad="2"), _row(codigo_dane="13001009", cantidad="1")]
    df, _excluded, _hechos, _skipped = _normalize(rows)
    assert df.height == 1
    assert df.row(0, named=True)["cod_mpio"] == "13001"
    assert df.row(0, named=True)["cantidad"] == 3


def test_normalize_primary_key_is_unique():
    df, _excluded, _hechos, _skipped = _normalize(DELINCUENCIA_HURTO_MODALIDADES_FALLBACK_DATA)
    assert df.select(PRIMARY_KEY).unique().height == df.height


def test_normalize_excludes_rows_without_municipio_and_counts_hechos():
    df, excluded, hechos, skipped = _normalize(
        [_row(), _row(codigo_dane="00000000", cantidad="3"), _row(codigo_dane=None)]
    )
    assert excluded == 2
    assert hechos == 4
    assert skipped == 0
    assert df["cod_mpio"].to_list() == ["05001"]


def test_normalize_strips_capital_suffix_from_nombre_mpio():
    df, _excluded, _hechos, _skipped = _normalize([_row(municipio="Bucaramanga (CT)")])
    assert df["nombre_mpio"].to_list() == ["Bucaramanga"]


def test_normalize_uses_most_frequent_name_per_code():
    # Mismo defecto conocido que lesiones: código y nombre contradictorios.
    rows = [
        _row(codigo_dane="25754000", municipio="Soacha", departamento="CUNDINAMARCA"),
        _row(
            codigo_dane="25754000",
            municipio="Soacha",
            departamento="CUNDINAMARCA",
            fecha_hecho="15/03/2025",
        ),
        _row(
            codigo_dane="25754001",
            municipio="Jamundí",
            departamento="VALLE",
            fecha_hecho="16/03/2025",
        ),
    ]
    df, _excluded, _hechos, _skipped = _normalize(rows)
    assert set(df["nombre_mpio"].to_list()) == {"Soacha"}
    assert set(df["nombre_dpto"].to_list()) == {"CUNDINAMARCA"}


@pytest.mark.parametrize(
    ("tipo_de_hurto", "expected"),
    [
        ("ARTÍCULO 239. HURTO RESIDENCIAS", "residencias"),
        ("ARTÍCULO 239. HURTO ENTIDADES COMERCIALES", "comercio"),
        ("ARTÍCULO 240. HURTO CALIFICADO", None),
    ],
)
def test_normalize_classifies_modalidad(tipo_de_hurto, expected):
    df, _excluded, _hechos, _skipped = _normalize([_row(tipo_de_hurto=tipo_de_hurto)])
    assert df["modalidad"].to_list() == [expected]


def test_normalize_parses_fecha_anio_and_cantidad():
    df, _excluded, _hechos, _skipped = _normalize([_row(cantidad="4")])
    row = df.row(0, named=True)
    assert row["fecha"] == datetime.date(2025, 3, 14)
    assert row["anio"] == 2025
    assert row["cantidad"] == 4


def test_normalize_keeps_null_genero_instead_of_inventing_a_value():
    df, _excluded, _hechos, _skipped = _normalize([_row(genero=None)])
    assert df["genero"].to_list() == [None]


def test_normalize_keeps_null_grupo_etario_instead_of_inventing_a_value():
    df, _excluded, _hechos, _skipped = _normalize([_row(grupo_etario=None)])
    assert df["grupo_etario"].to_list() == [None]


def test_normalize_skips_unparseable_rows_instead_of_raising():
    df, _excluded, _hechos, skipped = _normalize(
        [_row(), _row(fecha_hecho="no-es-fecha"), _row(cantidad=None)]
    )
    assert skipped == 2
    assert df.height == 1


def test_normalize_empty_input_returns_empty_frame_with_schema():
    df, excluded, hechos, skipped = _normalize([])
    assert df.height == 0
    assert (excluded, hechos, skipped) == (0, 0, 0)
    assert df.schema["cod_mpio"] == pl.Utf8


def test_extractor_dry_run_never_writes(tmp_path, monkeypatch):
    # Ver test_divipola_extractor.py: hay que parchear los paths tanto en
    # base.py como en el módulo del extractor.
    monkeypatch.setattr(base_module, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(base_module, "STAGING_DIR", tmp_path / "staging")
    monkeypatch.setattr(modalidades_module, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(modalidades_module, "STAGING_DIR", tmp_path / "staging")
    monkeypatch.setattr(modalidades_module, "ROOT_DIR", tmp_path)

    monkeypatch.setattr(
        modalidades_module,
        "_fetch_all_rows",
        lambda: DELINCUENCIA_HURTO_MODALIDADES_FALLBACK_DATA,
    )

    result = DelincuenciaHurtoModalidadesExtractor().run(dry_run=True)

    assert result.dataset == "delincuencia_hurto_modalidades"
    assert result.source_mode == "live"
    assert any("00000000" in note for note in result.notes)
    assert not (tmp_path / "staging" / "delincuencia_hurto_modalidades.csv").exists()
    assert not (tmp_path / "staging" / "delincuencia_hurto_modalidades.metadata.json").exists()


def test_fetch_falls_back_on_expected_source_failure(monkeypatch):
    def _bad_payload() -> None:
        raise ValueError("JSON con forma inesperada")

    monkeypatch.setattr(modalidades_module, "_fetch_all_rows", _bad_payload)

    result = DelincuenciaHurtoModalidadesExtractor().fetch()
    assert result.source_mode == "fallback"
    assert result.dataframe.height > 0


def test_fetch_propagates_unexpected_bugs_instead_of_hiding_as_fallback(monkeypatch):
    def _broken_fetch_all_rows() -> None:
        raise AttributeError("bug de programación simulado, no una falla de red")

    monkeypatch.setattr(modalidades_module, "_fetch_all_rows", _broken_fetch_all_rows)

    with pytest.raises(AttributeError):
        DelincuenciaHurtoModalidadesExtractor().fetch()
