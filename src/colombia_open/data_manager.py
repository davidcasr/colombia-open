"""Descarga y cachea el bundle de datos publicado en GitHub Releases.

El wheel de PyPI NO incluye los datos generados — son demasiado grandes y
cambian con cada fuente nueva. En el primer uso, `ColombiaOpen()` descarga
el bundle del último Release, verifica su SHA256, y lo cachea localmente
(`platformdirs.user_cache_dir`).

## De dónde se descarga

Por defecto, de la URL de descarga directa de GitHub
(`https://github.com/<repo>/releases/latest/download/<asset>`), **sin pasar
por `api.github.com`**: la API anónima tiene un límite de 60 req/h por IP
y suele estar bloqueada en proxies corporativos, CI y sandboxes, mientras
que la descarga directa sí funciona.

Overrides por variable de entorno (para mirrors y entornos offline):

- `COLOMBIA_OPEN_BUNDLE_URL`: URL (o ruta local) del `.zip`. Su checksum
  se busca en la misma URL + `.sha256`.
- `COLOMBIA_OPEN_DATA_DIR`: directorio ya descomprimido con
  `dataset_catalog.json` — no descarga nada (lo resuelve `core.py`).

## Caché e invalidación

En cada `ColombiaOpen()` se pide solo el `.sha256` (unos bytes). La
versión en caché se reusa si y solo si su SHA256 coincide con el publicado;
si el Release cambió, se descarga el bundle nuevo. El directorio de caché
se nombra con el tag (`v0.14.0`, leído de la redirección de GitHub) o, para
un mirror sin tag en la URL, con `sha256-<prefijo>` — nunca con un nombre
fijo tipo "latest" que podría servir un bundle viejo indefinidamente.

Sin red: si ya hay algún bundle verificado en caché, se usa el más reciente
con un `UserWarning`; si no, falla con un error que explica cómo usar
`data_dir=` o descargar el bundle a mano.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import warnings
import zipfile
from io import BytesIO
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests
from platformdirs import user_cache_dir

from .exceptions import ColombiaOpenCacheError

GITHUB_REPO = "davidcasr/colombia-open"
BUNDLE_ASSET_NAME = "colombia-open-bundle.zip"
BUNDLE_CHECKSUM_ASSET_NAME = "colombia-open-bundle.zip.sha256"
LATEST_BUNDLE_URL = f"https://github.com/{GITHUB_REPO}/releases/latest/download/{BUNDLE_ASSET_NAME}"
RELEASES_PAGE_URL = f"https://github.com/{GITHUB_REPO}/releases/latest"
CACHE_APP_NAME = "colombia-open"

BUNDLE_URL_ENV = "COLOMBIA_OPEN_BUNDLE_URL"
DATA_DIR_ENV = "COLOMBIA_OPEN_DATA_DIR"

_SHA_MARKER = "_sha256.json"
_TAG_IN_URL = re.compile(r"/releases/download/([^/]+)/")
_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")

_MANUAL_HELP = (
    "Alternativas: (1) descarga a mano "
    f"{BUNDLE_ASSET_NAME} desde {RELEASES_PAGE_URL}, descomprímelo y usa "
    "`ColombiaOpen(data_dir='ruta/al/bundle')` o la variable de entorno "
    f"{DATA_DIR_ENV}; (2) apunta {BUNDLE_URL_ENV} a un mirror o a un .zip "
    "local; (3) en un checkout del repo, corre `make build` y usa "
    "`data_dir='data/normalized'`."
)


def _cache_root() -> Path:
    return Path(user_cache_dir(CACHE_APP_NAME))


def _cached_version_dir(version: str) -> Path:
    return _cache_root() / version


def cache_status() -> dict[str, object]:
    root = _cache_root()
    if not root.exists():
        return {"cache_dir": str(root), "versions": []}
    versions = sorted(
        p.name for p in root.iterdir() if p.is_dir() and not p.name.endswith(".partial")
    )
    return {"cache_dir": str(root), "versions": versions}


def clear_cache() -> None:
    root = _cache_root()
    if root.exists():
        shutil.rmtree(root)


def _bundle_url() -> str:
    return os.environ.get(BUNDLE_URL_ENV) or LATEST_BUNDLE_URL


def _local_path(url: str) -> Path | None:
    """Ruta local si `url` es `file://...` o una ruta existente en disco."""
    parsed = urlparse(url)
    if parsed.scheme == "file":
        return Path(unquote(parsed.path))
    if parsed.scheme in ("http", "https"):
        return None
    return Path(url)


def _fetch(url: str, *, timeout: int) -> tuple[bytes, str | None]:
    """Devuelve (contenido, tag del release si la URL o sus redirecciones
    lo revelan). Lanza `requests.RequestException` en fallas de red/HTTP y
    `FileNotFoundError` si es una ruta local inexistente."""
    local = _local_path(url)
    if local is not None:
        return local.read_bytes(), None
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    tag = None
    for hop in [*response.history, response]:
        match = _TAG_IN_URL.search(hop.url or "")
        if match:
            tag = match.group(1)
            break
    return response.content, tag


def _cached_sha(version_dir: Path) -> str | None:
    marker = version_dir / _SHA_MARKER
    if not marker.exists():
        return None
    try:
        value = json.loads(marker.read_text(encoding="utf-8")).get("sha256")
    except (ValueError, OSError):
        return None
    return value if isinstance(value, str) else None


def _latest_verified_cache() -> Path | None:
    root = _cache_root()
    if not root.exists():
        return None
    candidates = [
        p
        for p in root.iterdir()
        if p.is_dir() and _cached_sha(p) and (p / "dataset_catalog.json").exists()
    ]
    return max(candidates, key=lambda p: (p / _SHA_MARKER).stat().st_mtime, default=None)


def _offline_or_raise(reason: str, exc: Exception, *, force: bool) -> Path:
    cached = None if force else _latest_verified_cache()
    if cached is not None:
        warnings.warn(
            f"{reason} Usando el bundle ya cacheado en {cached} (puede estar desactualizado).",
            UserWarning,
            stacklevel=3,
        )
        return cached
    raise ColombiaOpenCacheError(f"{reason} {_MANUAL_HELP} Detalle: {exc}") from exc


def download_and_cache_bundle(*, force: bool = False) -> Path:
    """Descarga el bundle (último Release o `COLOMBIA_OPEN_BUNDLE_URL`),
    verifica SHA256 y lo extrae al caché local. Devuelve el directorio con
    `dataset_catalog.json` + los parquet/json de cada dataset."""
    bundle_url = _bundle_url()
    checksum_url = bundle_url + ".sha256"
    custom = bundle_url != LATEST_BUNDLE_URL

    try:
        checksum_bytes, tag = _fetch(checksum_url, timeout=30)
    except FileNotFoundError as exc:
        raise ColombiaOpenCacheError(
            f"No existe el checksum local {checksum_url} (requerido junto a "
            f"{BUNDLE_URL_ENV}). {_MANUAL_HELP}"
        ) from exc
    except requests.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else None
        if status == 404 and not custom:
            raise ColombiaOpenCacheError(
                "No se encontró ningún Release publicado con el bundle "
                f"({LATEST_BUNDLE_URL} respondió 404). {_MANUAL_HELP}"
            ) from exc
        if status is not None and status < 500 and status != 429:
            raise ColombiaOpenCacheError(
                f"{checksum_url} respondió {status}. {_MANUAL_HELP}"
            ) from exc
        return _offline_or_raise(
            f"No se pudo descargar el bundle ({checksum_url} respondió {status}).",
            exc,
            force=force,
        )
    except requests.RequestException as exc:
        return _offline_or_raise(
            f"No se pudo conectar para descargar el bundle ({checksum_url}).", exc, force=force
        )

    parts = checksum_bytes.decode("utf-8", errors="replace").strip().split()
    expected_hex = parts[0].lower() if parts else ""
    if not _SHA256_HEX.match(expected_hex):
        raise ColombiaOpenCacheError(f"{checksum_url} no contiene un SHA256 válido. {_MANUAL_HELP}")

    version = tag or f"sha256-{expected_hex[:12]}"
    version_dir = _cached_version_dir(version)
    if not force and _cached_sha(version_dir) == expected_hex:
        return version_dir

    try:
        bundle_bytes, _ = _fetch(bundle_url, timeout=120)
    except (requests.RequestException, OSError) as exc:
        return _offline_or_raise(
            f"No se pudo descargar el bundle ({bundle_url}).", exc, force=force
        )

    actual_hex = hashlib.sha256(bundle_bytes).hexdigest()
    if actual_hex != expected_hex:
        raise ColombiaOpenCacheError(
            f"SHA256 no coincide para {BUNDLE_ASSET_NAME}: esperado {expected_hex}, "
            f"obtenido {actual_hex}. El bundle descargado no es confiable, no se cachea."
        )

    # Extraer a un directorio temporal y renombrar al final: un proceso
    # interrumpido nunca deja un directorio de versión a medias marcado
    # como válido (el marcador _sha256.json se escribe antes del rename).
    staging_dir = version_dir.with_name(version_dir.name + ".partial")
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True)
    with zipfile.ZipFile(BytesIO(bundle_bytes)) as zf:
        zf.extractall(staging_dir)
    (staging_dir / _SHA_MARKER).write_text(
        json.dumps({"sha256": actual_hex, "asset": BUNDLE_ASSET_NAME, "source": bundle_url}),
        encoding="utf-8",
    )
    if version_dir.exists():
        shutil.rmtree(version_dir)
    staging_dir.rename(version_dir)
    return version_dir
