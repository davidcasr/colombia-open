"""Registro tipado de datasets disponibles.

Fuente de verdad estática (mantenida a mano): `data/registry/datasets.json`.
Esto es DISTINTO del catálogo generado en build time
(`data/normalized/dataset_catalog.json`), que fusiona este registro con
metadata de extracción y resultados de validación — ese es el que lee la
librería pública (`colombia_open.core.ColombiaOpen`).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
REGISTRY_PATH = ROOT_DIR / "data" / "registry" / "datasets.json"


@dataclass(frozen=True)
class DatasetSpec:
    dataset: str
    description: str
    extractor: str
    source_name: str
    join_keys: list[str]
    outputs: dict[str, str]
    documentation: str
    usage_examples: dict[str, str] = field(default_factory=dict)
    expected_record_count: int | None = None
    alias_for: str | None = None
    # {columna_local: dataset_referenciado} — p. ej. municipios.cod_dpto
    # referencia departamentos. Declarativo: permite que ColombiaOpen
    # revalide integridad referencial sin conocer el dominio de cada
    # dataset (ver core.py::validate_dataset() y
    # `.claude/rules/validation.md`).
    references: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, dataset: str, data: dict[str, Any]) -> DatasetSpec:
        return cls(
            dataset=dataset,
            description=data["description"],
            extractor=data["extractor"],
            source_name=data["source_name"],
            join_keys=data.get("join_keys", []),
            outputs=data.get("outputs", {}),
            documentation=data.get("documentation", ""),
            usage_examples=data.get("usage_examples", {}),
            expected_record_count=data.get("expected_record_count"),
            alias_for=data.get("alias_for"),
            references=data.get("references", {}),
        )


def load_registry(path: Path | None = None) -> dict[str, DatasetSpec]:
    registry_path = path or REGISTRY_PATH
    raw = json.loads(registry_path.read_text(encoding="utf-8"))
    return {name: DatasetSpec.from_dict(name, entry) for name, entry in raw.items()}
