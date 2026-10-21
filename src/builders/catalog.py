"""Genera el catálogo runtime (`data/normalized/dataset_catalog.json`).

Este es el único archivo que lee la librería pública (`colombia_open.core`).
Fusiona el registro estático (`data/registry/datasets.json`) con la metadata
de extracción y el resultado de validación de cada dataset.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from src.registry import DatasetSpec
from src.validation import ValidationResult

from ._shared import CATALOG_PATH, ensure_normalized_dir


def write_dataset_catalog(entries: list[dict[str, Any]]) -> None:
    ensure_normalized_dir()
    catalog = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "datasets": entries,
    }
    CATALOG_PATH.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )


def build_catalog_entry(
    *,
    spec: DatasetSpec,
    extraction_metadata: dict[str, Any],
    validation_result: ValidationResult,
) -> dict[str, Any]:
    return {
        "dataset": spec.dataset,
        "description": spec.description,
        "source_name": extraction_metadata.get("source_name", spec.source_name),
        "source_url": extraction_metadata.get("source_url"),
        "source_mode": extraction_metadata.get("source_mode"),
        "refreshed_at_utc": extraction_metadata.get("refreshed_at_utc"),
        "record_count": validation_result.record_count,
        "join_keys": spec.join_keys,
        "reuse_policy": extraction_metadata.get("reuse_policy"),
        "validation_status": validation_result.status,
        "errors": validation_result.errors,
        "warnings": validation_result.warnings,
        "usage_examples": spec.usage_examples,
        "outputs": spec.outputs,
        "documentation": spec.documentation,
    }
