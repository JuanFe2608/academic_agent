"""Extracción multimodal basada en LLM."""

from ._llm_impl import llm_extract_schedule_from_image, llm_extract_text_from_image

__all__ = [
    "llm_extract_schedule_from_image",
    "llm_extract_text_from_image",
]
