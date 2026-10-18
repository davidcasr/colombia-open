"""Escritura atómica de outputs normalizados (parquet, json)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import polars as pl

from ._shared import ensure_normalized_dir


def write_parquet_atomic(df: pl.DataFrame, path: Path) -> Path:
    ensure_normalized_dir()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    os.close(fd)
    try:
        df.write_parquet(tmp_path)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    return path


def write_json_atomic(df: pl.DataFrame, path: Path) -> Path:
    ensure_normalized_dir()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    os.close(fd)
    try:
        df.write_json(tmp_path)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    return path
