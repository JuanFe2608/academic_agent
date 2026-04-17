"""Repositorios de persistencia para RAG."""

from .repository import (
    InMemoryRagRepository,
    PersistedRagIngestionRun,
    PostgresRagRepository,
    RagChunkSearchResult,
    RagEmbeddingCandidate,
    RagEmbeddingUpdate,
    RagRepository,
    RagRepositoryError,
    build_rag_repository,
)

__all__ = [
    "InMemoryRagRepository",
    "PersistedRagIngestionRun",
    "PostgresRagRepository",
    "RagChunkSearchResult",
    "RagEmbeddingCandidate",
    "RagEmbeddingUpdate",
    "RagRepository",
    "RagRepositoryError",
    "build_rag_repository",
]
