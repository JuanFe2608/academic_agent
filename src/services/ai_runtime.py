"""Wrappers de servicios para capacidades runtime de IA."""

from __future__ import annotations

from integrations.ai._llm_impl import load_image_as_data_url, maybe_get_llm

__all__ = ["load_image_as_data_url", "maybe_get_llm"]
