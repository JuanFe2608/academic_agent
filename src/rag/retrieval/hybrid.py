"""Hybrid lexical/vector retrieval orchestration for RAG."""

from __future__ import annotations

from dataclasses import dataclass

from bootstrap.settings import RagSettings, load_rag_settings
from integrations.embeddings import EmbeddingClient, EmbeddingClientError
from repositories.rag import RagRepository
from schemas.rag import StudyRecommendationQuery

from .context import build_grounded_context_package
from .filters import relaxed_filter_sets
from .models import GroundedContextPackage, QueryUnderstanding, RagRetrievedChunk
from .query import retrieval_search_text, understand_query
from .relations import expand_relations
from .rerank import merge_search_results, rerank_candidates


class RagRetrievalError(Exception):
    """Base error for RAG retrieval."""


@dataclass(frozen=True)
class RetrievalAttempt:
    """One filter attempt during controlled degradation."""

    filters: dict[str, list[str]]
    candidates: list[RagRetrievedChunk]
    notes: list[str]


class HybridRagRetriever:
    """Run structured hybrid retrieval without depending on LangGraph."""

    def __init__(
        self,
        *,
        repository: RagRepository,
        embedding_client: EmbeddingClient | None = None,
        settings: RagSettings | None = None,
    ) -> None:
        self.repository = repository
        self.embedding_client = embedding_client
        self.settings = settings or load_rag_settings()

    def retrieve(self, query: StudyRecommendationQuery) -> GroundedContextPackage:
        """Return a grounded context package for a study recommendation query."""

        understanding = understand_query(query)
        search_text = retrieval_search_text(query, understanding)
        if not search_text:
            return build_grounded_context_package(
                query=query,
                understanding=understanding,
                chunks=[],
                relations=[],
                notes=["fallback:empty_query"],
            )

        attempts = relaxed_filter_sets(query, understanding)
        attempt_notes: list[str] = []
        candidates: list[RagRetrievedChunk] = []
        used_filters: dict[str, list[str]] = {}
        for filters in attempts:
            attempt = self._retrieve_with_filters(
                search_text=search_text,
                understanding=understanding,
                filters=filters,
            )
            attempt_notes.extend(attempt.notes)
            if attempt.candidates:
                candidates = attempt.candidates
                used_filters = filters
                break

        if not candidates:
            return build_grounded_context_package(
                query=query,
                understanding=understanding,
                chunks=[],
                relations=[],
                notes=attempt_notes or ["fallback:no_candidates"],
            )

        initially_ranked = rerank_candidates(
            candidates=candidates,
            query=query,
            understanding=understanding,
        )
        relations = expand_relations(
            repository=self.repository,
            query=query,
            understanding=understanding,
            chunks=initially_ranked,
            limit=50,
        )
        ranked = rerank_candidates(
            candidates=initially_ranked,
            query=query,
            understanding=understanding,
            relations=relations,
        )
        top_k = max(1, query.max_chunks or self.settings.top_k_final)
        eligible = [
            chunk
            for chunk in ranked
            if chunk.final_score >= self.settings.min_score
        ]
        selected = _select_diverse_chunks(
            eligible,
            understanding=understanding,
            top_k=top_k,
        )
        notes = [
            *attempt_notes,
            f"filters:{_format_filters(used_filters)}",
            f"candidates:{len(candidates)}",
        ]
        return build_grounded_context_package(
            query=query,
            understanding=understanding,
            chunks=selected,
            relations=relations,
            notes=notes,
        )

    def _retrieve_with_filters(
        self,
        *,
        search_text: str,
        understanding: QueryUnderstanding,
        filters: dict[str, list[str]],
    ) -> RetrievalAttempt:
        notes = [f"attempt_filters:{_format_filters(filters)}"]
        lexical_results = self.repository.search_chunks_lexical(
            query_text=search_text,
            filters=filters,
            limit=self.settings.top_k_lexical,
        )
        vector_results = []
        if self.embedding_client is None:
            notes.append("vector:disabled")
        else:
            try:
                vectors = self.embedding_client.embed_texts([search_text])
            except EmbeddingClientError as exc:
                notes.append(f"vector:failed:{exc}")
            else:
                if vectors:
                    vector_results = self.repository.search_chunks_vector(
                        query_embedding=vectors[0],
                        filters=filters,
                        limit=self.settings.top_k_vector,
                    )
                    notes.append("vector:ok")
                else:
                    notes.append("vector:empty")
        candidates = merge_search_results(
            vector_results=vector_results,
            lexical_results=lexical_results,
        )
        notes.append(f"lexical:{len(lexical_results)}")
        notes.append(f"vector:{len(vector_results)}")
        if not candidates and understanding.filters and filters == understanding.filters:
            notes.append("degrade:strict_filters_empty")
        return RetrievalAttempt(filters=filters, candidates=candidates, notes=notes)


def _format_filters(filters: dict[str, list[str]]) -> str:
    if not filters:
        return "none"
    return ",".join(f"{key}={'+'.join(values)}" for key, values in sorted(filters.items()))


def _select_diverse_chunks(
    chunks: list[RagRetrievedChunk],
    *,
    understanding: QueryUnderstanding,
    top_k: int,
) -> list[RagRetrievedChunk]:
    """Keep high-ranked chunks while covering explicit entities in multi-entity asks."""

    if top_k <= 0 or not chunks:
        return []
    entities = list(understanding.detected_entities)
    if (
        len(entities) < 2
        or understanding.intent
        not in {
            "compare_options",
            "technique_vs_method",
            "combine_techniques",
            "contraindication_check",
        }
    ):
        return chunks[:top_k]

    selected: list[RagRetrievedChunk] = []
    selected_ids: set[str] = set()
    for entity_id in entities:
        match = next(
            (
                chunk
                for chunk in chunks
                if chunk.entity_id == entity_id and chunk.chunk_id not in selected_ids
            ),
            None,
        )
        if match is None:
            continue
        selected.append(match)
        selected_ids.add(match.chunk_id)
        if len(selected) >= top_k:
            return selected

    for chunk in chunks:
        if chunk.chunk_id in selected_ids:
            continue
        selected.append(chunk)
        selected_ids.add(chunk.chunk_id)
        if len(selected) >= top_k:
            break
    return selected


__all__ = [
    "HybridRagRetriever",
    "RagRetrievalError",
    "RetrievalAttempt",
]
