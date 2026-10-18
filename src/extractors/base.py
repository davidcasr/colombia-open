"""Contrato base para extractores de colombia-open.

Todo extractor nuevo implementa `BaseExtractor` y usa los helpers de este
módulo para escribir snapshots crudos y staging de forma atómica. Ver
`.claude/rules/extractors.md` para el contrato completo en prosa.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
STAGING_DIR = DATA_DIR / "staging"


def ensure_staging_directories() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    STAGING_DIR.mkdir(parents=True, exist_ok=True)


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def write_raw_snapshot_atomic(path: Path, payload: Any) -> Path:
    """Escribe un snapshot crudo (write-once, nunca se edita después de esto).

    `payload` puede ser bytes, str, o algo JSON-serializable (dict/list).
    """
    if isinstance(payload, bytes):
        data = payload
    elif isinstance(payload, str):
        data = payload.encode("utf-8")
    else:
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    _atomic_write_bytes(path, data)
    return path


def write_staging_metadata(path: Path, metadata: dict[str, Any]) -> Path:
    data = json.dumps(metadata, ensure_ascii=False, indent=2, default=str).encode("utf-8")
    _atomic_write_bytes(path, data)
    return path


def write_staging_csv_atomic(
    df: pl.DataFrame, csv_path: Path, metadata_path: Path, metadata: dict[str, Any]
) -> Path:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(csv_path.parent), prefix=f".{csv_path.name}.", suffix=".tmp"
    )
    os.close(fd)
    try:
        df.write_csv(tmp_path)
        os.replace(tmp_path, csv_path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    merged = {
        **metadata,
        "record_count": df.height,
        "fields": df.columns,
    }
    write_staging_metadata(metadata_path, merged)
    return csv_path


def compute_sha256(data: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(data)
    return digest.hexdigest()


@dataclass(frozen=True)
class ReusePolicy:
    """Estado legal de una fuente. Ver docs/licenses/data_licenses.md para el semáforo completo."""

    status: str  # "open-attribution" | "public-api-review-terms" | "restricted"
    license: str
    license_url: str
    attribution_required: bool
    redistribution_ok: bool
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "license": self.license,
            "license_url": self.license_url,
            "attribution_required": self.attribution_required,
            "redistribution_ok": self.redistribution_ok,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class ExtractionResult:
    """Resultado tipado de una extracción — el modelo de procedencia de datos.

    Nunca se fabrica un ExtractionResult con datos sintéticos presentados como
    reales: si `source_mode` es "fallback", el dato NO es en vivo y la CI de
    publicación debe rechazarlo (ver `.claude/rules/extractors.md`).
    """

    dataset: str
    dataframe: pl.DataFrame
    source_name: str
    source_url: str
    source_mode: str  # "live" | "fallback"
    reuse_policy: ReusePolicy
    raw_snapshot_path: str | None = None
    snapshot_hash: str | None = None
    source_detail: str = ""
    notes: list[str] = field(default_factory=list)
    retrieved_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_staging_metadata(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "source_mode": self.source_mode,
            "source_detail": self.source_detail,
            "refreshed_at_utc": self.retrieved_at.isoformat(),
            "record_count": self.dataframe.height,
            "fields": self.dataframe.columns,
            "notes": self.notes,
            "raw_snapshot_path": self.raw_snapshot_path,
            "snapshot_hash": self.snapshot_hash,
            "reuse_policy": self.reuse_policy.to_dict(),
        }


class BaseExtractor(ABC):
    """Contrato que todo extractor nuevo debe cumplir.

    Ver `.claude/skills/new-source/SKILL.md` para generar uno a partir de
    este contrato.
    """

    @property
    @abstractmethod
    def dataset_name(self) -> str: ...

    @abstractmethod
    def fetch(self, **kwargs: Any) -> ExtractionResult:
        """Intenta la fuente en vivo; cae a fallback solo si TODO falla.

        Nunca debe lanzar en caso de fallback — debe devolver un
        ExtractionResult con source_mode="fallback" y una nota explicando
        por qué. Solo debe propagar la excepción si no hay fallback posible.
        """

    @abstractmethod
    def write_staging(self, result: ExtractionResult) -> Path:
        """Escribe CSV + metadata.json en data/staging/. Debe ser atómico."""

    def run(self, dry_run: bool = False, **kwargs: Any) -> ExtractionResult:
        ensure_staging_directories()
        result = self.fetch(**kwargs)
        if not dry_run:
            self.write_staging(result)
        return result
