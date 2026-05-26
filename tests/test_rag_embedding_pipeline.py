"""Tests for the incremental RAG embedding pipeline."""

from __future__ import annotations

import pytest

from rag.ingestion.embedding_pipeline import (
    RagEmbeddingPipelineError,
    embed_changed_chunks,
)
from rag.ingestion.pipeline import CORPUS_NAME, CORPUS_VERSION, build_rag_corpus
from repositories.rag import InMemoryRagRepository


class _FakeEmbeddingClient:
    provider = "fake"
    model = "fake-embedding"

    def __init__(self, *, dimensions: int = 3, mismatch: bool = False) -> None:
        self.dimensions = dimensions
        self.mismatch = mismatch
        self.calls: list[list[str]] = []

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        size = self.dimensions - 1 if self.mismatch else self.dimensions
        return [[float(index + offset) for offset in range(size)] for index, _ in enumerate(texts)]


def _repository_with_three_chunks() -> InMemoryRagRepository:
    result = build_rag_corpus()
    document = next(document for document in result.documents if document.document_id == "technique.active_recall")
    chunks = [
        chunk
        for chunk in result.chunks
        if chunk.document_id == document.document_id
    ][:3]
    relations = [
        relation
        for relation in result.relations
        if relation.source_document_id == document.document_id
    ][:2]
    repository = InMemoryRagRepository()
    repository.sync_corpus_snapshot(
        corpus_name=CORPUS_NAME,
        corpus_version=CORPUS_VERSION,
        source_root="knowledge_base/study_recommendations",
        documents=[document],
        chunks=chunks,
        relations=relations,
        run_id="embedding-test-run",
    )
    return repository


def test_embed_changed_chunks_updates_missing_embeddings_in_batches() -> None:
    repository = _repository_with_three_chunks()
    client = _FakeEmbeddingClient(dimensions=3)

    result = embed_changed_chunks(
        repository=repository,
        embedding_client=client,
        batch_size=2,
    )

    assert result.requested_chunks == 3
    assert result.embedded_chunks == 3
    assert result.updated_chunks == 3
    assert result.skipped_chunks == 0
    assert [len(call) for call in client.calls] == [2, 1]
    assert all(chunk["embedding"] is not None for chunk in repository._chunks.values())


def test_embed_changed_chunks_respects_limit() -> None:
    repository = _repository_with_three_chunks()
    client = _FakeEmbeddingClient(dimensions=3)

    result = embed_changed_chunks(
        repository=repository,
        embedding_client=client,
        batch_size=2,
        limit=2,
    )

    assert result.requested_chunks == 2
    assert result.updated_chunks == 2
    assert len(repository.list_chunks_missing_embeddings(limit=10)) == 1


def test_embed_changed_chunks_skips_structured_metadata_chunks() -> None:
    result = build_rag_corpus()
    metadata_chunk = next(
        chunk
        for chunk in result.chunks
        if "metadatos_de_recuperacion_sugeridos" in chunk.chunk_id
    )
    document = next(
        document
        for document in result.documents
        if document.document_id == metadata_chunk.document_id
    )
    repository = InMemoryRagRepository()
    repository.sync_corpus_snapshot(
        corpus_name=CORPUS_NAME,
        corpus_version=CORPUS_VERSION,
        source_root="knowledge_base/study_recommendations",
        documents=[document],
        chunks=[metadata_chunk],
        relations=[],
        run_id="metadata-embedding-test",
    )
    client = _FakeEmbeddingClient(dimensions=3)

    result = embed_changed_chunks(
        repository=repository,
        embedding_client=client,
        batch_size=2,
    )

    assert result.requested_chunks == 0
    assert result.embedded_chunks == 0
    assert result.updated_chunks == 0
    assert result.skipped_chunks == 0
    assert client.calls == []


def test_embed_changed_chunks_rejects_dimension_mismatch() -> None:
    repository = _repository_with_three_chunks()
    client = _FakeEmbeddingClient(dimensions=3, mismatch=True)

    with pytest.raises(RagEmbeddingPipelineError):
        embed_changed_chunks(
            repository=repository,
            embedding_client=client,
            batch_size=2,
        )
