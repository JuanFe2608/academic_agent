"""Prompting grounded sobre contexto RAG recuperado."""

from .context_package import (
    GroundedPromptContext,
    build_grounded_prompt_context,
    clean_chunk_text,
    format_entity_name,
)
from .grounded_answer import build_grounded_study_recommendation_result
from .templates import render_fallback_answer, render_grounded_answer

__all__ = [
    "GroundedPromptContext",
    "build_grounded_prompt_context",
    "build_grounded_study_recommendation_result",
    "clean_chunk_text",
    "format_entity_name",
    "render_fallback_answer",
    "render_grounded_answer",
]
