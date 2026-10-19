"""Wrapper HTTP compartido por los extractores: reintentos + timeout por defecto.

Separado de cada extractor para que el comportamiento de red (backoff,
user-agent, timeout, qué se reintenta) sea consistente y se ajuste en un
solo lugar.
"""

from __future__ import annotations

from typing import Any

import requests
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

DEFAULT_TIMEOUT = 30
USER_AGENT = "colombia-open/0.1 (+https://github.com/davidcasr/colombia-open)"

# Respuestas HTTP que significan "el servidor está mal AHORA", no "el dato o
# el endpoint cambió": se reintentan igual que un error de red. Confirmado
# en vivo el 2026-10-19: datos.gov.co devolvía 500/503 intermitentes (~1 de
# cada 6 páginas) y una fuente paginada en ~28 páginas no lograba un build en
# vivo. Cualquier otro 4xx (400, 403, 404...) es una respuesta real — endpoint
# movido, bloqueo anti-bot — y NO se reintenta. Ver
# `.claude/rules/extractors.md` §5.
TRANSIENT_HTTP_STATUS: frozenset[int] = frozenset({429, 500, 502, 503, 504})
MAX_ATTEMPTS = 4


def _is_transient(exc: BaseException) -> bool:
    # ChunkedEncodingError = la conexión se cortó a mitad del cuerpo de la
    # respuesta (observado en vivo en datos.gov.co el 2026-10-19); es una
    # falla de red igual que ConnectionError, aunque requests no la herede.
    if isinstance(
        exc, (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError)
    ):
        return True
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        return exc.response.status_code in TRANSIENT_HTTP_STATUS
    return False


_retry_transient = retry(
    retry=retry_if_exception(_is_transient),
    wait=wait_exponential(multiplier=1, min=1, max=20),
    stop=stop_after_attempt(MAX_ATTEMPTS),
    reraise=True,
)


@_retry_transient
def get_json(
    url: str, *, params: dict[str, Any] | None = None, timeout: int = DEFAULT_TIMEOUT
) -> Any:
    """GET con reintentos en errores de red/timeout y en 429/5xx transitorios
    (`TRANSIENT_HTTP_STATUS`); nunca en otros 4xx."""
    response = requests.get(url, params=params, timeout=timeout, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return response.json()


@_retry_transient
def get_bytes(
    url: str, *, params: dict[str, Any] | None = None, timeout: int = DEFAULT_TIMEOUT
) -> bytes:
    response = requests.get(url, params=params, timeout=timeout, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return response.content
