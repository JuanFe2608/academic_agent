"""Adapter transitorio para el parsing de actividades extracurriculares."""

from __future__ import annotations

from services.scheduling.ai_support import llm_normalize_extracurricular_items
from services.scheduling import extracurricular_parsing as _service_parsing


def parse_extracurricular_items(
    text: str,
    expected_is_variable: bool | None = None,
):
    previous = _service_parsing.llm_normalize_extracurricular_items
    _service_parsing.llm_normalize_extracurricular_items = llm_normalize_extracurricular_items
    try:
        return _service_parsing.parse_extracurricular_items(
            text,
            expected_is_variable=expected_is_variable,
        )
    finally:
        _service_parsing.llm_normalize_extracurricular_items = previous


def parse_extracurricular_items_with_context(
    text: str,
    expected_is_variable: bool | None = None,
):
    previous = _service_parsing.llm_normalize_extracurricular_items
    _service_parsing.llm_normalize_extracurricular_items = llm_normalize_extracurricular_items
    try:
        return _service_parsing.parse_extracurricular_items_with_context(
            text,
            expected_is_variable=expected_is_variable,
        )
    finally:
        _service_parsing.llm_normalize_extracurricular_items = previous


complete_pending_extracurricular_item = _service_parsing.complete_pending_extracurricular_item
parse_extracurricular_text = _service_parsing.parse_extracurricular_text

__all__ = [
    "complete_pending_extracurricular_item",
    "llm_normalize_extracurricular_items",
    "parse_extracurricular_items",
    "parse_extracurricular_items_with_context",
    "parse_extracurricular_text",
]
