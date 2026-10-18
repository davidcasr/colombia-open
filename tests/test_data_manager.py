import pytest

from colombia_open import data_manager
from colombia_open.exceptions import ColombiaOpenCacheError


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"{self.status_code} error", response=self)


def test_download_bundle_gives_actionable_message_on_404(monkeypatch):
    """Un 404 (sin Releases todavía) es un requests.HTTPError — si se
    chequea DESPUÉS de response.raise_for_status(), el except genérico de
    RequestException lo atrapa primero y el mensaje útil de abajo nunca se
    alcanza. Este test fija ese comportamiento."""
    monkeypatch.setattr(data_manager.requests, "get", lambda *_a, **_k: _FakeResponse(404))

    with pytest.raises(ColombiaOpenCacheError, match="no tiene ningún Release publicado"):
        data_manager.download_and_cache_bundle()


def test_download_bundle_gives_network_error_message_on_connection_failure(monkeypatch):
    import requests

    def _raise(*_a: object, **_k: object) -> None:
        raise requests.ConnectionError("sin red")

    monkeypatch.setattr(data_manager.requests, "get", _raise)

    with pytest.raises(ColombiaOpenCacheError, match="No se pudo consultar los Releases"):
        data_manager.download_and_cache_bundle()


def test_download_bundle_raises_on_other_http_errors(monkeypatch):
    monkeypatch.setattr(data_manager.requests, "get", lambda *_a, **_k: _FakeResponse(500))

    with pytest.raises(ColombiaOpenCacheError, match="respondió 500"):
        data_manager.download_and_cache_bundle()
