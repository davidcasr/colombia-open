"""Paths y constantes compartidas entre builders."""

from __future__ import annotations

from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT_DIR / "data"
STAGING_DIR = DATA_DIR / "staging"
NORMALIZED_DIR = DATA_DIR / "normalized"
CATALOG_PATH = NORMALIZED_DIR / "dataset_catalog.json"


def ensure_normalized_dir() -> None:
    NORMALIZED_DIR.mkdir(parents=True, exist_ok=True)
