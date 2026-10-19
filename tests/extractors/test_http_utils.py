import pytest
import requests
from tenacity import wait_none

import src.extractors.http_utils as http_utils
from src.extractors.http_utils import MAX_ATTEMPTS, get_bytes, get_json


class _FakeResponse:
    def __init__(self, status_code: int, payload: object = None) -> None:
        self.status_code = status_code
        self._payload = payload
        self.content = b"ok"

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Error", response=self)  # type: ignore[arg-type]

    def json(self) -> object:
        return self._payload


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    # Sin esperas reales entre reintentos en los tests.
    monkeypatch.setattr(get_json.retry, "wait", wait_none())
    monkeypatch.setattr(get_bytes.retry, "wait", wait_none())


def _sequence(monkeypatch, outcomes):
    """Parchea requests.get para devolver/lanzar `outcomes` en orden."""
    calls = {"n": 0}

    def _fake_get(*_args, **_kwargs):
        outcome = outcomes[calls["n"]]
        calls["n"] += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(http_utils.requests, "get", _fake_get)
    return calls


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
def test_get_json_retries_transient_http_status_then_succeeds(monkeypatch, status):
    calls = _sequence(monkeypatch, [_FakeResponse(status), _FakeResponse(200, [{"a": 1}])])
    assert get_json("https://example.test") == [{"a": 1}]
    assert calls["n"] == 2


def test_get_json_retries_network_errors(monkeypatch):
    calls = _sequence(
        monkeypatch,
        [
            requests.ConnectionError("caída"),
            requests.Timeout("lento"),
            requests.exceptions.ChunkedEncodingError("cuerpo cortado"),
            _FakeResponse(200, []),
        ],
    )
    assert get_json("https://example.test") == []
    assert calls["n"] == 4


@pytest.mark.parametrize("status", [400, 403, 404])
def test_get_json_never_retries_non_transient_4xx(monkeypatch, status):
    calls = _sequence(monkeypatch, [_FakeResponse(status), _FakeResponse(200, [])])
    with pytest.raises(requests.HTTPError):
        get_json("https://example.test")
    assert calls["n"] == 1


def test_get_json_gives_up_after_max_attempts_and_reraises_http_error(monkeypatch):
    calls = _sequence(monkeypatch, [_FakeResponse(503)] * (MAX_ATTEMPTS + 1))
    with pytest.raises(requests.HTTPError):
        get_json("https://example.test")
    assert calls["n"] == MAX_ATTEMPTS


def test_get_bytes_retries_transient_http_status(monkeypatch):
    calls = _sequence(monkeypatch, [_FakeResponse(500), _FakeResponse(200)])
    assert get_bytes("https://example.test") == b"ok"
    assert calls["n"] == 2
