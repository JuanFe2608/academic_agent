"""Contratos compartidos y tipos base reutilizables."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

Occupation = Literal["solo_estudio", "ambos", "ninguna"]
Ocupacion = Occupation
Prioridad = Literal["alta", "media", "baja"]


class BaseSchemaModel(BaseModel):
    """Base de modelos con acceso tipo dict para compatibilidad."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)


__all__ = [
    "BaseSchemaModel",
    "Occupation",
    "Ocupacion",
    "Prioridad",
]
