"""Schemas reutilizables para integraciones de calendario."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field

from .common import BaseSchemaModel

CalendarProvider = Literal["outlook", "google"]


class CalendarState(BaseSchemaModel):
    """Metadatos de integracion de calendario."""

    provider: Optional[CalendarProvider] = None
    authorized: bool = False
    calendar_id: Optional[str] = None
    synced_event_map: dict[str, str] = Field(default_factory=dict)


__all__ = [
    "CalendarProvider",
    "CalendarState",
]
