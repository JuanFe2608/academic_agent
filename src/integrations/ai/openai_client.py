"""Factories de cliente para Azure OpenAI y OpenAI."""

from ._llm_impl import get_azure_llm, get_openai_llm, maybe_get_llm

__all__ = [
    "get_azure_llm",
    "get_openai_llm",
    "maybe_get_llm",
]
