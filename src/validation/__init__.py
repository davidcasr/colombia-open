"""Fachada de validación: siempre importar `validate_*` desde aquí, nunca
desde el submódulo de dominio directamente (mantiene un solo punto de
registro — ver `scripts/check_validation_registration.py`)."""

from collections.abc import Callable

from ._delincuencia import (
    validate_delincuencia_hurto_modalidades as validate_delincuencia_hurto_modalidades,
)
from ._delincuencia import (
    validate_delincuencia_hurto_personas as validate_delincuencia_hurto_personas,
)
from ._delincuencia import (
    validate_delincuencia_lesiones_personales as validate_delincuencia_lesiones_personales,
)
from ._demografia import validate_demografia as validate_demografia
from ._educacion import validate_educacion_establecimientos as validate_educacion_establecimientos
from ._infraestructura import validate_infraestructura_poi as validate_infraestructura_poi
from ._territorio import validate_departamentos as validate_departamentos
from ._territorio import validate_municipios as validate_municipios
from ._territorio import validate_municipios_geometria as validate_municipios_geometria
from .result import ValidationResult as ValidationResult

VALIDATORS: dict[str, Callable[..., ValidationResult]] = {
    "departamentos": validate_departamentos,
    "municipios": validate_municipios,
    "municipios_geometria": validate_municipios_geometria,
    "demografia": validate_demografia,
    "educacion_establecimientos": validate_educacion_establecimientos,
    "delincuencia_hurto_personas": validate_delincuencia_hurto_personas,
    "delincuencia_lesiones_personales": validate_delincuencia_lesiones_personales,
    "delincuencia_hurto_modalidades": validate_delincuencia_hurto_modalidades,
    "infraestructura_poi": validate_infraestructura_poi,
}

__all__ = [
    "VALIDATORS",
    "ValidationResult",
    "validate_delincuencia_hurto_modalidades",
    "validate_delincuencia_hurto_personas",
    "validate_delincuencia_lesiones_personales",
    "validate_demografia",
    "validate_departamentos",
    "validate_educacion_establecimientos",
    "validate_infraestructura_poi",
    "validate_municipios",
    "validate_municipios_geometria",
]
