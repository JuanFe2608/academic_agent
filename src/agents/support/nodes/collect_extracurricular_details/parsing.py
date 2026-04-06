"""Adapter transitorio para el parsing de actividades extracurriculares."""

from __future__ import annotations

from services.scheduling.extracurricular_parsing import (
    complete_pending_extracurricular_item,
    parse_extracurricular_items,
    parse_extracurricular_items_with_context,
    parse_extracurricular_text,
)

__all__ = [
    "complete_pending_extracurricular_item",
    "parse_extracurricular_items",
    "parse_extracurricular_items_with_context",
    "parse_extracurricular_text",
]
