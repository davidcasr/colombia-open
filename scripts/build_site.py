"""Genera la landing (`site/`) desde el catálogo publicado.

Las tarjetas de `#catalogo` y las filas de `#roadmap` de `site/index.html`
NO se escriben a mano: se generan desde `dataset_catalog.json` del último
GitHub Release (lo que la librería pública realmente descarga), más dos
archivos de presentación mantenidos a mano:

- `site/data/catalogo.json`: título y grupo de cada dataset en la landing.
- `site/data/roadmap.json`: filas del roadmap (las implementadas se ligan a
  datasets; las pendientes se muestran tal cual).

Así la web nunca anuncia una fuente, licencia o conteo distinto al publicado.

Uso (solo librería estándar, sin instalar el paquete):

    python scripts/build_site.py --fetch-latest --out _site      # deploy
    python scripts/build_site.py --catalog ruta/dataset_catalog.json --out _site
    python scripts/build_site.py --fetch-latest --in-place       # refrescar site/index.html

`--catalog` acepta el JSON o el `colombia-open-bundle.zip`.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
import os
import re
import shutil
import sys
import urllib.request
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent
SITE_DIR = ROOT_DIR / "site"
INDEX_PATH = SITE_DIR / "index.html"
DISPLAY_PATH = SITE_DIR / "data" / "catalogo.json"
ROADMAP_PATH = SITE_DIR / "data" / "roadmap.json"
REGISTRY_PATH = ROOT_DIR / "data" / "registry" / "datasets.json"

GITHUB_REPO = "davidcasr/colombia-open"
RELEASES_LATEST_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
CATALOG_ASSET = "dataset_catalog.json"
BUNDLE_ASSET = "colombia-open-bundle.zip"
BUNDLE_CHECKSUM_ASSET = "colombia-open-bundle.zip.sha256"

CATALOG_START, CATALOG_END = "<!-- catalogo:inicio -->", "<!-- catalogo:fin -->"
ROADMAP_START, ROADMAP_END = "<!-- roadmap:inicio -->", "<!-- roadmap:fin -->"

BOGOTA_TZ = timezone(timedelta(hours=-5))
MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]  # fmt: skip

CARD_INDENT = " " * 8
ROW_INDENT = " " * 12


class SiteBuildError(Exception):
    """El sitio no se puede generar sin inventar datos: falla fuerte."""


# --------------------------------------------------------------------------- fetch


def _http_get(url: str, *, accept: str | None = None) -> bytes:
    if not url.startswith("https://"):
        raise SiteBuildError(f"URL no HTTPS rechazada: {url}")
    headers = {"User-Agent": "colombia-open-site-builder"}
    if accept:
        headers["Accept"] = accept
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=300) as response:
        data: bytes = response.read()
        return data


def catalog_from_bundle(bundle: bytes) -> dict[str, Any]:
    with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
        names = [n for n in archive.namelist() if n.rsplit("/", 1)[-1] == CATALOG_ASSET]
        if not names:
            raise SiteBuildError(f"El bundle no contiene {CATALOG_ASSET}")
        loaded: dict[str, Any] = json.loads(archive.read(names[0]))
        return loaded


def fetch_latest_catalog() -> tuple[dict[str, Any], str]:
    """Descarga el catálogo del último Release. Devuelve (catálogo, tag)."""
    release = json.loads(_http_get(RELEASES_LATEST_URL, accept="application/vnd.github+json"))
    tag = str(release.get("tag_name", "?"))
    assets = {a["name"]: a["browser_download_url"] for a in release.get("assets", [])}

    if CATALOG_ASSET in assets:
        catalog: dict[str, Any] = json.loads(_http_get(assets[CATALOG_ASSET]))
        return catalog, tag

    # Releases anteriores solo traen el bundle: se verifica su SHA256 antes de leerlo.
    if BUNDLE_ASSET not in assets or BUNDLE_CHECKSUM_ASSET not in assets:
        raise SiteBuildError(f"El release {tag} no tiene {CATALOG_ASSET} ni el bundle con SHA256")
    bundle = _http_get(assets[BUNDLE_ASSET])
    expected = _http_get(assets[BUNDLE_CHECKSUM_ASSET]).decode().strip().split()[0]
    actual = hashlib.sha256(bundle).hexdigest()
    if actual != expected:
        raise SiteBuildError(
            f"SHA256 del bundle no coincide: esperado {expected}, obtenido {actual}"
        )
    return catalog_from_bundle(bundle), tag


def load_catalog(path: Path) -> dict[str, Any]:
    if path.suffix == ".zip":
        return catalog_from_bundle(path.read_bytes())
    loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


# ------------------------------------------------------------------------- render


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def format_count(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def format_date(iso: str | None) -> str:
    if not iso:
        return "sin fecha"
    moment = datetime.fromisoformat(iso).astimezone(BOGOTA_TZ)
    return f"{moment.day} de {MESES[moment.month - 1]} de {moment.year}"


def human_source_url(url: str | None) -> str | None:
    """El endpoint JSON de Socrata no se lee bien en un navegador: enlaza la vista."""
    if not url:
        return None
    return re.sub(
        r"^(https://www\.datos\.gov\.co/resource/[a-z0-9]{4}-[a-z0-9]{4})\.json$", r"\1", url
    )


def plain(text: str) -> str:
    return esc(text.replace("`", ""))


def render_card(entry: dict[str, Any], title: str) -> str:
    policy = entry.get("reuse_policy") or {}
    license_name = policy.get("license") or "Licencia sin declarar"
    license_url = policy.get("license_url")
    if str(policy.get("status", "")).startswith("open") or not license_url:
        license_pill = f'<span class="pill">{esc(license_name)}</span>'
    else:
        license_pill = (
            f'<a class="pill" href="{esc(license_url)}" target="_blank" rel="noopener" '
            f'title="{esc(license_name)}">Ver términos de uso</a>'
        )

    formats = " · ".join(entry.get("outputs") or {}) or "—"
    source_name = esc(entry.get("source_name") or "Fuente sin declarar")
    source_url = human_source_url(entry.get("source_url"))
    source = (
        f'<a href="{esc(source_url)}" target="_blank" rel="noopener">{source_name}</a>'
        if source_url
        else source_name
    )

    i = CARD_INDENT
    return "\n".join(
        [
            f'{i}<div class="dataset-card">',
            f'{i}  <div class="dataset-title">',
            f"{i}    <h3>{esc(title)}</h3>",
            f'{i}    <span class="dataset-slug">{esc(entry["dataset"])}</span>',
            f"{i}  </div>",
            f"{i}  <p>{plain(entry.get('description', ''))}</p>",
            f'{i}  <div class="dataset-meta">',
            f'{i}    <span class="pill">{format_count(int(entry["record_count"]))} filas</span>',
            f'{i}    <span class="pill">{esc(formats)}</span>',
            f"{i}    {license_pill}",
            f"{i}  </div>",
            f'{i}  <p class="dataset-source">Fuente: {source}<br>'
            f"Actualizado: {format_date(entry.get('refreshed_at_utc'))}</p>",
            f"{i}</div>",
        ]
    )


def render_catalog(catalog: dict[str, Any], display: dict[str, Any]) -> str:
    published = {e["dataset"]: e for e in catalog["datasets"]}
    shown = display["datasets"]

    missing = sorted(set(published) - set(shown))
    if missing:
        raise SiteBuildError(
            "Datasets publicados sin título/grupo en site/data/catalogo.json: " + ", ".join(missing)
        )
    unknown_groups = sorted({v["grupo"] for v in shown.values()} - set(display["grupos"]))
    if unknown_groups:
        raise SiteBuildError("Grupos no declarados en 'grupos': " + ", ".join(unknown_groups))

    blocks: list[str] = []
    for group in display["grupos"]:
        names = [n for n, v in shown.items() if v["grupo"] == group and n in published]
        if not names:
            continue
        blocks.append(f'{CARD_INDENT}<p class="eyebrow catalog-group-label">{esc(group)}</p>')
        blocks.extend(render_card(published[n], shown[n]["titulo"]) for n in names)
    return "\n".join(blocks)


def _row(dominio: str, fuente: str, done: bool, estado: str) -> str:
    dot = "done" if done else "pending"
    return (
        f"{ROW_INDENT}<tr><td>{esc(dominio)}</td><td>{esc(fuente)}</td>"
        f'<td><span class="status-dot {dot}"></span>{esc(estado)}</td></tr>'
    )


def render_roadmap(
    catalog: dict[str, Any], roadmap: dict[str, Any], registry: dict[str, Any]
) -> str:
    published = {e["dataset"]: e for e in catalog["datasets"]}
    rows: list[str] = []
    for fila in roadmap["filas"]:
        datasets = fila.get("datasets")
        if not datasets:
            rows.append(_row(fila["dominio"], fila["fuente"], False, fila["estado"]))
            continue
        unknown = [d for d in datasets if d not in registry]
        if unknown:
            raise SiteBuildError(f"roadmap.json referencia datasets inexistentes: {unknown}")
        if all(d in published for d in datasets):
            fuente = (
                published[datasets[0]].get("source_name") or registry[datasets[0]]["source_name"]
            )
            rows.append(_row(fila["dominio"], fuente, True, "Implementada"))
        else:
            fuente = registry[datasets[0]]["source_name"]
            rows.append(_row(fila["dominio"], fuente, False, "En desarrollo"))
    return "\n".join(rows)


def replace_block(page: str, start: str, end: str, content: str, indent: str) -> str:
    if page.count(start) != 1 or page.count(end) != 1:
        raise SiteBuildError(f"site/index.html debe tener exactamente un {start} y un {end}")
    head, rest = page.split(start, 1)
    _, tail = rest.split(end, 1)
    return f"{head}{start}\n{content}\n{indent}{end}{tail}"


def build_page(page: str, catalog: dict[str, Any]) -> str:
    display = json.loads(DISPLAY_PATH.read_text(encoding="utf-8"))
    roadmap = json.loads(ROADMAP_PATH.read_text(encoding="utf-8"))
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    page = replace_block(
        page, CATALOG_START, CATALOG_END, render_catalog(catalog, display), CARD_INDENT
    )
    return replace_block(
        page, ROADMAP_START, ROADMAP_END, render_roadmap(catalog, roadmap, registry), ROW_INDENT
    )


# --------------------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--catalog", type=Path, help="dataset_catalog.json o bundle .zip local")
    source.add_argument("--fetch-latest", action="store_true", help="usar el último GitHub Release")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--out", type=Path, help="directorio de salida (copia de site/)")
    target.add_argument("--in-place", action="store_true", help="reescribir site/index.html")
    args = parser.parse_args(argv)

    try:
        if args.fetch_latest:
            catalog, origin = fetch_latest_catalog()
        else:
            catalog, origin = load_catalog(args.catalog), str(args.catalog)
        page = build_page(INDEX_PATH.read_text(encoding="utf-8"), catalog)
    except SiteBuildError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if args.in_place:
        INDEX_PATH.write_text(page, encoding="utf-8")
        destination = INDEX_PATH
    else:
        out: Path = args.out
        if out.exists():
            shutil.rmtree(out)
        shutil.copytree(SITE_DIR, out, ignore=shutil.ignore_patterns("data"))
        destination = out / "index.html"
        destination.write_text(page, encoding="utf-8")

    print(f"OK: {len(catalog['datasets'])} datasets de {origin} -> {destination}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
