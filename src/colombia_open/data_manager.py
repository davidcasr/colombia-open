"""Descarga y cachea el bundle de datos publicado en GitHub Releases.

El wheel de PyPI NO incluye los datos generados — son demasiado grandes y
cambian con cada fuente nueva. En el primer uso, `ColombiaOpen()` descarga
el bundle del último Release, verifica su SHA256, y lo cachea localmente
(`platformdirs.user_cache_dir`). Llamadas siguientes usan el caché.

Mientras no exista ningún Release publicado (el proyecto todavía no ha
hecho su primer release — ver README.md "Estado del proyecto"), esto falla
con un error explicando cómo correr el pipeline localmente en su lugar.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

import requests
from platformdirs import user_cache_dir

from .exceptions import ColombiaOpenCacheError

GITHUB_REPO = "davidcasr/colombia-open"
RELEASES_LATEST_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
BUNDLE_ASSET_NAME = "colombia-open-bundle.zip"
BUNDLE_CHECKSUM_ASSET_NAME = "colombia-open-bundle.zip.sha256"
CACHE_APP_NAME = "colombia-open"


def _cache_root() -> Path:
    return Path(user_cache_dir(CACHE_APP_NAME))


def _cached_version_dir(version: str) -> Path:
    return _cache_root() / version


def cache_status() -> dict[str, object]:
    root = _cache_root()
    if not root.exists():
        return {"cache_dir": str(root), "versions": []}
    versions = sorted(p.name for p in root.iterdir() if p.is_dir())
    return {"cache_dir": str(root), "versions": versions}


def clear_cache() -> None:
    import shutil

    root = _cache_root()
    if root.exists():
        shutil.rmtree(root)


def _find_asset(assets: list[dict[str, Any]], name: str) -> dict[str, Any]:
    for asset in assets:
        if asset.get("name") == name:
            return asset
    raise ColombiaOpenCacheError(
        f"El último Release no tiene un asset llamado '{name}'. "
        f"Revisa https://github.com/{GITHUB_REPO}/releases/latest"
    )


def download_and_cache_bundle(*, force: bool = False) -> Path:
    """Descarga el bundle del último Release, verifica SHA256, y lo extrae
    al caché local. Devuelve el directorio con `dataset_catalog.json` +
    los parquet/json de cada dataset."""
    try:
        response = requests.get(RELEASES_LATEST_URL, timeout=30)
    except requests.RequestException as exc:
        raise ColombiaOpenCacheError(
            "No se pudo consultar los Releases de GitHub. Si estás desarrollando "
            "localmente, corre `make build` para generar data/normalized/ en vez "
            f"de depender del bundle publicado. Detalle: {exc}"
        ) from exc

    # Chequear 404 ANTES de raise_for_status(): un 404 es un HTTPError (subclase
    # de RequestException), así que si no se chequea primero, el except de
    # arriba lo atrapa y nunca se llega a este mensaje más útil.
    if response.status_code == 404:
        raise ColombiaOpenCacheError(
            "Este proyecto todavía no tiene ningún Release publicado — la "
            "estrategia es validar el patrón con 2-3 fuentes antes de publicar "
            "un bundle. Corre el pipeline localmente: `make bootstrap && make build`, "
            "o pasa `data_dir='data/normalized'` a ColombiaOpen()."
        )

    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise ColombiaOpenCacheError(
            f"GitHub Releases respondió {response.status_code}. Detalle: {exc}"
        ) from exc

    release = response.json()
    version = release.get("tag_name", "latest")
    version_dir = _cached_version_dir(version)

    if version_dir.exists() and not force:
        return version_dir

    assets = release.get("assets", [])
    bundle_asset = _find_asset(assets, BUNDLE_ASSET_NAME)
    checksum_asset = _find_asset(assets, BUNDLE_CHECKSUM_ASSET_NAME)

    bundle_bytes = requests.get(bundle_asset["browser_download_url"], timeout=120).content
    expected_hex = (
        requests.get(checksum_asset["browser_download_url"], timeout=30).text.strip().split()[0]
    )

    actual_hex = hashlib.sha256(bundle_bytes).hexdigest()
    if actual_hex != expected_hex:
        raise ColombiaOpenCacheError(
            f"SHA256 no coincide para {BUNDLE_ASSET_NAME}: esperado {expected_hex}, "
            f"obtenido {actual_hex}. El bundle descargado no es confiable, no se cachea."
        )

    version_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(BytesIO(bundle_bytes)) as zf:
        zf.extractall(version_dir)

    (version_dir / "_sha256.json").write_text(
        json.dumps({"sha256": actual_hex, "asset": BUNDLE_ASSET_NAME}), encoding="utf-8"
    )
    return version_dir
