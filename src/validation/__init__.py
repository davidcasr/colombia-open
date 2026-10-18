"""Fachada de validación: siempre importar `validate_*` desde aquí, nunca
desde el submódulo de dominio directamente (mantiene un solo punto de
registro — ver `scripts/check_validation_registration.py`)."""

from collections.abc import Callable

from ._demografia import validate_demografia as validate_demografia
from ._territorio import validate_departamentos as validate_departamentos
from ._territorio import validate_municipios as validate_municipios
from .result import ValidationResult as ValidationResult

VALIDATORS: dict[str, Callable[..., ValidationResult]] = {
    "departamentos": validate_departamentos,
    "municipios": validate_municipios,
    "demografia": validate_demografia,
}

__all__ = [
    "VALIDATORS",
    "ValidationResult",
    "validate_demografia",
    "validate_departamentos",
    "validate_municipios",
]
