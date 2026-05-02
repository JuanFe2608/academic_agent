"""Adapter transitorio para la normalización de títulos de scheduling."""

from __future__ import annotations

from services.scheduling.title_normalization import (
    is_placeholder_schedule_title,
    normalize_schedule_title,
)

__all__ = ["is_placeholder_schedule_title", "normalize_schedule_title"]
