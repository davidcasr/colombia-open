import pytest

import src.extractors.base as base_module
import src.extractors.infraestructura_poi_extractor as poi_module
from src.extractors.infraestructura_poi_extractor import (
    INFRAESTRUCTURA_POI_FALLBACK_DATA,
    InfraestructuraPoiExtractor,
    _classify,
    _fallback_municipios_geometria,
    _normalize,
)


def test_classify_amenity_in_whitelist():
    assert _classify("pharmacy", None) == ("salud", "pharmacy")
    assert _classify("school", None) == ("educacion", "school")


def test_classify_shop_in_whitelist():
    assert _classify(None, "supermarket") == ("comercio", "supermarket")


def test_classify_returns_none_for_tags_outside_curated_list():
    # "bench"/"restaurant" existen en OSM pero no están en la lista curada.
    assert _classify("bench", None) is None
    assert _classify("restaurant", None) is None
    assert _classify(None, "hairdresser") is None
    assert _classify(None, None) is None


def test_normalize_fallback_rows_geocode_against_fallback_polygons():
    df, sin_municipio, duplicates = _normalize(
        INFRAESTRUCTURA_POI_FALLBACK_DATA, _fallback_municipios_geometria()
    )
    assert duplicates == 0
    # 6 POI reales dentro de Bogotá/Medellín + 1 fuera de cualquier polígono
    # (prueba de exclusión, coordenadas 0,0) a propósito.
    assert sin_municipio == 1
    assert df.height == 6
    assert all(len(c) == 2 for c in df["cod_dpto"].to_list())
    assert all(len(c) == 5 for c in df["cod_mpio"].to_list())


def test_normalize_excludes_poi_outside_any_municipio_polygon():
    rows = [
        {
            "osm_id": 1,
            "categoria": "comercio",
            "subcategoria": "supermarket",
            "nombre": "Dentro",
            "lon": -74.060183,
            "lat": 4.726381,
        },
        {
            "osm_id": 2,
            "categoria": "comercio",
            "subcategoria": "supermarket",
            "nombre": "Fuera de Colombia",
            "lon": 0.0,
            "lat": 0.0,
        },
    ]
    df, sin_municipio, _duplicates = _normalize(rows, _fallback_municipios_geometria())
    assert sin_municipio == 1
    assert df.height == 1
    assert df["osm_id"].to_list() == [1]


def test_normalize_keeps_null_nombre_instead_of_inventing_a_value():
    rows = [
        {
            "osm_id": 1,
            "categoria": "comercio",
            "subcategoria": "supermarket",
            "nombre": None,
            "lon": -74.060183,
            "lat": 4.726381,
        }
    ]
    df, _sin_municipio, _duplicates = _normalize(rows, _fallback_municipios_geometria())
    assert df["nombre"].to_list() == [None]


def test_normalize_empty_input_returns_empty_frame_with_schema():
    df, sin_municipio, duplicates = _normalize([], _fallback_municipios_geometria())
    assert df.height == 0
    assert (sin_municipio, duplicates) == (0, 0)
    assert df.schema["cod_mpio"].__class__.__name__ in {"Utf8", "String"}


def test_extractor_dry_run_never_writes(tmp_path, monkeypatch):
    # Ver test_divipola_extractor.py: hay que parchear los paths tanto en
    # base.py como en el módulo del extractor.
    monkeypatch.setattr(base_module, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(base_module, "STAGING_DIR", tmp_path / "staging")
    monkeypatch.setattr(poi_module, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(poi_module, "STAGING_DIR", tmp_path / "staging")
    monkeypatch.setattr(poi_module, "ROOT_DIR", tmp_path)

    monkeypatch.setattr(poi_module, "get_bytes", lambda *_args, **_kwargs: b"pbf-de-prueba")
    monkeypatch.setattr(
        poi_module,
        "_extract_poi_nodes",
        lambda _path: [
            {
                "osm_id": 1,
                "categoria": "comercio",
                "subcategoria": "supermarket",
                "nombre": "Carulla",
                "lon": -74.060183,
                "lat": 4.726381,
            }
        ],
    )

    result = InfraestructuraPoiExtractor().run(
        dry_run=True, municipios_geometria=_fallback_municipios_geometria()
    )

    assert result.dataset == "infraestructura_poi"
    assert result.source_mode == "live"
    assert result.dataframe.height == 1
    assert not (tmp_path / "staging" / "infraestructura_poi.csv").exists()
    assert not (tmp_path / "staging" / "infraestructura_poi.metadata.json").exists()


def test_fetch_falls_back_on_expected_source_failure(monkeypatch):
    def _bad_get_bytes(*_args: object, **_kwargs: object) -> None:
        raise ValueError("JSON con forma inesperada")

    monkeypatch.setattr(poi_module, "get_bytes", _bad_get_bytes)

    result = InfraestructuraPoiExtractor().fetch(
        municipios_geometria=_fallback_municipios_geometria()
    )
    assert result.source_mode == "fallback"
    assert result.dataframe.height > 0


def test_fetch_propagates_unexpected_bugs_instead_of_hiding_as_fallback(monkeypatch):
    def _broken_get_bytes(*_args: object, **_kwargs: object) -> None:
        raise AttributeError("bug de programación simulado, no una falla de red")

    monkeypatch.setattr(poi_module, "get_bytes", _broken_get_bytes)

    with pytest.raises(AttributeError):
        InfraestructuraPoiExtractor().fetch(municipios_geometria=_fallback_municipios_geometria())
