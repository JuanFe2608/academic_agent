"""Incremental embedding pipeline for RAG chunks."""

from __future__ import annotations

from dataclasses import dataclass

from integrations.embeddings import EmbeddingClient, EmbeddingClientError
from repositories.rag import RagEmbeddingUpdate, RagRepository


class RagEmbeddingPipelineError(Exception):
    """Base error for RAG embedding ingestion."""


@dataclass(frozen=True)
class RagEmbeddingPipelineResult:
    """Summary of one embedding pipeline execution."""

    requested_chunks: int
    embedded_chunks: int
    updated_chunks: int
    skipped_chunks: int = 0


def embed_changed_chunks(
    *,
    repository: RagRepository,
    embedding_client: EmbeddingClient,
    batch_size: int = 32,
    limit: int | None = None,
) -> RagEmbeddingPipelineResult:
    """Generate embeddings only for chunks whose embedding is missing."""

    if batch_size < 1:
        raise RagEmbeddingPipelineError("batch_size must be >= 1.")
    if embedding_client.dimensions < 1:
        raise RagEmbeddingPipelineError("embedding dimensions must be >= 1.")

    requested = 0
    embedded = 0
    updated = 0
    skipped = 0

    while True:
        remaining = None if limit is None else max(0, limit - requested)
        if remaining == 0:
            break
        current_batch_size = batch_size if remaining is None else min(batch_size, remaining)
        candidates = repository.list_chunks_missing_embeddings(limit=current_batch_size)
        if not candidates:
            break

        texts = [candidate.content for candidate in candidates]
        try:
            vectors = embedding_client.embed_texts(texts)
        except EmbeddingClientError as exc:
            raise RagEmbeddingPipelineError(str(exc)) from exc

        if len(vectors) != len(candidates):
            raise RagEmbeddingPipelineError(
                f"Embedding count mismatch: expected {len(candidates)}, got {len(vectors)}."
            )

        updates: list[RagEmbeddingUpdate] = []
        for candidate, vector in zip(candidates, vectors, strict=True):
            if len(vector) != embedding_client.dimensions:
                raise RagEmbeddingPipelineError(
                    f"Embedding dimension mismatch for chunk {candidate.chunk_id}: "
                    f"expected {embedding_client.dimensions}, got {len(vector)}."
                )
            updates.append(
                RagEmbeddingUpdate(
                    chunk_id=candidate.chunk_id,
                    checksum=candidate.checksum,
                    embedding=[float(value) for value in vector],
                    provider=embedding_client.provider,
                    model=embedding_client.model,
                    dimensions=embedding_client.dimensions,
                )
            )

        batch_updated = repository.update_chunk_embeddings(updates)
        requested += len(candidates)
        embedded += len(vectors)
        updated += batch_updated
        skipped += len(candidates) - batch_updated
        if batch_updated == 0:
            break

    return RagEmbeddingPipelineResult(
        requested_chunks=requested,
        embedded_chunks=embedded,
        updated_chunks=updated,
        skipped_chunks=skipped,
    )


__all__ = [
    "RagEmbeddingPipelineError",
    "RagEmbeddingPipelineResult",
    "embed_changed_chunks",
]
