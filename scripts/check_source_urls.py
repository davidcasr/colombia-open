#!/usr/bin/env python
"""Chequeo periódico de liveness de las URLs de fuentes registradas.

Nunca bloquea publicación por sí solo (ver `.github/workflows/source-urls.yml`)
— un 4xx puede ser bloqueo anti-bot, no caída real. Solo reporta. Sale con
código 1 únicamente ante un error de red (DNS, timeout, conexión cortada).

Las URLs NO se duplican aquí a mano: para cada dataset de
`data/registry/datasets.json` se usa su `source_url` si el registro la
declara, y si no, la constante `SOURCE_URL` del extractor que el registro
apunta en `extractor` — leída con `ast`, sin importar el módulo (los
extractores tienen deps pesadas detrás del extra `pipeline`, y este chequeo
corre solo con `requests` instalado).

Las descargas pesadas (Geofabrik ~332 MB, xlsx del DANE) se revisan con
`HEAD`, nunca con `GET`.
"""

from __future__ import annotations

import ast
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests

ROOT_DIR = Path(__file__).resolve().parent.parent
REGISTRY_PATH = ROOT_DIR / "data" / "registry" / "datasets.json"

TIMEOUT_SECONDS = 30
# Extensiones de descarga directa (potencialmente pesadas): solo HEAD.
HEAD_SUFFIXES = (".pbf", ".xlsx", ".xls", ".zip", ".csv", ".shp", ".gpkg", ".geojson")


@dataclass(frozen=True)
class SourceCheck:
    """Una URL a revisar y los datasets del registro que dependen de ella."""

    url: str
    datasets: tuple[str, ...]


def extractor_source_url(extractor_path: Path) -> str | None:
    """Devuelve la constante de módulo `SOURCE_URL` de un extractor, o None.

    Se parsea con `ast` (sin ejecutar el módulo). Soporta concatenación
    implícita de literales entre paréntesis, que `ast` ya resuelve a un
    único `Constant`.
    """
    if not extractor_path.is_file():
        return None
    tree = ast.parse(extractor_path.read_text(encoding="utf-8"))
    for node in tree.body:
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets, value = list(node.targets), node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        if value is None:
            continue
        if any(isinstance(t, ast.Name) and t.id == "SOURCE_URL" for t in targets):
            try:
                url = ast.literal_eval(value)
            except ValueError:
                return None
            return url if isinstance(url, str) else None
    return None


def collect_source_urls(
    registry_path: Path = REGISTRY_PATH, root_dir: Path = ROOT_DIR
) -> tuple[list[SourceCheck], list[str]]:
    """Resuelve la URL de fuente de cada dataset del registro.

    Devuelve (checks, sin_url): los checks agrupan los datasets que comparten
    URL (p. ej. `departamentos` y `municipios` salen del mismo extractor) para
    pedirla una sola vez; `sin_url` lista los datasets cuya URL no se pudo
    resolver — se reportan, no se ignoran en silencio.
    """
    raw: dict[str, dict[str, Any]] = json.loads(registry_path.read_text(encoding="utf-8"))
    by_url: dict[str, list[str]] = {}
    missing: list[str] = []
    for dataset, entry in raw.items():
        url = entry.get("source_url")
        if not url and entry.get("extractor"):
            url = extractor_source_url(root_dir / entry["extractor"])
        if not url:
            missing.append(dataset)
            continue
        by_url.setdefault(url, []).append(dataset)
    checks = [SourceCheck(url=url, datasets=tuple(names)) for url, names in by_url.items()]
    return checks, missing


def request_plan(url: str) -> tuple[str, str, dict[str, str]]:
    """Decide método, URL y parámetros para revisar una fuente sin descargarla entera."""
    path = urlsplit(url).path.lower()
    if path.endswith(HEAD_SUFFIXES):
        return "HEAD", url, {}
    if "/resource/" in path and path.endswith(".json"):
        # API Socrata (datos.gov.co): una sola fila basta.
        return "GET", url, {"$limit": "1"}
    if "/featureserver/" in path or "/mapserver/" in path:
        # ArcGIS REST: la metadata de la capa, no la geometría.
        return "GET", url, {"f": "json"}
    return "HEAD", url, {}


def check_url(url: str, session: Any = requests) -> tuple[int | None, str]:
    """Revisa una URL. Devuelve (status_code, detalle); status None = error de red."""
    method, target, params = request_plan(url)
    try:
        response = session.request(
            method, target, params=params, timeout=TIMEOUT_SECONDS, allow_redirects=True
        )
    except requests.RequestException as exc:
        return None, f"{method} -> {exc}"
    return response.status_code, method


def main(session: Any = requests) -> int:
    checks, missing = collect_source_urls()
    total = sum(len(c.datasets) for c in checks) + len(missing)
    print(f"{total} datasets en el registro, {len(checks)} URLs de fuente distintas.")

    had_hard_failure = False
    for check in checks:
        names = ", ".join(check.datasets)
        status, detail = check_url(check.url, session=session)
        if status is None:
            print(f"[ERROR DE RED] {names}: {check.url} ({detail})")
            had_hard_failure = True
        else:
            print(f"[{status}] {names}: {check.url} ({detail})")

    for dataset in missing:
        print(
            f"[SIN URL] {dataset}: ni `source_url` en el registro ni `SOURCE_URL` en el extractor"
        )

    return 1 if had_hard_failure else 0


if __name__ == "__main__":
    sys.exit(main())
