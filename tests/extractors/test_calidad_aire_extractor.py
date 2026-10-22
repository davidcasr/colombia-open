import pytest

import src.extractors.base as base_module
import src.extractors.calidad_aire_extractor as aire_module
from src.extractors.calidad_aire_extractor import (
    CALIDAD_AIRE_FALLBACK_DATA,
    PRIMARY_KEY,
    CalidadAireExtractor,
    _normalize,
    _parse_cod,
)


def _row(**overrides: str | None) -> dict[str, str | None]:
    row: dict[str, str | None] = {
        "id_estacion": "9020",
        "estaci_n": "I.E. COL. COLOMBIA",
        "autoridad_ambiental": "AMVA",
        "tipo_de_estaci_n": "Fija",
        "latitud": "6.378517",
        "longitud": "-75.443986",
        "variable": "PM10",
        "unidades": "ugm3",
        "tiempo_de_exposici_n_horas": "24",
        "a_o": "2022",
        "promedio": "17.5",
        "mediana": "17.9",
        "m_ximo": "37.5",
        "no_de_datos": "65",
        "representatividad_temporal": "53.0",
        "d_as_de_excedencias": "0",
        "porcentaje_excedencias_limite": "0.0",
        "c_digo_del_departamento": "5",
        "nombre_del_departamento": "ANTIOQUIA",
        "c_digo_del_municipio": "5001",
        "nombre_del_municipio": "MEDELLIN",
    }
    row.update(overrides)
    return row


def test_parse_cod_handles_float_string_and_plain_int_string():
    assert _parse_cod("5308.0", 5) == "05308"
    assert _parse_cod("5308", 5) == "05308"
    assert _parse_cod("5", 2) == "05"
    assert _parse_cod(None, 5) is None
    assert _parse_cod("", 5) is None


def test_normalize_fallback_rows_have_fixed_width_codes():
    df, excluded, skipped, _dupes = _normalize(CALIDAD_AIRE_FALLBACK_DATA)
    assert skipped == 0
    assert excluded == 1
    assert all(len(c) == 2 for c in df["cod_dpto"].to_list())
    assert all(len(c) == 5 for c in df["cod_mpio"].to_list())


def test_normalize_primary_key_is_unique():
    df, _excluded, _skipped, _dupes = _normalize(CALIDAD_AIRE_FALLBACK_DATA)
    assert df.select(PRIMARY_KEY).unique().height == df.height


def test_normalize_excludes_rows_without_municipio():
    df, excluded, _skipped, _dupes = _normalize([_row(), _row(c_digo_del_municipio=None)])
    assert excluded == 1
    assert df.height == 1


def test_normalize_parses_cod_municipio_with_decimal_suffix():
    df, _excluded, _skipped, _dupes = _normalize([_row(c_digo_del_municipio="5308.0")])
    assert df["cod_mpio"].to_list() == ["05308"]


def test_normalize_uses_most_frequent_name_per_code_despite_inconsistent_casing():
    # Patrón real de la fuente: mismo departamento/municipio con mayúsculas
    # inconsistentes entre filas (confirmado en vivo: 20/33 departamentos,
    # 103 municipios afectados).
    rows = [
        _row(nombre_del_departamento="ANTIOQUIA", nombre_del_municipio="MEDELLIN"),
        _row(nombre_del_departamento="ANTIOQUIA", nombre_del_municipio="MEDELLIN", a_o="2023"),
        _row(nombre_del_departamento="Antioquia", nombre_del_municipio="Medellin", a_o="2024"),
    ]
    df, _excluded, _skipped, _dupes = _normalize(rows)
    assert df["nombre_dpto"].n_unique() == 1
    assert df["nombre_mpio"].n_unique() == 1
    assert df["nombre_dpto"].to_list()[0] == "ANTIOQUIA"


def test_normalize_collapses_exact_duplicate_key_published_twice():
    # Patrón real de la fuente, confirmado en vivo: la misma fila
    # (estación+contaminante+ventana+año) publicada dos veces, casi
    # siempre con el mismo promedio pero formato de código distinto.
    rows = [
        _row(c_digo_del_municipio="5001"),
        _row(c_digo_del_municipio="5001.0"),
    ]
    df, _excluded, _skipped, dupes = _normalize(rows)
    assert df.height == 1
    assert dupes == 1
    assert df["promedio"].to_list() == [17.5]


def test_normalize_averages_promedio_when_duplicate_copies_genuinely_differ():
    # Confirmado en vivo: ~1% de los pares duplicados (56/6306) tienen un
    # promedio distinto entre copias, no solo un formato distinto. Se
    # promedia — nunca se fabrica un tercer valor ni se descarta el grupo.
    rows = [_row(promedio="10.0"), _row(promedio="20.0")]
    df, _excluded, _skipped, dupes = _normalize(rows)
    assert dupes == 1
    assert df["promedio"].to_list() == [15.0]


def test_normalize_keeps_only_requested_fields_contaminante_passthrough():
    df, _excluded, _skipped, _dupes = _normalize(
        [_row(variable="O3", tiempo_de_exposici_n_horas="8")]
    )
    row = df.row(0, named=True)
    assert row["contaminante"] == "O3"
    assert row["tiempo_exposicion_horas"] == 8


def test_normalize_skips_rows_missing_required_field_instead_of_raising():
    rows = [_row(), {"id_estacion": "1"}]
    df, _excluded, skipped, _dupes = _normalize(rows)
    assert skipped == 1
    assert df.height == 1


def test_normalize_empty_input_returns_empty_frame_with_schema():
    import polars as pl

    df, excluded, skipped, dupes = _normalize([])
    assert df.height == 0
    assert (excluded, skipped, dupes) == (0, 0, 0)
    assert df.schema["cod_mpio"] == pl.Utf8


def test_extractor_dry_run_never_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(base_module, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(base_module, "STAGING_DIR", tmp_path / "staging")
    monkeypatch.setattr(aire_module, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(aire_module, "STAGING_DIR", tmp_path / "staging")
    monkeypatch.setattr(aire_module, "ROOT_DIR", tmp_path)

    monkeypatch.setattr(aire_module, "_fetch_all_rows", lambda: CALIDAD_AIRE_FALLBACK_DATA)

    result = CalidadAireExtractor().run(dry_run=True)

    assert result.dataset == "calidad_aire"
    assert result.source_mode == "live"
    assert not (tmp_path / "staging" / "calidad_aire.csv").exists()
    assert not (tmp_path / "staging" / "calidad_aire.metadata.json").exists()


def test_fetch_falls_back_on_expected_source_failure(monkeypatch):
    def _bad_payload() -> None:
        raise ValueError("JSON con forma inesperada")

    monkeypatch.setattr(aire_module, "_fetch_all_rows", _bad_payload)

    result = CalidadAireExtractor().fetch()
    assert result.source_mode == "fallback"
    assert result.dataframe.height > 0


def test_fetch_propagates_unexpected_bugs_instead_of_hiding_as_fallback(monkeypatch):
    def _broken_fetch_all_rows() -> None:
        raise AttributeError("bug de programación simulado, no una falla de red")

    monkeypatch.setattr(aire_module, "_fetch_all_rows", _broken_fetch_all_rows)

    with pytest.raises(AttributeError):
        CalidadAireExtractor().fetch()
