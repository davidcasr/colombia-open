"""Wrapper HTTP compartido por los extractores: reintentos + timeout por defecto.

Separado de cada extractor para que el comportamiento de red (backoff,
user-agent, timeout) sea consistente y se ajuste en un solo lugar.
"""

from __future__ import annotations

from typing import Any

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

DEFAULT_TIMEOUT = 30
USER_AGENT = "colombia-open/0.1 (+https://github.com/davidcasr/colombia-open)"


@retry(
    retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
    wait=wait_exponential(multiplier=1, min=1, max=20),
    stop=stop_after_attempt(4),
    reraise=True,
)
def get_json(
    url: str, *, params: dict[str, Any] | None = None, timeout: int = DEFAULT_TIMEOUT
) -> Any:
    """GET con reintentos (solo en errores de red/timeout, nunca en 4xx/5xx)."""
    response = requests.get(url, params=params, timeout=timeout, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return response.json()


@retry(
    retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
    wait=wait_exponential(multiplier=1, min=1, max=20),
    stop=stop_after_attempt(4),
    reraise=True,
)
def get_bytes(
    url: str, *, params: dict[str, Any] | None = None, timeout: int = DEFAULT_TIMEOUT
) -> bytes:
    response = requests.get(url, params=params, timeout=timeout, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return response.content
