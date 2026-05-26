"""Repository for persisting local RAG corpus artifacts."""

from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator, Protocol

from repositories.common import RepositoryConfigurationError, postgres_connection, require_database_url
from schemas.rag import (
    DEFAULT_RAG_RETRIEVAL_ROLE,
    RAG_RETRIEVAL_ROLES,
    NormalizedRagDocument,
    RagChunk,
    RagRelation,
)


class RagRepositoryError(Exception):
    """Base error for RAG persistence."""


@dataclass(frozen=True)
class PersistedRagIngestionRun:
    """Minimal result returned after syncing a corpus snapshot."""

    ingestion_run_id: int
    run_id: str
    corpus_name: str
    corpus_version: str
    documents_count: int
    chunks_count: int
    relations_count: int


@dataclass(frozen=True)
class RagEmbeddingCandidate:
    """Chunk pending embedding generation."""

    chunk_id: str
    content: str
    checksum: str
    token_estimate: int


@dataclass(frozen=True)
class RagEmbeddingUpdate:
    """Embedding update guarded by the source chunk checksum."""

    chunk_id: str
    checksum: str
    embedding: list[float]
    provider: str
    model: str
    dimensions: int


@dataclass(frozen=True)
class RagChunkSearchResult:
    """Search result returned by lexical or vector retrieval."""

    chunk_id: str
    document_id: str
    knowledge_type: str
    document_type: str
    entity_id: str
    section_title: str
    chunk_kind: str
    content: str
    metadata: dict[str, object]
    token_estimate: int
    retrieval_role: str = "answerable"
    semantic_score: float = 0.0
    lexical_score: float = 0.0


class RagRepository(Protocol):
    """Contract for storing normalized RAG corpus snapshots."""

    def sync_corpus_snapshot(
        self,
        *,
        corpus_name: str,
        corpus_version: str,
        source_root: str,
        documents: list[NormalizedRagDocument],
        chunks: list[RagChunk],
        relations: list[RagRelation],
        run_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> PersistedRagIngestionRun: ...

    def list_chunks_missing_embeddings(
        self,
        *,
        limit: int,
    ) -> list[RagEmbeddingCandidate]: ...

    def update_chunk_embeddings(
        self,
        updates: list[RagEmbeddingUpdate],
    ) -> int: ...

    def search_chunks_lexical(
        self,
        *,
        query_text: str,
        filters: dict[str, list[str]],
        limit: int,
    ) -> list[RagChunkSearchResult]: ...

    def search_chunks_vector(
        self,
        *,
        query_embedding: list[float],
        filters: dict[str, list[str]],
        limit: int,
    ) -> list[RagChunkSearchResult]: ...

    def get_chunks_by_ids(
        self,
        *,
        chunk_ids: list[str],
    ) -> list[RagChunkSearchResult]: ...

    def list_relations_for_entities(
        self,
        *,
        entity_ids: list[str],
        relation_types: list[str] | None = None,
        limit: int = 50,
    ) -> list[RagRelation]: ...


class InMemoryRagRepository:
    """In-memory repository used by unit tests and service fallbacks."""

    def __init__(self) -> None:
        self._next_run_id = 1
        self._runs: dict[str, dict[str, Any]] = {}
        self._documents: dict[str, dict[str, Any]] = {}
        self._chunks: dict[str, dict[str, Any]] = {}
        self._relations: dict[str, dict[str, Any]] = {}

    def sync_corpus_snapshot(
        self,
        *,
        corpus_name: str,
        corpus_version: str,
        source_root: str,
        documents: list[NormalizedRagDocument],
        chunks: list[RagChunk],
        relations: list[RagRelation],
        run_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> PersistedRagIngestionRun:
        effective_run_id = run_id or compute_rag_run_id(
            corpus_name=corpus_name,
            corpus_version=corpus_version,
            documents=documents,
            chunks=chunks,
            relations=relations,
        )
        existing_run = self._runs.get(effective_run_id)
        ingestion_run_id = (
            int(existing_run["id"]) if existing_run is not None else self._next_run_id
        )
        if existing_run is None:
            self._next_run_id += 1

        document_ids = {document.document_id for document in documents}
        chunk_ids = {chunk.chunk_id for chunk in chunks}
        relation_ids = {relation.relation_id for relation in relations}

        for document in documents:
            self._documents[document.document_id] = _document_payload(
                document,
                ingestion_run_id=ingestion_run_id,
                corpus_name=corpus_name,
            )

        for chunk in chunks:
            previous = self._chunks.get(chunk.chunk_id)
            payload = _chunk_payload(
                chunk,
                ingestion_run_id=ingestion_run_id,
                corpus_name=corpus_name,
            )
            if (
                previous
                and previous.get("checksum") == chunk.checksum
                and _embedding_enabled_for_payload(payload)
            ):
                payload["embedding"] = previous.get("embedding")
            else:
                payload["embedding"] = None
            self._chunks[chunk.chunk_id] = payload

        for relation in relations:
            self._relations[relation.relation_id] = _relation_payload(
                relation,
                ingestion_run_id=ingestion_run_id,
                corpus_name=corpus_name,
            )

        self._chunks = {
            chunk_id: chunk
            for chunk_id, chunk in self._chunks.items()
            if chunk.get("corpus_name") != corpus_name
            or (chunk["document_id"] in document_ids and chunk_id in chunk_ids)
        }
        self._relations = {
            relation_id: relation
            for relation_id, relation in self._relations.items()
            if relation.get("corpus_name") != corpus_name
            or (
                relation["source_document_id"] in document_ids
                and relation_id in relation_ids
            )
        }
        self._documents = {
            document_id: document
            for document_id, document in self._documents.items()
            if document.get("corpus_name") != corpus_name or document_id in document_ids
        }

        self._runs[effective_run_id] = {
            "id": ingestion_run_id,
            "run_id": effective_run_id,
            "corpus_name": corpus_name,
            "corpus_version": corpus_version,
            "source_root": source_root,
            "status": "completed",
            "documents_count": len(documents),
            "chunks_count": len(chunks),
            "relations_count": len(relations),
            "metadata": dict(metadata or {}),
        }

        return PersistedRagIngestionRun(
            ingestion_run_id=ingestion_run_id,
            run_id=effective_run_id,
            corpus_name=corpus_name,
            corpus_version=corpus_version,
            documents_count=len(documents),
            chunks_count=len(chunks),
            relations_count=len(relations),
        )

    def list_chunks_missing_embeddings(
        self,
        *,
        limit: int,
    ) -> list[RagEmbeddingCandidate]:
        candidates: list[RagEmbeddingCandidate] = []
        for chunk in sorted(self._chunks.values(), key=lambda item: item["chunk_id"]):
            if not _embedding_enabled_for_payload(chunk):
                continue
            if chunk.get("embedding") is not None:
                continue
            candidates.append(
                RagEmbeddingCandidate(
                    chunk_id=str(chunk["chunk_id"]),
                    content=str(chunk["content"]),
                    checksum=str(chunk["checksum"]),
                    token_estimate=int(chunk["token_estimate"]),
                )
            )
            if len(candidates) >= limit:
                break
        return candidates

    def update_chunk_embeddings(
        self,
        updates: list[RagEmbeddingUpdate],
    ) -> int:
        updated = 0
        for update in updates:
            chunk = self._chunks.get(update.chunk_id)
            if (
                chunk is None
                or chunk.get("checksum") != update.checksum
                or not _embedding_enabled_for_payload(chunk)
            ):
                continue
            if len(update.embedding) != update.dimensions:
                raise RagRepositoryError(
                    f"Embedding dimension mismatch for chunk {update.chunk_id}: "
                    f"expected {update.dimensions}, got {len(update.embedding)}."
                )
            chunk["embedding"] = [float(value) for value in update.embedding]
            metadata = dict(chunk.get("metadata") or {})
            metadata["embedding"] = {
                "provider": update.provider,
                "model": update.model,
                "dimensions": update.dimensions,
                "checksum": update.checksum,
            }
            chunk["metadata"] = metadata
            updated += 1
        return updated

    def search_chunks_lexical(
        self,
        *,
        query_text: str,
        filters: dict[str, list[str]],
        limit: int,
    ) -> list[RagChunkSearchResult]:
        query_terms = _search_terms(query_text)
        if not query_terms:
            return []
        results: list[RagChunkSearchResult] = []
        for chunk in self._chunks.values():
            if not _normal_retrieval_enabled_for_payload(chunk):
                continue
            if not _chunk_matches_filters(chunk, filters):
                continue
            haystack = " ".join(
                [
                    str(chunk.get("content") or ""),
                    str(chunk.get("section_title") or ""),
                    str(chunk.get("entity_id") or ""),
                ]
            ).lower()
            score = sum(1 for term in query_terms if term in haystack) / max(
                1,
                len(query_terms),
            )
            if score <= 0:
                continue
            results.append(_search_result_from_payload(chunk, lexical_score=score))
        return sorted(results, key=lambda item: item.lexical_score, reverse=True)[:limit]

    def search_chunks_vector(
        self,
        *,
        query_embedding: list[float],
        filters: dict[str, list[str]],
        limit: int,
    ) -> list[RagChunkSearchResult]:
        results: list[RagChunkSearchResult] = []
        for chunk in self._chunks.values():
            if not _normal_retrieval_enabled_for_payload(chunk):
                continue
            if not _chunk_matches_filters(chunk, filters):
                continue
            embedding = chunk.get("embedding")
            if not isinstance(embedding, list):
                continue
            score = _cosine_similarity(query_embedding, [float(value) for value in embedding])
            results.append(_search_result_from_payload(chunk, semantic_score=score))
        return sorted(results, key=lambda item: item.semantic_score, reverse=True)[:limit]

    def get_chunks_by_ids(
        self,
        *,
        chunk_ids: list[str],
    ) -> list[RagChunkSearchResult]:
        results: list[RagChunkSearchResult] = []
        for chunk_id in chunk_ids:
            chunk = self._chunks.get(chunk_id)
            if chunk is None:
                continue
            results.append(_search_result_from_payload(chunk))
        return results

    def list_relations_for_entities(
        self,
        *,
        entity_ids: list[str],
        relation_types: list[str] | None = None,
        limit: int = 50,
    ) -> list[RagRelation]:
        entity_set = set(entity_ids)
        relation_type_set = set(relation_types or [])
        relations: list[RagRelation] = []
        for relation in self._relations.values():
            if relation_type_set and relation["relation_type"] not in relation_type_set:
                continue
            if relation["source_id"] not in entity_set and relation["target_id"] not in entity_set:
                continue
            relations.append(_relation_from_payload(relation))
        return sorted(relations, key=lambda item: item.relation_id)[:limit]


class PostgresRagRepository:
    """PostgreSQL repository for RAG documents, chunks and relations."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    def sync_corpus_snapshot(
        self,
        *,
        corpus_name: str,
        corpus_version: str,
        source_root: str,
        documents: list[NormalizedRagDocument],
        chunks: list[RagChunk],
        relations: list[RagRelation],
        run_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> PersistedRagIngestionRun:
        effective_run_id = run_id or compute_rag_run_id(
            corpus_name=corpus_name,
            corpus_version=corpus_version,
            documents=documents,
            chunks=chunks,
            relations=relations,
        )
        metadata_payload = dict(metadata or {})
        metadata_payload.setdefault("documents_count", len(documents))
        metadata_payload.setdefault("chunks_count", len(chunks))
        metadata_payload.setdefault("relations_count", len(relations))

        with self._connect() as conn:
            run_row = conn.execute(
                """
                INSERT INTO rag.ingestion_runs (
                    run_id,
                    corpus_name,
                    corpus_version,
                    source_root,
                    status,
                    documents_count,
                    chunks_count,
                    relations_count,
                    metadata_json,
                    started_at,
                    finished_at
                ) VALUES (
                    %s, %s, %s, %s, 'started', %s, %s, %s, %s::jsonb, NOW(), NULL
                )
                ON CONFLICT (run_id) DO UPDATE
                SET corpus_name = EXCLUDED.corpus_name,
                    corpus_version = EXCLUDED.corpus_version,
                    source_root = EXCLUDED.source_root,
                    status = 'started',
                    documents_count = EXCLUDED.documents_count,
                    chunks_count = EXCLUDED.chunks_count,
                    relations_count = EXCLUDED.relations_count,
                    metadata_json = EXCLUDED.metadata_json,
                    started_at = NOW(),
                    finished_at = NULL
                RETURNING id
                """,
                (
                    effective_run_id,
                    corpus_name,
                    corpus_version,
                    source_root,
                    len(documents),
                    len(chunks),
                    len(relations),
                    _json(metadata_payload),
                ),
            ).fetchone()
            ingestion_run_id = int(_row_value(run_row, "id"))

            for document in documents:
                self._upsert_document(conn, document, ingestion_run_id, corpus_name)

            for chunk in chunks:
                self._upsert_chunk(conn, chunk, ingestion_run_id)

            for relation in relations:
                self._upsert_relation(conn, relation, ingestion_run_id)

            self._delete_stale_rows(
                conn,
                corpus_name=corpus_name,
                document_ids=[document.document_id for document in documents],
                chunk_ids=[chunk.chunk_id for chunk in chunks],
                relation_ids=[relation.relation_id for relation in relations],
            )

            conn.execute(
                """
                UPDATE rag.ingestion_runs
                SET status = 'completed',
                    documents_count = %s,
                    chunks_count = %s,
                    relations_count = %s,
                    finished_at = NOW()
                WHERE id = %s
                """,
                (len(documents), len(chunks), len(relations), ingestion_run_id),
            )
            conn.commit()

        return PersistedRagIngestionRun(
            ingestion_run_id=ingestion_run_id,
            run_id=effective_run_id,
            corpus_name=corpus_name,
            corpus_version=corpus_version,
            documents_count=len(documents),
            chunks_count=len(chunks),
            relations_count=len(relations),
        )

    def list_chunks_missing_embeddings(
        self,
        *,
        limit: int,
    ) -> list[RagEmbeddingCandidate]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT chunk_id, content, checksum, token_estimate
                FROM rag.chunks
                WHERE embedding IS NULL
                  AND COALESCE(metadata_json->>'embedding_enabled', 'true') <> 'false'
                  AND COALESCE(metadata_json->>'retrieval_role', 'answerable') <> 'structured_metadata'
                  AND chunk_kind <> 'metadata'
                ORDER BY document_id, position_in_document
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
        return [
            RagEmbeddingCandidate(
                chunk_id=str(_row_value(row, "chunk_id")),
                content=str(_row_value(row, "content")),
                checksum=str(_row_value(row, "checksum")),
                token_estimate=int(_row_value(row, "token_estimate", 0)),
            )
            for row in rows
        ]

    def update_chunk_embeddings(
        self,
        updates: list[RagEmbeddingUpdate],
    ) -> int:
        updated = 0
        with self._connect() as conn:
            for update in updates:
                if len(update.embedding) != update.dimensions:
                    raise RagRepositoryError(
                        f"Embedding dimension mismatch for chunk {update.chunk_id}: "
                        f"expected {update.dimensions}, got {len(update.embedding)}."
                    )
                result = conn.execute(
                    """
                    UPDATE rag.chunks
                    SET embedding = %s::vector,
                        metadata_json = metadata_json || %s::jsonb,
                        updated_at = NOW()
                    WHERE chunk_id = %s
                      AND checksum = %s
                      AND COALESCE(metadata_json->>'embedding_enabled', 'true') <> 'false'
                      AND COALESCE(metadata_json->>'retrieval_role', 'answerable') <> 'structured_metadata'
                      AND chunk_kind <> 'metadata'
                    """,
                    (
                        _embedding_literal(update.embedding),
                        _json(
                            {
                                "embedding": {
                                    "provider": update.provider,
                                    "model": update.model,
                                    "dimensions": update.dimensions,
                                    "checksum": update.checksum,
                                }
                            }
                        ),
                        update.chunk_id,
                        update.checksum,
                    ),
                )
                updated += int(getattr(result, "rowcount", 0) or 0)
            conn.commit()
        return updated

    def search_chunks_lexical(
        self,
        *,
        query_text: str,
        filters: dict[str, list[str]],
        limit: int,
    ) -> list[RagChunkSearchResult]:
        if not query_text.strip():
            return []
        where_sql, params = _build_chunk_filter_sql(filters)
        like_query = f"%{query_text.strip()}%"
        sql = f"""
            WITH q AS (
                SELECT websearch_to_tsquery('spanish', %s) AS query
            )
            SELECT
                c.chunk_id,
                c.document_id,
                c.knowledge_type,
                c.document_type,
                c.entity_id,
                c.section_title,
                c.chunk_kind,
                c.content,
                c.metadata_json,
                c.token_estimate,
                (
                    ts_rank_cd(c.content_tsv, q.query)
                    + CASE WHEN c.entity_id ILIKE %s THEN 1.0 ELSE 0.0 END
                    + CASE WHEN c.section_title ILIKE %s THEN 0.5 ELSE 0.0 END
                ) AS lexical_score
            FROM rag.chunks c, q
            WHERE {where_sql}
              AND (
                c.content_tsv @@ q.query
                OR c.content ILIKE %s
                OR c.entity_id ILIKE %s
                OR c.section_title ILIKE %s
              )
            ORDER BY lexical_score DESC, c.document_id, c.position_in_document
            LIMIT %s
        """
        with self._connect() as conn:
            rows = conn.execute(
                sql,
                (
                    query_text,
                    like_query,
                    like_query,
                    *params,
                    like_query,
                    like_query,
                    like_query,
                    limit,
                ),
            ).fetchall()
        return [_search_result_from_row(row, lexical_score_key="lexical_score") for row in rows]

    def search_chunks_vector(
        self,
        *,
        query_embedding: list[float],
        filters: dict[str, list[str]],
        limit: int,
    ) -> list[RagChunkSearchResult]:
        where_sql, params = _build_chunk_filter_sql(filters, require_embedding=True)
        sql = f"""
            SELECT
                c.chunk_id,
                c.document_id,
                c.knowledge_type,
                c.document_type,
                c.entity_id,
                c.section_title,
                c.chunk_kind,
                c.content,
                c.metadata_json,
                c.token_estimate,
                (1.0 - (c.embedding <=> %s::vector)) AS semantic_score
            FROM rag.chunks c
            WHERE {where_sql}
            ORDER BY c.embedding <=> %s::vector, c.document_id, c.position_in_document
            LIMIT %s
        """
        embedding_literal = _embedding_literal(query_embedding)
        with self._connect() as conn:
            rows = conn.execute(
                sql,
                (
                    embedding_literal,
                    *params,
                    embedding_literal,
                    limit,
                ),
            ).fetchall()
        return [_search_result_from_row(row, semantic_score_key="semantic_score") for row in rows]

    def get_chunks_by_ids(
        self,
        *,
        chunk_ids: list[str],
    ) -> list[RagChunkSearchResult]:
        if not chunk_ids:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    c.chunk_id,
                    c.document_id,
                    c.knowledge_type,
                    c.document_type,
                    c.entity_id,
                    c.section_title,
                    c.chunk_kind,
                    c.content,
                    c.metadata_json,
                    c.token_estimate
                FROM rag.chunks c
                WHERE c.chunk_id = ANY(%s)
                """,
                (chunk_ids,),
            ).fetchall()
        chunks_by_id = {
            result.chunk_id: result
            for result in [_search_result_from_row(row) for row in rows]
        }
        return [chunks_by_id[chunk_id] for chunk_id in chunk_ids if chunk_id in chunks_by_id]

    def list_relations_for_entities(
        self,
        *,
        entity_ids: list[str],
        relation_types: list[str] | None = None,
        limit: int = 50,
    ) -> list[RagRelation]:
        if not entity_ids:
            return []
        relation_filter = ""
        params: list[object] = [entity_ids, entity_ids]
        if relation_types:
            relation_filter = "AND relation_type = ANY(%s)"
            params.append(relation_types)
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    relation_id,
                    source_type,
                    source_id,
                    relation_type,
                    target_type,
                    target_id,
                    weight,
                    evidence_text,
                    source_document_id,
                    source_chunk_id,
                    metadata_json
                FROM rag.relations
                WHERE (source_id = ANY(%s) OR target_id = ANY(%s))
                  {relation_filter}
                ORDER BY weight DESC, relation_id
                LIMIT %s
                """,
                tuple(params),
            ).fetchall()
        return [_relation_from_row(row) for row in rows]

    def _upsert_document(
        self,
        conn: Any,
        document: NormalizedRagDocument,
        ingestion_run_id: int,
        corpus_name: str,
    ) -> None:
        metadata_json = document.metadata.model_dump(mode="json")
        metadata_json["corpus_name"] = corpus_name
        conn.execute(
            """
            INSERT INTO rag.documents (
                document_id,
                knowledge_type,
                document_type,
                entity_id,
                name,
                aliases,
                status,
                version,
                source_path,
                checksum,
                metadata_json,
                ingestion_run_id
            ) VALUES (
                %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s::jsonb, %s
            )
            ON CONFLICT (document_id) DO UPDATE
            SET knowledge_type = EXCLUDED.knowledge_type,
                document_type = EXCLUDED.document_type,
                entity_id = EXCLUDED.entity_id,
                name = EXCLUDED.name,
                aliases = EXCLUDED.aliases,
                status = EXCLUDED.status,
                version = EXCLUDED.version,
                source_path = EXCLUDED.source_path,
                checksum = EXCLUDED.checksum,
                metadata_json = EXCLUDED.metadata_json,
                ingestion_run_id = EXCLUDED.ingestion_run_id,
                updated_at = NOW()
            """,
            (
                document.document_id,
                document.knowledge_type,
                document.document_type,
                document.entity_id,
                document.metadata.name,
                _json(document.metadata.aliases),
                document.metadata.status,
                document.metadata.version,
                document.metadata.source_path,
                document.metadata.checksum,
                _json(metadata_json),
                ingestion_run_id,
            ),
        )

    def _upsert_chunk(self, conn: Any, chunk: RagChunk, ingestion_run_id: int) -> None:
        conn.execute(
            """
            INSERT INTO rag.chunks (
                chunk_id,
                document_id,
                knowledge_type,
                document_type,
                entity_id,
                section_title,
                heading_path,
                chunk_kind,
                content,
                metadata_json,
                position_in_document,
                token_estimate,
                checksum,
                ingestion_run_id
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s::jsonb, %s, %s, %s, %s
            )
            ON CONFLICT (chunk_id) DO UPDATE
            SET document_id = EXCLUDED.document_id,
                knowledge_type = EXCLUDED.knowledge_type,
                document_type = EXCLUDED.document_type,
                entity_id = EXCLUDED.entity_id,
                section_title = EXCLUDED.section_title,
                heading_path = EXCLUDED.heading_path,
                chunk_kind = EXCLUDED.chunk_kind,
                content = EXCLUDED.content,
                metadata_json = EXCLUDED.metadata_json,
                embedding = CASE
                    WHEN COALESCE(EXCLUDED.metadata_json->>'embedding_enabled', 'true') = 'false'
                         OR COALESCE(EXCLUDED.metadata_json->>'retrieval_role', 'answerable') = 'structured_metadata'
                         OR EXCLUDED.chunk_kind = 'metadata'
                    THEN NULL
                    WHEN rag.chunks.checksum = EXCLUDED.checksum
                    THEN rag.chunks.embedding
                    ELSE NULL
                END,
                position_in_document = EXCLUDED.position_in_document,
                token_estimate = EXCLUDED.token_estimate,
                checksum = EXCLUDED.checksum,
                ingestion_run_id = EXCLUDED.ingestion_run_id,
                updated_at = NOW()
            """,
            (
                chunk.chunk_id,
                chunk.document_id,
                chunk.knowledge_type,
                chunk.document_type,
                chunk.entity_id,
                chunk.section_title,
                _json(chunk.heading_path),
                chunk.chunk_kind,
                chunk.content,
                _json(chunk.metadata),
                chunk.position_in_document,
                chunk.token_estimate,
                chunk.checksum,
                ingestion_run_id,
            ),
        )

    def _upsert_relation(
        self,
        conn: Any,
        relation: RagRelation,
        ingestion_run_id: int,
    ) -> None:
        conn.execute(
            """
            INSERT INTO rag.relations (
                relation_id,
                source_type,
                source_id,
                relation_type,
                target_type,
                target_id,
                weight,
                evidence_text,
                source_document_id,
                source_chunk_id,
                metadata_json,
                ingestion_run_id
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s
            )
            ON CONFLICT (relation_id) DO UPDATE
            SET source_type = EXCLUDED.source_type,
                source_id = EXCLUDED.source_id,
                relation_type = EXCLUDED.relation_type,
                target_type = EXCLUDED.target_type,
                target_id = EXCLUDED.target_id,
                weight = EXCLUDED.weight,
                evidence_text = EXCLUDED.evidence_text,
                source_document_id = EXCLUDED.source_document_id,
                source_chunk_id = EXCLUDED.source_chunk_id,
                metadata_json = EXCLUDED.metadata_json,
                ingestion_run_id = EXCLUDED.ingestion_run_id
            """,
            (
                relation.relation_id,
                relation.source_type,
                relation.source_id,
                relation.relation_type,
                relation.target_type,
                relation.target_id,
                relation.weight,
                relation.evidence_text,
                relation.source_document_id,
                relation.source_chunk_id,
                _json(relation.metadata),
                ingestion_run_id,
            ),
        )

    def _delete_stale_rows(
        self,
        conn: Any,
        *,
        corpus_name: str,
        document_ids: list[str],
        chunk_ids: list[str],
        relation_ids: list[str],
    ) -> None:
        conn.execute(
            """
            DELETE FROM rag.relations
            WHERE source_document_id = ANY(%s)
              AND relation_id <> ALL(%s)
            """,
            (document_ids, relation_ids),
        )
        conn.execute(
            """
            DELETE FROM rag.chunks
            WHERE document_id = ANY(%s)
              AND chunk_id <> ALL(%s)
            """,
            (document_ids, chunk_ids),
        )
        conn.execute(
            """
            DELETE FROM rag.documents AS d
            USING rag.ingestion_runs AS r
            WHERE d.ingestion_run_id = r.id
              AND r.corpus_name = %s
              AND d.document_id <> ALL(%s)
            """,
            (corpus_name, document_ids),
        )

    @contextmanager
    def _connect(self) -> Iterator[Any]:
        try:
            with postgres_connection(self.database_url) as conn:
                yield conn
        except RepositoryConfigurationError:
            raise
        except Exception as exc:  # pragma: no cover - covers real psycopg failures
            raise RagRepositoryError(str(exc)) from exc


def build_rag_repository(database_url: str) -> RagRepository:
    """Build the PostgreSQL RAG repository or fail explicitly."""

    return PostgresRagRepository(require_database_url(database_url))


def compute_rag_run_id(
    *,
    corpus_name: str,
    corpus_version: str,
    documents: list[NormalizedRagDocument],
    chunks: list[RagChunk],
    relations: list[RagRelation],
) -> str:
    """Compute a deterministic run ID from corpus checksums and relation IDs."""

    digest = hashlib.sha256()
    digest.update(corpus_name.encode("utf-8"))
    digest.update(b"\0")
    digest.update(corpus_version.encode("utf-8"))
    for document in sorted(documents, key=lambda item: item.document_id):
        digest.update(b"\0doc\0")
        digest.update(document.document_id.encode("utf-8"))
        digest.update(document.metadata.checksum.encode("utf-8"))
    for chunk in sorted(chunks, key=lambda item: item.chunk_id):
        digest.update(b"\0chunk\0")
        digest.update(chunk.chunk_id.encode("utf-8"))
        digest.update(chunk.checksum.encode("utf-8"))
    for relation in sorted(relations, key=lambda item: item.relation_id):
        digest.update(b"\0rel\0")
        digest.update(relation.relation_id.encode("utf-8"))
    return f"{corpus_name}.{digest.hexdigest()[:24]}"


def _document_payload(
    document: NormalizedRagDocument,
    *,
    ingestion_run_id: int,
    corpus_name: str,
) -> dict[str, Any]:
    payload = document.metadata.model_dump(mode="json")
    payload["ingestion_run_id"] = ingestion_run_id
    payload["corpus_name"] = corpus_name
    return payload


def _chunk_payload(
    chunk: RagChunk,
    *,
    ingestion_run_id: int,
    corpus_name: str,
) -> dict[str, Any]:
    payload = chunk.model_dump(mode="json")
    payload["ingestion_run_id"] = ingestion_run_id
    payload["corpus_name"] = corpus_name
    return payload


def _relation_payload(
    relation: RagRelation,
    *,
    ingestion_run_id: int,
    corpus_name: str,
) -> dict[str, Any]:
    payload = relation.model_dump(mode="json")
    payload["ingestion_run_id"] = ingestion_run_id
    payload["corpus_name"] = corpus_name
    return payload


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _embedding_literal(values: list[float]) -> str:
    return "[" + ",".join(str(float(value)) for value in values) + "]"


def _row_value(row: Any, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    if key == "id":
        return row[0]
    if key == "chunk_id":
        return row[0]
    if key == "content":
        return row[1]
    if key == "checksum":
        return row[2]
    if key == "token_estimate":
        return row[3]
    return default


def _build_chunk_filter_sql(
    filters: dict[str, list[str]],
    *,
    require_embedding: bool = False,
) -> tuple[str, list[object]]:
    clauses = [
        "COALESCE(c.metadata_json->>'retrieval_role', 'answerable') <> 'structured_metadata'",
        "COALESCE(c.metadata_json->>'semantic_retrieval_enabled', 'true') <> 'false'",
        "c.chunk_kind <> 'metadata'",
    ]
    params: list[object] = []
    column_by_filter = {
        "knowledge_types": "c.knowledge_type",
        "document_types": "c.document_type",
        "entity_ids": "c.entity_id",
        "chunk_kinds": "c.chunk_kind",
        "document_ids": "c.document_id",
    }
    for key, column in column_by_filter.items():
        values = [value for value in filters.get(key, []) if value]
        if not values:
            continue
        clauses.append(f"{column} = ANY(%s)")
        params.append(values)
    if require_embedding:
        clauses.append("c.embedding IS NOT NULL")
    return " AND ".join(clauses), params


def _search_terms(query_text: str) -> list[str]:
    return [
        term
        for term in query_text.lower().replace("_", " ").split()
        if len(term.strip()) >= 3
    ]


def _chunk_matches_filters(chunk: dict[str, Any], filters: dict[str, list[str]]) -> bool:
    key_map = {
        "knowledge_types": "knowledge_type",
        "document_types": "document_type",
        "entity_ids": "entity_id",
        "chunk_kinds": "chunk_kind",
        "document_ids": "document_id",
    }
    for filter_key, chunk_key in key_map.items():
        values = set(filters.get(filter_key, []))
        if values and chunk.get(chunk_key) not in values:
            return False
    return True


def _normal_retrieval_enabled_for_payload(chunk: dict[str, Any]) -> bool:
    metadata = dict(chunk.get("metadata") or {})
    retrieval_role = _retrieval_role_from_chunk_payload(chunk, metadata)
    if retrieval_role == "structured_metadata":
        return False
    if str(chunk.get("chunk_kind") or "") == "metadata":
        return False
    return _metadata_bool(metadata, "semantic_retrieval_enabled", default=True)


def _embedding_enabled_for_payload(chunk: dict[str, Any]) -> bool:
    metadata = dict(chunk.get("metadata") or {})
    retrieval_role = _retrieval_role_from_chunk_payload(chunk, metadata)
    if retrieval_role == "structured_metadata":
        return False
    if str(chunk.get("chunk_kind") or "") == "metadata":
        return False
    return _metadata_bool(metadata, "embedding_enabled", default=True)


def _search_result_from_payload(
    chunk: dict[str, Any],
    *,
    semantic_score: float = 0.0,
    lexical_score: float = 0.0,
) -> RagChunkSearchResult:
    metadata = dict(chunk.get("metadata") or {})
    return RagChunkSearchResult(
        chunk_id=str(chunk["chunk_id"]),
        document_id=str(chunk["document_id"]),
        knowledge_type=str(chunk["knowledge_type"]),
        document_type=str(chunk["document_type"]),
        entity_id=str(chunk["entity_id"]),
        section_title=str(chunk["section_title"]),
        chunk_kind=str(chunk["chunk_kind"]),
        retrieval_role=_retrieval_role_from_chunk_payload(chunk, metadata),
        content=str(chunk["content"]),
        metadata=metadata,
        token_estimate=int(chunk["token_estimate"]),
        semantic_score=float(semantic_score),
        lexical_score=float(lexical_score),
    )


def _search_result_from_row(
    row: Any,
    *,
    semantic_score_key: str | None = None,
    lexical_score_key: str | None = None,
) -> RagChunkSearchResult:
    metadata = _row_value(row, "metadata_json", {}) or {}
    metadata = dict(metadata)
    return RagChunkSearchResult(
        chunk_id=str(_row_value(row, "chunk_id")),
        document_id=str(_row_value(row, "document_id")),
        knowledge_type=str(_row_value(row, "knowledge_type")),
        document_type=str(_row_value(row, "document_type")),
        entity_id=str(_row_value(row, "entity_id")),
        section_title=str(_row_value(row, "section_title")),
        chunk_kind=str(_row_value(row, "chunk_kind")),
        retrieval_role=_retrieval_role_from_metadata(metadata),
        content=str(_row_value(row, "content")),
        metadata=metadata,
        token_estimate=int(_row_value(row, "token_estimate", 0)),
        semantic_score=float(_row_value(row, semantic_score_key or "", 0.0) or 0.0),
        lexical_score=float(_row_value(row, lexical_score_key or "", 0.0) or 0.0),
    )


def _retrieval_role_from_chunk_payload(
    chunk: dict[str, Any],
    metadata: dict[str, object],
) -> str:
    return _retrieval_role_from_metadata(metadata, fallback=chunk.get("retrieval_role"))


def _retrieval_role_from_metadata(
    metadata: dict[str, object],
    *,
    fallback: object = None,
) -> str:
    value = str(
        metadata.get("retrieval_role") or fallback or DEFAULT_RAG_RETRIEVAL_ROLE
    ).strip()
    if value in RAG_RETRIEVAL_ROLES:
        return value
    return DEFAULT_RAG_RETRIEVAL_ROLE


def _metadata_bool(
    metadata: dict[str, object],
    key: str,
    *,
    default: bool,
) -> bool:
    value = metadata.get(key)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"false", "0", "no"}:
            return False
        if normalized in {"true", "1", "yes"}:
            return True
    return bool(value)


def _relation_from_payload(relation: dict[str, Any]) -> RagRelation:
    return RagRelation(
        relation_id=str(relation["relation_id"]),
        source_type=str(relation["source_type"]),
        source_id=str(relation["source_id"]),
        relation_type=str(relation["relation_type"]),
        target_type=str(relation["target_type"]),
        target_id=str(relation["target_id"]),
        weight=float(relation.get("weight", 1.0)),
        evidence_text=str(relation["evidence_text"]),
        source_document_id=str(relation["source_document_id"]),
        source_chunk_id=relation.get("source_chunk_id"),
        metadata=dict(relation.get("metadata") or {}),
    )


def _relation_from_row(row: Any) -> RagRelation:
    return RagRelation(
        relation_id=str(_row_value(row, "relation_id")),
        source_type=str(_row_value(row, "source_type")),
        source_id=str(_row_value(row, "source_id")),
        relation_type=str(_row_value(row, "relation_type")),
        target_type=str(_row_value(row, "target_type")),
        target_id=str(_row_value(row, "target_id")),
        weight=float(_row_value(row, "weight", 1.0) or 1.0),
        evidence_text=str(_row_value(row, "evidence_text")),
        source_document_id=str(_row_value(row, "source_document_id")),
        source_chunk_id=_row_value(row, "source_chunk_id"),
        metadata=dict(_row_value(row, "metadata_json", {}) or {}),
    )


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = sum(value * value for value in left) ** 0.5
    right_norm = sum(value * value for value in right) ** 0.5
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


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
    "compute_rag_run_id",
]
