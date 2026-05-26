"""Tests for RAG persistence repositories."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from rag.ingestion.pipeline import CORPUS_NAME, CORPUS_VERSION, build_rag_corpus
from repositories.rag.repository import (
    InMemoryRagRepository,
    PostgresRagRepository,
    RagEmbeddingUpdate,
    compute_rag_run_id,
)


def _small_corpus_slice():
    result = build_rag_corpus()
    document = next(
        document
        for document in result.documents
        if document.document_id == "technique.active_recall"
    )
    chunk = next(
        chunk for chunk in result.chunks if chunk.document_id == document.document_id
    )
    relation = next(
        relation
        for relation in result.relations
        if relation.source_document_id == document.document_id
    )
    return document, chunk, relation


def test_compute_rag_run_id_is_stable_for_same_corpus_snapshot() -> None:
    document, chunk, relation = _small_corpus_slice()

    first = compute_rag_run_id(
        corpus_name=CORPUS_NAME,
        corpus_version=CORPUS_VERSION,
        documents=[document],
        chunks=[chunk],
        relations=[relation],
    )
    second = compute_rag_run_id(
        corpus_name=CORPUS_NAME,
        corpus_version=CORPUS_VERSION,
        documents=[document],
        chunks=[chunk],
        relations=[relation],
    )

    assert first == second
    assert first.startswith(f"{CORPUS_NAME}.")


def test_in_memory_rag_repository_preserves_embeddings_when_chunk_is_unchanged() -> None:
    document, chunk, relation = _small_corpus_slice()
    repository = InMemoryRagRepository()

    first = repository.sync_corpus_snapshot(
        corpus_name=CORPUS_NAME,
        corpus_version=CORPUS_VERSION,
        source_root="knowledge_base/study_recommendations",
        documents=[document],
        chunks=[chunk],
        relations=[relation],
        run_id="run-stable",
    )
    repository._chunks[chunk.chunk_id]["embedding"] = [0.1, 0.2, 0.3]
    second = repository.sync_corpus_snapshot(
        corpus_name=CORPUS_NAME,
        corpus_version=CORPUS_VERSION,
        source_root="knowledge_base/study_recommendations",
        documents=[document],
        chunks=[chunk],
        relations=[relation],
        run_id="run-stable",
    )

    assert first.ingestion_run_id == second.ingestion_run_id
    assert repository._chunks[chunk.chunk_id]["embedding"] == [0.1, 0.2, 0.3]


def test_in_memory_rag_repository_clears_embedding_when_chunk_changes() -> None:
    document, chunk, relation = _small_corpus_slice()
    repository = InMemoryRagRepository()
    repository.sync_corpus_snapshot(
        corpus_name=CORPUS_NAME,
        corpus_version=CORPUS_VERSION,
        source_root="knowledge_base/study_recommendations",
        documents=[document],
        chunks=[chunk],
        relations=[relation],
        run_id="run-before-change",
    )
    repository._chunks[chunk.chunk_id]["embedding"] = [0.1, 0.2, 0.3]

    changed_chunk = chunk.model_copy(
        update={
            "content": f"{chunk.content}\n\nCambio controlado para test.",
            "checksum": "a" * 64,
        }
    )
    repository.sync_corpus_snapshot(
        corpus_name=CORPUS_NAME,
        corpus_version=CORPUS_VERSION,
        source_root="knowledge_base/study_recommendations",
        documents=[document],
        chunks=[changed_chunk],
        relations=[relation],
        run_id="run-after-change",
    )

    assert repository._chunks[chunk.chunk_id]["embedding"] is None


def test_in_memory_rag_repository_clears_and_skips_disabled_chunk_embeddings() -> None:
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
        run_id="disabled-embedding-before",
    )
    repository._chunks[metadata_chunk.chunk_id]["embedding"] = [0.1, 0.2, 0.3]

    repository.sync_corpus_snapshot(
        corpus_name=CORPUS_NAME,
        corpus_version=CORPUS_VERSION,
        source_root="knowledge_base/study_recommendations",
        documents=[document],
        chunks=[metadata_chunk],
        relations=[],
        run_id="disabled-embedding-after",
    )
    updated = repository.update_chunk_embeddings(
        [
            RagEmbeddingUpdate(
                chunk_id=metadata_chunk.chunk_id,
                checksum=metadata_chunk.checksum,
                embedding=[0.1, 0.2, 0.3],
                provider="fake",
                model="fake-model",
                dimensions=3,
            )
        ]
    )

    assert repository._chunks[metadata_chunk.chunk_id]["embedding"] is None
    assert repository.list_chunks_missing_embeddings(limit=10) == []
    assert updated == 0


def test_in_memory_rag_repository_excludes_structured_metadata_from_normal_search() -> None:
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
        run_id="metadata-search-test",
    )
    repository._chunks[metadata_chunk.chunk_id]["embedding"] = [1.0, 0.0, 0.0]

    lexical_results = repository.search_chunks_lexical(
        query_text="technique_id objective_types",
        filters={"document_ids": [metadata_chunk.document_id]},
        limit=10,
    )
    vector_results = repository.search_chunks_vector(
        query_embedding=[1.0, 0.0, 0.0],
        filters={"document_ids": [metadata_chunk.document_id]},
        limit=10,
    )

    assert lexical_results == []
    assert vector_results == []
    assert (
        repository.get_chunks_by_ids(chunk_ids=[metadata_chunk.chunk_id])[0].chunk_id
        == metadata_chunk.chunk_id
    )


class _FakeResult:
    def __init__(self, row=None, *, rows=None, rowcount=0):
        self._row = row
        self._rows = list(rows or [])
        self.rowcount = rowcount

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class _FakeConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple | None]] = []
        self.commit_called = False

    def execute(self, query, params=None):
        self.executed.append((query, params))
        if "INSERT INTO rag.ingestion_runs" in query:
            return _FakeResult({"id": 101})
        if "SELECT chunk_id, content, checksum, token_estimate" in query:
            return _FakeResult(
                rows=[
                    {
                        "chunk_id": "chunk-1",
                        "content": "contenido para embedding",
                        "checksum": "b" * 64,
                        "token_estimate": 12,
                    }
                ]
            )
        if "UPDATE rag.chunks" in query and "SET embedding" in query:
            return _FakeResult(rowcount=1)
        return _FakeResult(None)

    def commit(self) -> None:
        self.commit_called = True


@contextmanager
def _fake_connect(connection: _FakeConnection):
    yield connection


def test_postgres_rag_repository_upserts_documents_chunks_and_relations() -> None:
    document, chunk, relation = _small_corpus_slice()
    connection = _FakeConnection()
    repository = PostgresRagRepository("postgresql://ignored")
    repository._connect = lambda: _fake_connect(connection)

    persisted = repository.sync_corpus_snapshot(
        corpus_name=CORPUS_NAME,
        corpus_version=CORPUS_VERSION,
        source_root="knowledge_base/study_recommendations",
        documents=[document],
        chunks=[chunk],
        relations=[relation],
        run_id="run-postgres-test",
    )

    assert persisted.ingestion_run_id == 101
    assert persisted.documents_count == 1
    assert persisted.chunks_count == 1
    assert persisted.relations_count == 1
    assert connection.commit_called is True
    assert sum("INSERT INTO rag.documents" in query for query, _ in connection.executed) == 1
    assert sum("INSERT INTO rag.chunks" in query for query, _ in connection.executed) == 1
    assert sum("INSERT INTO rag.relations" in query for query, _ in connection.executed) == 1
    assert any(
        "embedding = CASE" in query and "THEN rag.chunks.embedding" in query
        for query, _ in connection.executed
    )
    assert any(
        "metadata_json->>'embedding_enabled'" in query
        and "EXCLUDED.chunk_kind = 'metadata'" in query
        for query, _ in connection.executed
    )
    assert any(
        "DELETE FROM rag.documents" in query for query, _ in connection.executed
    )
    assert any(
        "status = 'completed'" in query and "UPDATE rag.ingestion_runs" in query
        for query, _ in connection.executed
    )


def test_postgres_rag_repository_lists_and_updates_missing_embeddings() -> None:
    connection = _FakeConnection()
    repository = PostgresRagRepository("postgresql://ignored")
    repository._connect = lambda: _fake_connect(connection)

    candidates = repository.list_chunks_missing_embeddings(limit=5)
    updated = repository.update_chunk_embeddings(
        [
            RagEmbeddingUpdate(
                chunk_id="chunk-1",
                checksum="b" * 64,
                embedding=[0.1, 0.2, 0.3],
                provider="fake",
                model="fake-model",
                dimensions=3,
            )
        ]
    )

    assert candidates[0].chunk_id == "chunk-1"
    assert candidates[0].checksum == "b" * 64
    assert updated == 1
    assert connection.commit_called is True
    assert any(
        "WHERE embedding IS NULL" in query for query, _ in connection.executed
    )
    assert any(
        "metadata_json->>'embedding_enabled'" in query
        and "metadata_json->>'retrieval_role'" in query
        and "chunk_kind <> 'metadata'" in query
        for query, _ in connection.executed
        if "SELECT chunk_id, content, checksum, token_estimate" in query
    )
    update_params = [
        params
        for query, params in connection.executed
        if "UPDATE rag.chunks" in query and "SET embedding" in query
    ][0]
    update_query = [
        query
        for query, _ in connection.executed
        if "UPDATE rag.chunks" in query and "SET embedding" in query
    ][0]
    assert update_params[0] == "[0.1,0.2,0.3]"
    assert update_params[2] == "chunk-1"
    assert update_params[3] == "b" * 64
    assert "metadata_json->>'embedding_enabled'" in update_query
    assert "metadata_json->>'retrieval_role'" in update_query
    assert "chunk_kind <> 'metadata'" in update_query


def test_postgres_rag_repository_orders_lexical_filter_params_after_select_params() -> None:
    connection = _FakeConnection()
    repository = PostgresRagRepository("postgresql://ignored")
    repository._connect = lambda: _fake_connect(connection)

    repository.search_chunks_lexical(
        query_text="Pomodoro",
        filters={"knowledge_types": ["technique"]},
        limit=5,
    )

    lexical_params = [
        params
        for query, params in connection.executed
        if "websearch_to_tsquery" in query
    ][0]
    lexical_query = [
        query
        for query, _ in connection.executed
        if "websearch_to_tsquery" in query
    ][0]
    assert lexical_params == (
        "Pomodoro",
        "%Pomodoro%",
        "%Pomodoro%",
        ["technique"],
        "%Pomodoro%",
        "%Pomodoro%",
        "%Pomodoro%",
        5,
    )
    assert "metadata_json->>'retrieval_role'" in lexical_query
    assert "metadata_json->>'semantic_retrieval_enabled'" in lexical_query
    assert "c.chunk_kind <> 'metadata'" in lexical_query


def test_rag_migration_defines_schema_tables_fts_and_vector_index() -> None:
    migration = Path("migrations/0016_rag_study_recommendations.sql").read_text(
        encoding="utf-8"
    )

    assert "FROM pg_extension" in migration
    assert "pgvector extension is required" in migration
    assert "CREATE SCHEMA IF NOT EXISTS rag" in migration
    assert "CREATE TABLE IF NOT EXISTS rag.ingestion_runs" in migration
    assert "CREATE TABLE IF NOT EXISTS rag.documents" in migration
    assert "CREATE TABLE IF NOT EXISTS rag.chunks" in migration
    assert "CREATE TABLE IF NOT EXISTS rag.relations" in migration
    assert "content_tsv TSVECTOR GENERATED ALWAYS AS" in migration
    assert "ON rag.chunks USING GIN (content_tsv)" in migration
    assert "ON rag.chunks USING hnsw (embedding vector_cosine_ops)" in migration
    assert "embedding VECTOR(1536) NULL" in migration
