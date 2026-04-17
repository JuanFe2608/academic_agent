"""Tests for the study recommendation business service."""

from __future__ import annotations

from agents.support.dependencies import (
    get_study_recommendation_service,
    set_study_recommendation_service,
)
from bootstrap.container import get_app_container, reset_app_container
from bootstrap.settings import RagSettings
from rag.retrieval.models import (
    GroundedContextPackage,
    QueryUnderstanding,
    RagCitation,
    RagRetrievedChunk,
)
from schemas.rag import RagRelation, StudyRecommendationQuery
from services.study_recommendations import (
    StudyRecommendationService,
    build_study_recommendation_service,
)


class _FakeRetriever:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.queries: list[StudyRecommendationQuery] = []

    def retrieve(self, query: StudyRecommendationQuery) -> GroundedContextPackage:
        self.queries.append(query)
        if self.fail:
            raise RuntimeError("forced failure")
        relations = []
        if query.intent == "contraindication_check":
            relations.append(
                RagRelation(
                    relation_id="rel-block",
                    source_type="technique",
                    source_id="pomodoro",
                    relation_type="contraindicated_with",
                    target_type="technique",
                    target_id="feynman",
                    evidence_text="rompe la explicacion profunda",
                    source_document_id="technique.pomodoro",
                )
            )
        chunk = RagRetrievedChunk(
            chunk_id="technique.pomodoro::answer",
            document_id="technique.pomodoro",
            knowledge_type="technique",
            document_type="study_technique",
            entity_id="pomodoro",
            section_title="Respuesta corta reusable para RAG",
            chunk_kind="answer_ready",
            content=(
                "## Respuesta corta reusable para RAG\n"
                "Pomodoro organiza el estudio en bloques cortos con pausas."
            ),
            metadata={
                "confidence_level": "alto",
                "evidence_level": "alto",
                "source_path": "raw/techniques/tecnica_pomodoro_rag.md",
            },
            token_estimate=24,
            final_score=3.5,
        )
        return GroundedContextPackage(
            query=query,
            understanding=QueryUnderstanding(
                intent=query.intent or "recommend_technique",
                query_text=query.query_text,
                detected_entities=list(query.top_techniques),
                detected_techniques=list(query.top_techniques),
            ),
            selected_chunks=[chunk],
            relations=relations,
            citations=[
                RagCitation(
                    document_id=chunk.document_id,
                    chunk_id=chunk.chunk_id,
                    section_title=chunk.section_title,
                    source_path=str(chunk.metadata["source_path"]),
                )
            ],
            groundedness_notes=["sources:1"],
        )


def test_explain_technique_returns_grounded_result_from_retriever() -> None:
    retriever = _FakeRetriever()
    service = StudyRecommendationService(
        settings=_settings(enabled=True),
        retriever=retriever,
    )

    result = service.explain_technique("tecnica_pomodoro")

    assert retriever.queries[0].intent == "explain_technique"
    assert retriever.queries[0].top_techniques == ["pomodoro"]
    assert "Pomodoro organiza" in result.answer
    assert result.source_chunks == ["technique.pomodoro::answer"]
    assert result.recommended_techniques == ["pomodoro"]


def test_recommend_for_session_builds_narrow_query_dto() -> None:
    retriever = _FakeRetriever()
    service = StudyRecommendationService(
        settings=_settings(enabled=True),
        retriever=retriever,
    )

    service.recommend_for_session(
        technique_id="recuperacion_activa",
        subject_name="Bases de datos",
        subject_type="teorica",
        activity_type="quiz",
        available_minutes=45,
        student_signals=["olvida_rapido"],
    )

    query = retriever.queries[0]
    assert query.intent == "session_guidance"
    assert query.top_techniques == ["active_recall"]
    assert query.subject_name == "Bases de datos"
    assert query.subject_type == "teorica"
    assert query.activity_type == "quiz"
    assert query.available_minutes == 45
    assert query.student_signals == ["rapid_forgetting"]


def test_validate_technique_combination_returns_caution_when_relation_blocks_pair() -> None:
    service = StudyRecommendationService(
        settings=_settings(enabled=True),
        retriever=_FakeRetriever(),
    )

    result = service.validate_technique_combination(["pomodoro", "feynman"])

    assert result.confidence == "baja"
    assert result.combinations == []
    assert "rel-block" in result.relations_used
    assert result.cautions[0].startswith("Evitar combinar Pomodoro con Feynman")


def test_service_returns_fallback_when_rag_is_disabled() -> None:
    service = StudyRecommendationService(
        settings=_settings(enabled=False),
        retriever=None,
        unavailable_reason="rag_disabled",
    )

    result = service.recommend_for_student(
        student_signals=["distraction"],
        top_techniques=["pomodoro"],
    )

    assert result.confidence == "baja"
    assert result.source_chunks == []
    assert "No tengo suficientes fuentes internas" in result.answer
    assert "service:rag_disabled" in result.groundedness_notes


def test_service_returns_fallback_when_retrieval_fails() -> None:
    service = StudyRecommendationService(
        settings=_settings(enabled=True),
        retriever=_FakeRetriever(fail=True),
    )

    result = service.explain_technique("pomodoro")

    assert result.confidence == "baja"
    assert "service:rag_runtime_error" in result.groundedness_notes
    assert "service_error:RuntimeError" in result.groundedness_notes


def test_build_service_returns_disabled_instance_when_rag_disabled(monkeypatch) -> None:
    monkeypatch.setenv("RAG_ENABLED", "false")

    service = build_study_recommendation_service()

    assert service.status.enabled is False
    assert service.status.ready is False
    assert service.status.reason == "rag_disabled"


def test_container_and_agent_dependency_wrappers_expose_service_override() -> None:
    reset_app_container()
    service = StudyRecommendationService(
        settings=_settings(enabled=False),
        retriever=None,
    )

    try:
        set_study_recommendation_service(service)

        assert get_study_recommendation_service() is service
        assert get_app_container().get_study_recommendation_service() is service
    finally:
        set_study_recommendation_service(None)
        reset_app_container()


def _settings(*, enabled: bool) -> RagSettings:
    return RagSettings(
        enabled=enabled,
        embedding_provider="fake",
        embedding_model="fake",
        embedding_dimensions=3,
        top_k_vector=4,
        top_k_lexical=4,
        top_k_final=3,
        min_score=0.0,
    )
