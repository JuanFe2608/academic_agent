"""Tests for rule-based RAG query understanding."""

from __future__ import annotations

from rag.retrieval.query import retrieval_search_text, understand_query
from schemas.rag import StudyRecommendationQuery


def test_understand_query_detects_technique_alias_and_explain_intent() -> None:
    query = StudyRecommendationQuery(query_text="Que es la tecnica Feynman?")

    understanding = understand_query(query)

    assert understanding.intent == "explain_technique"
    assert understanding.detected_techniques == ["feynman"]
    assert understanding.detected_entities == ["feynman"]
    assert "entity_ids" in understanding.filters
    assert "feynman" in understanding.filters["entity_ids"]


def test_understand_query_normalizes_active_recall_alias_and_combination_intent() -> None:
    query = StudyRecommendationQuery(
        query_text="Puedo combinar Pomodoro con recuperacion activa?",
        student_signals=["olvida_rapido"],
    )

    understanding = understand_query(query)

    assert understanding.intent == "combine_techniques"
    assert set(understanding.detected_techniques) == {"pomodoro", "active_recall"}
    assert "rapid_forgetting" in understanding.detected_signals
    assert "recommended_with" in understanding.relation_types
    assert "contraindicated_with" in understanding.relation_types


def test_understand_query_promotes_primary_technique_from_student_signal() -> None:
    query = StudyRecommendationQuery(
        query_text="Me distraigo mucho y aplazo el inicio",
        student_signals=["distraction", "procrastination"],
    )

    understanding = understand_query(query)

    assert understanding.intent == "recommend_technique"
    assert understanding.detected_techniques == ["pomodoro"]
    assert understanding.filters["entity_ids"] == ["pomodoro"]


def test_retrieval_search_text_uses_sparse_context_when_query_text_is_empty() -> None:
    query = StudyRecommendationQuery(
        query_text="",
        subject_name="Calculo",
        activity_type="resolucion de problemas",
        top_techniques=["interleaving"],
    )

    understanding = understand_query(query)
    search_text = retrieval_search_text(query, understanding)

    assert "Calculo" in search_text
    assert "resolucion de problemas" in search_text
    assert "interleaving" in search_text
