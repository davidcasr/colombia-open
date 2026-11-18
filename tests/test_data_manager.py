import hashlib
import io
import json
import zipfile

import pytest
import requests

from colombia_open import ColombiaOpen, data_manager
from colombia_open.exceptions import ColombiaOpenCacheError

_TAGGED_URL = (
    "https://github.com/davidcasr/colombia-open/releases/download/v9.9.9/colombia-open-bundle.zip"
)


def _bundle(marker: str = "v1") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("dataset_catalog.json", json.dumps({"datasets": [], "marker": marker}))
    return buffer.getvalue()


class _Resp:
    def __init__(self, status: int, content: bytes = b"", url: str = "", history=()):
        self.status_code = status
        self.content = content
        self.url = url
        self.history = list(history)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error", response=self)


class _FakeGitHub:
    """Simula la descarga directa de GitHub: `latest/download/x` redirige a
    `download/<tag>/x`. Registra cada URL pedida."""

    def __init__(self, bundle: bytes, *, tag: str = "v9.9.9", status: int = 200):
        self.bundle = bundle
        self.tag = tag
        self.status = status
        self.calls: list[str] = []

    def get(self, url: str, timeout: int = 0) -> _Resp:
        self.calls.append(url)
        if self.status != 200:
            return _Resp(self.status, url=url)
        sha = hashlib.sha256(self.bundle).hexdigest()
        body = (
            f"{sha}  colombia-open-bundle.zip\n".encode()
            if url.endswith(".sha256")
            else self.bundle
        )
        final = url.replace("/latest/download/", f"/download/{self.tag}/")
        hop = _Resp(302, url=final)
        return _Resp(
            200, body, url="https://objects.example/abc", history=[_Resp(302, url=url), hop]
        )


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(data_manager, "_cache_root", lambda: tmp_path / "cache")
    monkeypatch.delenv(data_manager.BUNDLE_URL_ENV, raising=False)
    monkeypatch.delenv(data_manager.DATA_DIR_ENV, raising=False)
    return tmp_path / "cache"


def test_downloads_from_direct_url_without_github_api(monkeypatch, isolated_cache):
    fake = _FakeGitHub(_bundle())
    monkeypatch.setattr(data_manager.requests, "get", fake.get)

    path = data_manager.download_and_cache_bundle()

    assert all("api.github.com" not in url for url in fake.calls)
    assert fake.calls[0] == data_manager.LATEST_BUNDLE_URL + ".sha256"
    assert path == isolated_cache / "v9.9.9"
    assert (path / "dataset_catalog.json").exists()


def test_cache_hit_only_fetches_checksum(monkeypatch):
    fake = _FakeGitHub(_bundle())
    monkeypatch.setattr(data_manager.requests, "get", fake.get)
    data_manager.download_and_cache_bundle()
    fake.calls.clear()

    data_manager.download_and_cache_bundle()

    assert fake.calls == [data_manager.LATEST_BUNDLE_URL + ".sha256"]


def test_cache_invalidated_when_published_sha_changes(monkeypatch):
    """Mismo tag pero bundle distinto (release re-subido): no se sirve el
    viejo — la validez del caché depende del SHA256, no del nombre."""
    fake = _FakeGitHub(_bundle("v1"))
    monkeypatch.setattr(data_manager.requests, "get", fake.get)
    first = data_manager.download_and_cache_bundle()

    fake.bundle = _bundle("v2")
    second = data_manager.download_and_cache_bundle()

    assert first == second
    catalog = json.loads((second / "dataset_catalog.json").read_text(encoding="utf-8"))
    assert catalog["marker"] == "v2"


def test_new_release_gets_its_own_version_dir(monkeypatch, isolated_cache):
    fake = _FakeGitHub(_bundle("v1"), tag="v1.0.0")
    monkeypatch.setattr(data_manager.requests, "get", fake.get)
    data_manager.download_and_cache_bundle()
    fake.bundle, fake.tag = _bundle("v2"), "v1.1.0"

    path = data_manager.download_and_cache_bundle()

    assert path == isolated_cache / "v1.1.0"
    assert data_manager.cache_status()["versions"] == ["v1.0.0", "v1.1.0"]


def test_mirror_url_without_tag_uses_sha_as_version(monkeypatch, isolated_cache):
    bundle = _bundle()
    monkeypatch.setenv(data_manager.BUNDLE_URL_ENV, "https://mirror.example/co/bundle.zip")
    fake = _FakeGitHub(bundle)
    monkeypatch.setattr(data_manager.requests, "get", fake.get)

    path = data_manager.download_and_cache_bundle()

    assert fake.calls[0] == "https://mirror.example/co/bundle.zip.sha256"
    assert path.name == "sha256-" + hashlib.sha256(bundle).hexdigest()[:12]


def test_local_bundle_path_works_fully_offline(monkeypatch, tmp_path):
    bundle = _bundle()
    zip_path = tmp_path / "bundle.zip"
    zip_path.write_bytes(bundle)
    (tmp_path / "bundle.zip.sha256").write_text(hashlib.sha256(bundle).hexdigest())
    monkeypatch.setenv(data_manager.BUNDLE_URL_ENV, str(zip_path))

    def _no_network(*_a, **_k):
        raise AssertionError("no debe tocar la red")

    monkeypatch.setattr(data_manager.requests, "get", _no_network)

    assert (data_manager.download_and_cache_bundle() / "dataset_catalog.json").exists()


def test_sha_mismatch_is_rejected_and_not_cached(monkeypatch, isolated_cache):
    fake = _FakeGitHub(_bundle())
    real_get = fake.get

    def tampered(url, timeout=0):
        resp = real_get(url, timeout)
        if not url.endswith(".sha256"):
            resp.content = _bundle("tampered")
        return resp

    monkeypatch.setattr(data_manager.requests, "get", tampered)

    with pytest.raises(ColombiaOpenCacheError, match="SHA256 no coincide"):
        data_manager.download_and_cache_bundle()
    assert data_manager.cache_status()["versions"] == []


def test_invalid_checksum_file_is_rejected(monkeypatch):
    monkeypatch.setattr(
        data_manager.requests, "get", lambda url, timeout=0: _Resp(200, b"<html>login</html>", url)
    )
    with pytest.raises(ColombiaOpenCacheError, match="SHA256 válido"):
        data_manager.download_and_cache_bundle()


def test_404_gives_actionable_message(monkeypatch):
    monkeypatch.setattr(data_manager.requests, "get", _FakeGitHub(b"", status=404).get)
    with pytest.raises(ColombiaOpenCacheError, match="data_dir=") as exc_info:
        data_manager.download_and_cache_bundle()
    assert "404" in str(exc_info.value)
    assert data_manager.RELEASES_PAGE_URL in str(exc_info.value)


def test_403_from_proxy_is_not_retried_as_offline(monkeypatch):
    monkeypatch.setattr(data_manager.requests, "get", _FakeGitHub(b"", status=403).get)
    with pytest.raises(ColombiaOpenCacheError, match="respondió 403"):
        data_manager.download_and_cache_bundle()


def test_network_failure_without_cache_suggests_manual_download(monkeypatch):
    def _raise(*_a, **_k):
        raise requests.ConnectionError("sin red")

    monkeypatch.setattr(data_manager.requests, "get", _raise)
    with pytest.raises(ColombiaOpenCacheError, match="No se pudo conectar") as exc_info:
        data_manager.download_and_cache_bundle()
    assert "ColombiaOpen(data_dir=" in str(exc_info.value)
    assert data_manager.DATA_DIR_ENV in str(exc_info.value)


@pytest.mark.parametrize("failure", ["network", "500"])
def test_failure_falls_back_to_cached_bundle_with_warning(monkeypatch, failure):
    fake = _FakeGitHub(_bundle())
    monkeypatch.setattr(data_manager.requests, "get", fake.get)
    cached = data_manager.download_and_cache_bundle()

    if failure == "network":

        def _raise(*_a, **_k):
            raise requests.ConnectionError("sin red")

        monkeypatch.setattr(data_manager.requests, "get", _raise)
    else:
        monkeypatch.setattr(data_manager.requests, "get", _FakeGitHub(b"", status=500).get)

    with pytest.warns(UserWarning, match="ya cacheado"):
        assert data_manager.download_and_cache_bundle() == cached


def test_force_does_not_fall_back_to_cache(monkeypatch):
    monkeypatch.setattr(data_manager.requests, "get", _FakeGitHub(_bundle()).get)
    data_manager.download_and_cache_bundle()

    def _raise(*_a, **_k):
        raise requests.ConnectionError("sin red")

    monkeypatch.setattr(data_manager.requests, "get", _raise)
    with pytest.raises(ColombiaOpenCacheError):
        data_manager.download_and_cache_bundle(force=True)


def test_interrupted_extraction_never_leaves_valid_looking_dir(monkeypatch, isolated_cache):
    monkeypatch.setattr(data_manager.requests, "get", _FakeGitHub(_bundle()).get)

    def _boom(*_a, **_k):
        raise OSError("disco lleno")

    monkeypatch.setattr(zipfile.ZipFile, "extractall", _boom)
    with pytest.raises(OSError):
        data_manager.download_and_cache_bundle()
    assert data_manager.cache_status()["versions"] == []
    assert data_manager._latest_verified_cache() is None


def test_data_dir_env_var_skips_download(monkeypatch, tmp_path):
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    (bundle_dir / "dataset_catalog.json").write_text(json.dumps({"datasets": []}))
    monkeypatch.setenv(data_manager.DATA_DIR_ENV, str(bundle_dir))
    monkeypatch.setattr("colombia_open.core._find_dev_catalog", lambda: None)

    def _fail(**_k):
        raise AssertionError("no debe descargar")

    monkeypatch.setattr(data_manager, "download_and_cache_bundle", _fail)

    hub = ColombiaOpen()
    assert hub.root_dir == bundle_dir


def test_explicit_data_dir_wins_over_env_var(monkeypatch, tmp_path):
    explicit = tmp_path / "explicit"
    explicit.mkdir()
    (explicit / "dataset_catalog.json").write_text(json.dumps({"datasets": []}))
    monkeypatch.setenv(data_manager.DATA_DIR_ENV, str(tmp_path / "otro"))

    assert ColombiaOpen(data_dir=explicit).root_dir == explicit
