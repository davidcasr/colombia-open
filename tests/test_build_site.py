"""Tests de scripts/build_site.py (genera #catalogo y #roadmap de la landing)."""

from __future__ import annotations

import importlib.util
import io
import json
import zipfile
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "build_site.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_site", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bs = _load_module()


def _entry(dataset: str, **overrides: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "dataset": dataset,
        "description": f"Descripción de `{dataset}`",
        "source_name": "DANE — Fuente de prueba (vía datos.gov.co)",
        "source_url": "https://www.datos.gov.co/resource/abcd-1234.json",
        "refreshed_at_utc": "2026-10-22T06:55:19+00:00",
        "record_count": 1122,
        "reuse_policy": {"status": "open-attribution", "license": "CC BY-SA 4.0"},
        "outputs": {"parquet": "x.parquet", "json": "x.json"},
    }
    entry.update(overrides)
    return entry


DISPLAY = {
    "grupos": ["Geografía", "Economía"],
    "datasets": {
        "municipios": {"titulo": "Municipios", "grupo": "Geografía"},
        "macroeconomia_trm": {"titulo": "TRM diaria", "grupo": "Economía"},
    },
}


def test_render_card_uses_published_metadata() -> None:
    card = bs.render_card(_entry("municipios"), "Municipios")
    assert "<h3>Municipios</h3>" in card
    assert "1.122 filas" in card
    assert "parquet · json" in card
    assert "CC BY-SA 4.0" in card
    assert "Actualizado: 22 de octubre de 2026" in card
    # El enlace de Socrata apunta a la vista legible, no al endpoint .json
    assert 'href="https://www.datos.gov.co/resource/abcd-1234"' in card
    assert "`" not in card


def test_render_card_links_terms_when_license_not_open() -> None:
    entry = _entry(
        "demografia",
        reuse_policy={
            "status": "public-api-review-terms",
            "license": "Sin licencia abierta explícita",
            "license_url": "https://www.dane.gov.co/terminos",
        },
    )
    card = bs.render_card(entry, "Proyecciones")
    assert 'href="https://www.dane.gov.co/terminos"' in card
    assert "Ver términos de uso" in card


def test_render_card_escapes_html() -> None:
    card = bs.render_card(_entry("municipios", source_name="<script>x</script>"), "M")
    assert "<script>" not in card
    assert "&lt;script&gt;" in card


def test_render_catalog_groups_in_declared_order() -> None:
    catalog = {"datasets": [_entry("macroeconomia_trm"), _entry("municipios")]}
    out = bs.render_catalog(catalog, DISPLAY)
    assert out.index("Geografía") < out.index("Municipios") < out.index("Economía")


def test_render_catalog_skips_unpublished_datasets() -> None:
    out = bs.render_catalog({"datasets": [_entry("municipios")]}, DISPLAY)
    assert "TRM diaria" not in out
    assert "Economía" not in out


def test_render_catalog_fails_when_published_dataset_has_no_display() -> None:
    catalog = {"datasets": [_entry("municipios"), _entry("calidad_aire")]}
    with pytest.raises(bs.SiteBuildError, match="calidad_aire"):
        bs.render_catalog(catalog, DISPLAY)


def test_render_roadmap_statuses() -> None:
    catalog = {"datasets": [_entry("municipios")]}
    registry = {
        "municipios": {"source_name": "DANE"},
        "macroeconomia_trm": {"source_name": "Superfinanciera"},
    }
    roadmap = {
        "filas": [
            {"dominio": "Geografía", "datasets": ["municipios"]},
            {"dominio": "TRM", "datasets": ["macroeconomia_trm"]},
            {"dominio": "Salud", "fuente": "MinSalud", "estado": "Pendiente"},
        ]
    }
    rows = bs.render_roadmap(catalog, roadmap, registry).split("\n")
    assert 'status-dot done"></span>Implementada' in rows[0]
    assert "DANE — Fuente de prueba" in rows[0]
    assert 'status-dot pending"></span>En desarrollo' in rows[1]
    assert "Superfinanciera" in rows[1]
    assert 'status-dot pending"></span>Pendiente' in rows[2]


def test_render_roadmap_rejects_unknown_dataset() -> None:
    roadmap = {"filas": [{"dominio": "X", "datasets": ["no_existe"]}]}
    with pytest.raises(bs.SiteBuildError, match="no_existe"):
        bs.render_roadmap({"datasets": []}, roadmap, {})


def test_replace_block_requires_single_markers() -> None:
    page = "a <!-- catalogo:inicio -->viejo<!-- catalogo:fin --> b"
    out = bs.replace_block(page, bs.CATALOG_START, bs.CATALOG_END, "nuevo", "")
    assert "viejo" not in out
    assert "nuevo" in out
    with pytest.raises(bs.SiteBuildError):
        bs.replace_block("sin marcadores", bs.CATALOG_START, bs.CATALOG_END, "x", "")


def test_catalog_from_bundle() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("dataset_catalog.json", json.dumps({"datasets": []}))
    assert bs.catalog_from_bundle(buffer.getvalue()) == {"datasets": []}


def test_real_site_files_cover_registry() -> None:
    """Todo dataset del registro necesita título/grupo para salir en la landing."""
    registry = json.loads(bs.REGISTRY_PATH.read_text(encoding="utf-8"))
    display = json.loads(bs.DISPLAY_PATH.read_text(encoding="utf-8"))
    missing = sorted(set(registry) - set(display["datasets"]))
    assert not missing, f"Agrega a site/data/catalogo.json: {missing}"


def test_main_builds_site_from_local_catalog(tmp_path: Path) -> None:
    registry = json.loads(bs.REGISTRY_PATH.read_text(encoding="utf-8"))
    catalog = {"datasets": [_entry(name) for name in registry]}
    catalog_path = tmp_path / "dataset_catalog.json"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    out = tmp_path / "_site"

    assert bs.main(["--catalog", str(catalog_path), "--out", str(out)]) == 0

    page = (out / "index.html").read_text(encoding="utf-8")
    block = page.split(bs.CATALOG_START, 1)[1].split(bs.CATALOG_END, 1)[0]
    assert block.count('class="dataset-card"') == len(registry)
    assert all(f'<span class="dataset-slug">{name}</span>' in block for name in registry)
    assert (out / "styles.css").exists()
    assert not (out / "data").exists()
