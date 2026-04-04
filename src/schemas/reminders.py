"""Schemas reutilizables del dominio de recordatorios."""

from __future__ import annotations

from typing import Optional

from pydantic import Field

from .common import BaseSchemaModel


class RemindersState(BaseSchemaModel):
    """Configuracion de recordatorios y politicas."""

    enabled: bool = True
    policy: dict[str, object] = Field(default_factory=dict)
    persisted_policy_ids: list[int] = Field(default_factory=list)
    last_dispatch_error: Optional[str] = None
    last_sync_at: Optional[str] = None


__all__ = ["RemindersState"]
