"""Tests for the atomic parquet/json writers in src/builders/formats.py (issue #14)."""

import polars as pl
import pytest

from src.builders import formats


def _sample_df() -> pl.DataFrame:
    return pl.DataFrame({"cod_dpto": ["05", "08"], "nombre": ["Antioquia", "Atlántico"]})


def _stub_ensure_normalized_dir(monkeypatch) -> None:
    monkeypatch.setattr(formats, "ensure_normalized_dir", lambda: None)


def test_write_parquet_atomic_roundtrip(tmp_path, monkeypatch):
    _stub_ensure_normalized_dir(monkeypatch)
    df = _sample_df()
    path = tmp_path / "out.parquet"

    formats.write_parquet_atomic(df, path)

    result = pl.read_parquet(path)
    assert result.equals(df)
    assert result["cod_dpto"].dtype == pl.Utf8


def test_write_json_atomic_roundtrip(tmp_path, monkeypatch):
    _stub_ensure_normalized_dir(monkeypatch)
    df = _sample_df()
    path = tmp_path / "out.json"

    formats.write_json_atomic(df, path)

    result = pl.read_json(path)
    assert result.equals(df)
    assert result["cod_dpto"].dtype == pl.Utf8


def test_write_atomic_creates_parent_directory(tmp_path, monkeypatch):
    _stub_ensure_normalized_dir(monkeypatch)
    df = _sample_df()
    path = tmp_path / "nested" / "deep" / "out.parquet"

    formats.write_parquet_atomic(df, path)

    assert path.exists()
    assert pl.read_parquet(path).equals(df)


def test_write_atomic_leaves_no_temp_file(tmp_path, monkeypatch):
    _stub_ensure_normalized_dir(monkeypatch)
    df = _sample_df()
    path = tmp_path / "out.parquet"

    formats.write_parquet_atomic(df, path)

    leftovers = list(tmp_path.glob(f".{path.name}.*.tmp"))
    assert leftovers == []


def test_write_atomic_failure_leaves_no_debris(tmp_path, monkeypatch):
    _stub_ensure_normalized_dir(monkeypatch)
    df = _sample_df()
    path = tmp_path / "out.parquet"

    def _raise(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(pl.DataFrame, "write_parquet", _raise)

    with pytest.raises(RuntimeError):
        formats.write_parquet_atomic(df, path)

    assert not path.exists()
    assert list(tmp_path.glob(f".{path.name}.*.tmp")) == []
