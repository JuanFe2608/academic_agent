"""Adapter transitorio para utilidades puras del subdominio extracurricular."""

from __future__ import annotations

from services.scheduling.extracurricular_state import (
    build_extracurricular_item_source_text,
    build_extracurricular_items_source_text,
    coerce_extracurricular_pending_items,
    merge_extracurricular_items,
)
from services.scheduling.pending_extracurricular_support import (
    build_extracurricular_reply_hint,
)

__all__ = [
    "build_extracurricular_item_source_text",
    "build_extracurricular_items_source_text",
    "build_extracurricular_reply_hint",
    "coerce_extracurricular_pending_items",
    "merge_extracurricular_items",
]
