"""Shared contracts for embedding providers."""

from __future__ import annotations

from typing import Protocol


class EmbeddingClientError(Exception):
    """Base error for embedding providers."""


class EmbeddingClient(Protocol):
    """Minimal embedding client contract used by RAG ingestion."""

    provider: str
    model: str
    dimensions: int

    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...


__all__ = ["EmbeddingClient", "EmbeddingClientError"]
