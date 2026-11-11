"""Tests de scripts/check_source_urls.py — sin red: la sesión HTTP es un doble."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import requests

from scripts import check_source_urls as csu

ROOT = Path(__file__).resolve().parents[2]


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _FakeSession:
    """Registra cada request y responde según un mapa url -> status (o excepción)."""

    def __init__(self, responses: dict[str, int | Exception]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str, dict[str, str]]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls.append((method, url, kwargs.get("params", {})))
        outcome = self.responses[url]
        if isinstance(outcome, Exception):
            raise outcome
        return _FakeResponse(outcome)


def test_real_registry_resolves_a_url_for_every_dataset() -> None:
    checks, missing = csu.collect_source_urls()
    registry = json.loads((ROOT / "data/registry/datasets.json").read_text(encoding="utf-8"))
    covered = {name for check in checks for name in check.datasets}

    assert missing == []
    assert covered == set(registry)
    # departamentos y municipios comparten extractor -> una sola URL.
    divipola = next(c for c in checks if "municipios" in c.datasets)
    assert set(divipola.datasets) == {"departamentos", "municipios"}
    assert divipola.url == "https://www.datos.gov.co/resource/gdxc-w37w.json"


def test_extractor_source_url_handles_parenthesized_concatenation(tmp_path: Path) -> None:
    extractor = tmp_path / "x_extractor.py"
    extractor.write_text(
        'SOURCE_URL = (\n    "https://example.org/a/"\n    "b.xlsx"\n)\nOTHER = 1\n',
        encoding="utf-8",
    )
    assert csu.extractor_source_url(extractor) == "https://example.org/a/b.xlsx"


def test_extractor_source_url_missing_constant_or_file(tmp_path: Path) -> None:
    extractor = tmp_path / "x_extractor.py"
    extractor.write_text("URL = 'https://example.org'\n", encoding="utf-8")
    assert csu.extractor_source_url(extractor) is None
    assert csu.extractor_source_url(tmp_path / "no_existe.py") is None


def test_registry_source_url_takes_precedence_and_missing_is_reported(tmp_path: Path) -> None:
    (tmp_path / "ext.py").write_text('SOURCE_URL = "https://from-extractor.org/x.json"\n')
    registry = tmp_path / "datasets.json"
    registry.write_text(
        json.dumps(
            {
                "a": {"extractor": "ext.py", "source_url": "https://from-registry.org/y.json"},
                "b": {"extractor": "ext.py"},
                "c": {"extractor": "no_existe.py"},
            }
        ),
        encoding="utf-8",
    )
    checks, missing = csu.collect_source_urls(registry, tmp_path)
    urls = {c.url: c.datasets for c in checks}
    assert urls == {
        "https://from-registry.org/y.json": ("a",),
        "https://from-extractor.org/x.json": ("b",),
    }
    assert missing == ["c"]


@pytest.mark.parametrize(
    ("url", "method", "params"),
    [
        ("https://download.geofabrik.de/south-america/colombia-latest.osm.pbf", "HEAD", {}),
        ("https://www.dane.gov.co/files/x/PPED-AreaMun-2018-2042_VP.xlsx", "HEAD", {}),
        ("https://www.datos.gov.co/resource/gdxc-w37w.json", "GET", {"$limit": "1"}),
        (
            "https://services2.arcgis.com/abc/arcgis/rest/services/MunicipiosSNR/FeatureServer/0",
            "GET",
            {"f": "json"},
        ),
    ],
)
def test_request_plan_never_gets_heavy_downloads(
    url: str, method: str, params: dict[str, str]
) -> None:
    assert csu.request_plan(url) == (method, url, params)


def test_real_registry_heavy_sources_use_head() -> None:
    checks, _ = csu.collect_source_urls()
    for check in checks:
        if check.url.endswith((".pbf", ".xlsx")):
            assert csu.request_plan(check.url)[0] == "HEAD", check.url


def test_main_reports_4xx_without_failing(monkeypatch: pytest.MonkeyPatch) -> None:
    checks = [
        csu.SourceCheck("https://ok.org/resource/a.json", ("a",)),
        csu.SourceCheck("https://blocked.org/b.xlsx", ("b",)),
    ]
    monkeypatch.setattr(csu, "collect_source_urls", lambda: (checks, []))
    session = _FakeSession(
        {"https://ok.org/resource/a.json": 200, "https://blocked.org/b.xlsx": 403}
    )
    assert csu.main(session=session) == 0
    assert [c[0] for c in session.calls] == ["GET", "HEAD"]


def test_main_fails_on_network_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    checks = [csu.SourceCheck("https://down.org/resource/a.json", ("a",))]
    monkeypatch.setattr(csu, "collect_source_urls", lambda: (checks, ["huerfano"]))
    session = _FakeSession({"https://down.org/resource/a.json": requests.ConnectionError("x")})
    assert csu.main(session=session) == 1
    out = capsys.readouterr().out
    assert "[ERROR DE RED] a" in out
    assert "[SIN URL] huerfano" in out
