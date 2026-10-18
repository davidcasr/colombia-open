"""Enum canónico de datasets publicados. Actualizar a mano al agregar una
fuente nueva (ver `.claude/skills/new-source/SKILL.md`, paso final)."""

from __future__ import annotations

import enum
from difflib import get_close_matches


class Dataset(enum.StrEnum):
    DEPARTAMENTOS = "departamentos"
    MUNICIPIOS = "municipios"
    DEMOGRAFIA = "demografia"
    EDUCACION_ESTABLECIMIENTOS = "educacion_establecimientos"

    @classmethod
    def from_string(cls, name: str) -> Dataset:
        try:
            return cls(name)
        except ValueError as exc:
            matches = get_close_matches(name, cls.values(), n=1)
            hint = f" ¿Quisiste decir '{matches[0]}'?" if matches else ""
            raise ValueError(
                f"Dataset '{name}' no es válido.{hint} Valores posibles: {', '.join(cls.values())}"
            ) from exc

    @classmethod
    def values(cls) -> list[str]:
        return [member.value for member in cls]
