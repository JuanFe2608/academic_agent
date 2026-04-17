"""Tests for hybrid RAG retrieval orchestration."""

from __future__ import annotations

from bootstrap.settings import RagSettings
from rag.ingestion.pipeline import CORPUS_NAME, CORPUS_VERSION, build_rag_corpus
from rag.retrieval.hybrid import HybridRagRetriever
from repositories.rag import InMemoryRagRepository
from schemas.rag import StudyRecommendationQuery


class _FakeEmbeddingClient:
    provider = "fake"
    model = "fake-embedding"
    dimensions = 3

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            lowered = text.lower()
            if "pomodoro" in lowered:
                vectors.append([1.0, 0.0, 0.0])
            elif "feynman" in lowered:
                vectors.append([0.0, 1.0, 0.0])
            else:
                vectors.append([0.0, 0.0, 1.0])
        return vectors


def test_hybrid_retriever_returns_grounded_context_for_explicit_technique() -> None:
    repository = _repository_with_embeddings()
    retriever = HybridRagRetriever(
        repository=repository,
        embedding_client=_FakeEmbeddingClient(),
        settings=_settings(),
    )

    package = retriever.retrieve(
        StudyRecommendationQuery(
            query_text="Que es Pomodoro y cuando conviene?",
            max_chunks=3,
        )
    )

    assert package.has_sufficient_sources is True
    assert package.understanding.intent == "explain_technique"
    assert package.selected_chunks[0].entity_id == "pomodoro"
    assert package.citations[0].chunk_id == package.selected_chunks[0].chunk_id
    assert any("vector:ok" in note for note in package.groundedness_notes)


def test_hybrid_retriever_expands_relations_for_combination_query() -> None:
    repository = _repository_with_embeddings()
    retriever = HybridRagRetriever(
        repository=repository,
        embedding_client=_FakeEmbeddingClient(),
        settings=_settings(),
    )

    package = retriever.retrieve(
        StudyRecommendationQuery(
            query_text="Puedo combinar Pomodoro con recuperacion activa?",
            max_chunks=5,
        )
    )

    assert package.has_sufficient_sources is True
    assert {"pomodoro", "active_recall"} <= set(package.understanding.detected_entities)
    assert any(
        relation.relation_type in {"recommended_with", "contraindicated_with"}
        for relation in package.relations
    )


def test_hybrid_retriever_keeps_entity_diversity_for_comparison_query() -> None:
    repository = _repository_with_embeddings()
    retriever = HybridRagRetriever(
        repository=repository,
        embedding_client=_FakeEmbeddingClient(),
        settings=_settings(),
    )

    package = retriever.retrieve(
        StudyRecommendationQuery(
            query_text="Compara Pomodoro con recuperacion activa",
            intent="compare_options",
            max_chunks=5,
        )
    )

    selected_entities = {chunk.entity_id for chunk in package.selected_chunks}
    assert {"pomodoro", "active_recall"} <= selected_entities


def test_hybrid_retriever_falls_back_for_empty_query_and_context() -> None:
    retriever = HybridRagRetriever(
        repository=InMemoryRagRepository(),
        embedding_client=None,
        settings=_settings(),
    )

    package = retriever.retrieve(StudyRecommendationQuery(query_text=""))

    assert package.has_sufficient_sources is False
    assert "fallback:empty_query" in package.groundedness_notes


def _repository_with_embeddings() -> InMemoryRagRepository:
    result = build_rag_corpus()
    repository = InMemoryRagRepository()
    repository.sync_corpus_snapshot(
        corpus_name=CORPUS_NAME,
        corpus_version=CORPUS_VERSION,
        source_root="knowledge_base/study_recommendations",
        documents=result.documents,
        chunks=result.chunks,
        relations=result.relations,
        run_id="retrieval-test",
    )
    for payload in repository._chunks.values():
        entity_id = str(payload["entity_id"])
        if entity_id == "pomodoro":
            payload["embedding"] = [1.0, 0.0, 0.0]
        elif entity_id == "feynman":
            payload["embedding"] = [0.0, 1.0, 0.0]
        else:
            payload["embedding"] = [0.0, 0.0, 1.0]
    return repository


def _settings() -> RagSettings:
    return RagSettings(
        enabled=True,
        top_k_vector=6,
        top_k_lexical=6,
        top_k_final=5,
        min_score=0.0,
    )
