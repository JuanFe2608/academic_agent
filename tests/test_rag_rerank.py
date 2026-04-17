"""Tests for deterministic RAG reranking."""

from __future__ import annotations

from rag.retrieval.query import understand_query
from rag.retrieval.rerank import merge_search_results, rerank_candidates
from repositories.rag import RagChunkSearchResult
from schemas.rag import RagRelation, StudyRecommendationQuery


def test_merge_search_results_combines_vector_and_lexical_hits() -> None:
    vector_hit = _search_result("chunk-1", semantic_score=0.8)
    lexical_hit = _search_result("chunk-1", lexical_score=0.5)

    merged = merge_search_results(
        vector_results=[vector_hit],
        lexical_results=[lexical_hit],
    )

    assert len(merged) == 1
    assert merged[0].semantic_score == 0.8
    assert merged[0].lexical_score == 0.5
    assert merged[0].retrieval_sources == ("vector", "lexical")


def test_rerank_boosts_entity_signal_activity_and_answer_ready_chunks() -> None:
    query = StudyRecommendationQuery(
        query_text="Me distraigo y procrastino, que tecnica me conviene?",
        student_signals=["distraction", "procrastination"],
        activity_type="lectura",
        top_techniques=["pomodoro"],
    )
    understanding = understand_query(query)
    pomodoro = _search_result(
        "chunk-pomodoro",
        entity_id="pomodoro",
        chunk_kind="answer_ready",
        lexical_score=0.2,
        metadata={
            "best_for_activity_types": ["lectura"],
            "best_for_signals": ["distraction", "procrastination"],
            "confidence_level": "alto",
            "evidence_level": "medio",
        },
    )
    generic = _search_result(
        "chunk-generic",
        entity_id="mnemotecnia",
        chunk_kind="definition",
        lexical_score=0.6,
        metadata={
            "not_ideal_for_activity_types": ["lectura"],
            "confidence_level": "medio",
            "evidence_level": "bajo",
        },
    )
    candidates = merge_search_results(vector_results=[], lexical_results=[generic, pomodoro])

    ranked = rerank_candidates(
        candidates=candidates,
        query=query,
        understanding=understanding,
    )

    assert ranked[0].entity_id == "pomodoro"
    assert ranked[0].metadata_score > 0
    assert ranked[0].chunk_kind_boost > 0
    assert ranked[1].contraindication_penalty > 0


def test_rerank_penalizes_explicit_contraindicated_pair() -> None:
    query = StudyRecommendationQuery(
        query_text="Puedo combinar Pomodoro con Feynman?",
    )
    understanding = understand_query(query)
    candidate = merge_search_results(
        vector_results=[],
        lexical_results=[_search_result("chunk-feynman", entity_id="feynman")],
    )
    relation = RagRelation(
        relation_id="rel-test",
        source_type="technique",
        source_id="pomodoro",
        relation_type="contraindicated_with",
        target_type="technique",
        target_id="feynman",
        evidence_text="No combinar cuando la sesion exige explicacion profunda.",
        source_document_id="technique.pomodoro",
    )

    ranked = rerank_candidates(
        candidates=candidate,
        query=query,
        understanding=understanding,
        relations=[relation],
    )

    assert ranked[0].contraindication_penalty >= 1.0
    assert "relation_block:contraindicated_with" in ranked[0].ranking_notes


def _search_result(
    chunk_id: str,
    *,
    entity_id: str = "pomodoro",
    chunk_kind: str = "answer_ready",
    semantic_score: float = 0.0,
    lexical_score: float = 0.0,
    metadata: dict[str, object] | None = None,
) -> RagChunkSearchResult:
    return RagChunkSearchResult(
        chunk_id=chunk_id,
        document_id=f"technique.{entity_id}",
        knowledge_type="technique",
        document_type="study_technique",
        entity_id=entity_id,
        section_title="Respuesta corta reusable para RAG",
        chunk_kind=chunk_kind,
        content="Contenido de prueba",
        metadata=metadata or {},
        token_estimate=20,
        semantic_score=semantic_score,
        lexical_score=lexical_score,
    )
