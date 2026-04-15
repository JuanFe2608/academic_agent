"""Wrappers de dominio para capacidades AI usadas por scheduling."""

from __future__ import annotations

from integrations.ai.structured_extraction import (
    llm_extract_json,
    llm_extract_schedule_blocks,
    llm_normalize_extracurricular_items,
    llm_normalize_schedule,
)
from integrations.ai.multimodal_extraction import llm_extract_schedule_from_image

__all__ = [
    "llm_extract_json",
    "llm_extract_schedule_blocks",
    "llm_extract_schedule_from_image",
    "llm_normalize_extracurricular_items",
    "llm_normalize_schedule",
]
