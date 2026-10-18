import pytest

import src.extractors.base as base_module
import src.extractors.divipola_extractor as divipola_module
from src.extractors.divipola_extractor import DIVIPOLA_FALLBACK_DATA, DivipolaExtractor, _normalize


def test_normalize_fallback_rows_have_fixed_width_codes():
    df = _normalize(DIVIPOLA_FALLBACK_DATA)
    assert all(len(c) == 2 for c in df["cod_dpto"].to_list())
    assert all(len(c) == 5 for c in df["cod_mpio"].to_list())


def test_normalize_parses_comma_decimal_coordinates():
    df = _normalize(DIVIPOLA_FALLBACK_DATA)
    bogota = df.filter(df["cod_mpio"] == "11001")
    assert bogota["longitud"].item() == -74.083652
    assert bogota["latitud"].item() == 4.60971


def test_extractor_dry_run_never_writes(tmp_path, monkeypatch):
    # `RAW_DIR`/`STAGING_DIR` se importan con `from ... import` tanto en
    # base.py como en divipola_extractor.py — cada módulo tiene su PROPIO
    # nombre apuntando al mismo Path original, así que hay que parchear
    # ambos: parchear solo base_module.RAW_DIR no afecta la escritura real
    # dentro de divipola_extractor.fetch(), que usa su propio nombre local.
    monkeypatch.setattr(base_module, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(base_module, "STAGING_DIR", tmp_path / "staging")
    monkeypatch.setattr(divipola_module, "RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(divipola_module, "STAGING_DIR", tmp_path / "staging")
    # fetch() calcula raw_path.relative_to(ROOT_DIR) para la metadata —
    # también hay que moverlo a tmp_path, o esa llamada lanza ValueError
    # (tmp_path no es subpath del repo real) y fetch() lo traga en su
    # except genérico, degradando a source_mode="fallback" en silencio.
    monkeypatch.setattr(divipola_module, "ROOT_DIR", tmp_path)

    # Nunca pegarle a la red real en un test: fetch() debe ver un éxito
    # "en vivo" simulado, sin salir a internet.
    monkeypatch.setattr(
        divipola_module, "get_json", lambda *_args, **_kwargs: DIVIPOLA_FALLBACK_DATA
    )

    extractor = DivipolaExtractor()
    result = extractor.run(dry_run=True)

    assert result.dataset == "divipola"
    assert result.source_mode == "live"
    assert not (tmp_path / "staging" / "divipola.csv").exists()
    assert not (tmp_path / "staging" / "divipola.metadata.json").exists()


def test_fetch_propagates_unexpected_bugs_instead_of_hiding_as_fallback(monkeypatch):
    """Un error de programación real (no una falla esperada de la fuente)
    debe reventar, no disfrazarse de source_mode="fallback". Si esto
    empieza a fallar porque alguien volvió a poner `except Exception`
    desnudo en fetch(), es justo el regresión que este test existe para
    atrapar."""

    def _broken_get_json(*_args: object, **_kwargs: object) -> None:
        raise AttributeError("bug de programación simulado, no una falla de red")

    monkeypatch.setattr(divipola_module, "get_json", _broken_get_json)

    extractor = DivipolaExtractor()
    with pytest.raises(AttributeError):
        extractor.fetch()
