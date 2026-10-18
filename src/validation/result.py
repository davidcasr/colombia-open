"""Resultado tipado de una validación — mypy puede chequear sus campos,
a diferencia de un `dict[str, Any]` plano."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ValidationStatus = Literal["ok", "error"]


@dataclass(frozen=True)
class ValidationResult:
    dataset: str
    status: ValidationStatus
    record_count: int
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "status": self.status,
            "record_count": self.record_count,
            "errors": self.errors,
            "warnings": self.warnings,
        }
