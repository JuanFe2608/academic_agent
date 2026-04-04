"""Integraciones AI para extracción estructurada y multimodal."""

from .multimodal_extraction import (
    llm_extract_schedule_from_image,
    llm_extract_text_from_image,
)
from .openai_client import (
    get_azure_llm,
    get_openai_llm,
    maybe_get_llm,
)
from .structured_extraction import (
    _content_to_text,
    _safe_json_loads,
    _safe_json_value,
    get_last_llm_error,
    llm_extract_json,
    llm_extract_schedule_blocks,
    llm_generate_text,
    llm_normalize_extracurricular_items,
    llm_normalize_schedule,
)

__all__ = [
    "get_azure_llm",
    "get_openai_llm",
    "maybe_get_llm",
    "llm_extract_json",
    "llm_generate_text",
    "llm_normalize_schedule",
    "llm_normalize_extracurricular_items",
    "llm_extract_schedule_blocks",
    "llm_extract_schedule_from_image",
    "llm_extract_text_from_image",
    "get_last_llm_error",
    "_safe_json_loads",
    "_safe_json_value",
    "_content_to_text",
]
