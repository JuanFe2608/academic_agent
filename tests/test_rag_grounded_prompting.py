"""Tests for grounded RAG prompting assembly."""

from __future__ import annotations

from rag.prompting import build_grounded_study_recommendation_result
from rag.prompting.context_package import clean_chunk_text
from rag.retrieval.models import (
    GroundedContextPackage,
    QueryUnderstanding,
    RagCitation,
    RagRetrievedChunk,
)
from schemas.rag import RagRelation, StudyRecommendationQuery


def test_grounded_answer_uses_sources_and_infers_recommendation_payload() -> None:
    package = _package(
        query=StudyRecommendationQuery(
            query_text="Que es Pomodoro y cuando conviene?",
            top_techniques=["pomodoro"],
        ),
        understanding=QueryUnderstanding(
            intent="explain_technique",
            query_text="Que es Pomodoro y cuando conviene?",
            detected_entities=["pomodoro"],
            detected_techniques=["pomodoro"],
        ),
        chunks=[
            _chunk(
                chunk_id="technique.pomodoro::answer",
                entity_id="pomodoro",
                chunk_kind="answer_ready",
                content=(
                    "## Respuesta corta reusable para RAG\n"
                    "La tecnica Pomodoro sirve para estudiar en bloques cortos con pausas. "
                    "Es util cuando procrastinas o te distraes facil."
                ),
            )
        ],
        relations=[
            _relation(
                relation_id="rel-recommended",
                source_id="pomodoro",
                relation_type="recommended_with",
                target_id="active_recall",
                evidence_text="autoevaluacion",
            )
        ],
    )

    result = build_grounded_study_recommendation_result(package)

    assert "Pomodoro" in result.answer
    assert result.source_chunks == ["technique.pomodoro::answer"]
    assert result.recommended_techniques == ["pomodoro"]
    assert result.combinations == []
    assert result.relations_used == []
    assert result.confidence == "media"
    assert "sources:cited" in result.groundedness_notes


def test_grounded_answer_allows_recommended_combination_for_combination_intent() -> None:
    package = _package(
        query=StudyRecommendationQuery(
            query_text="Puedo combinar Pomodoro con recuperacion activa?",
            intent="combine_techniques",
        ),
        understanding=QueryUnderstanding(
            intent="combine_techniques",
            query_text="Puedo combinar Pomodoro con recuperacion activa?",
            detected_entities=["pomodoro", "active_recall"],
            detected_techniques=["pomodoro", "active_recall"],
        ),
        chunks=[
            _chunk(
                chunk_id="technique.pomodoro::combination",
                entity_id="pomodoro",
                chunk_kind="combination",
                content="## Combinaciones recomendadas\nPomodoro puede apoyar una sesion de recuperacion activa.",
            )
        ],
        relations=[
            _relation(
                relation_id="rel-recommended",
                source_id="pomodoro",
                relation_type="recommended_with",
                target_id="active_recall",
                evidence_text="autoevaluacion",
            )
        ],
    )

    result = build_grounded_study_recommendation_result(package)

    assert result.recommended_techniques == ["pomodoro", "active_recall"]
    assert result.combinations == [["pomodoro", "active_recall"]]
    assert result.relations_used == ["rel-recommended"]


def test_grounded_answer_does_not_expand_pair_relations_for_single_recommendation() -> None:
    package = _package(
        query=StudyRecommendationQuery(
            query_text="Necesito memorizar terminos exactos",
            intent="recommend_technique",
        ),
        understanding=QueryUnderstanding(
            intent="recommend_technique",
            query_text="Necesito memorizar terminos exactos",
            detected_entities=["mnemotecnia"],
            detected_techniques=["mnemotecnia"],
        ),
        chunks=[
            _chunk(
                chunk_id="technique.mnemotecnia::answer",
                entity_id="mnemotecnia",
                chunk_kind="answer_ready",
                content="## Respuesta corta reusable para RAG\nLa mnemotecnia ayuda con datos exactos.",
            )
        ],
        relations=[
            _relation(
                relation_id="rel-pomodoro",
                source_id="mnemotecnia",
                relation_type="recommended_with",
                target_id="pomodoro",
                evidence_text="contenedor opcional",
            )
        ],
    )

    result = build_grounded_study_recommendation_result(package)

    assert result.recommended_techniques == ["mnemotecnia"]
    assert result.combinations == []
    assert result.relations_used == []


def test_grounded_answer_keeps_signal_relations_inside_selected_entities() -> None:
    package = _package(
        query=StudyRecommendationQuery(
            query_text="Me distraigo mucho y aplazo el inicio",
            intent="recommend_technique",
            student_signals=["distraction"],
        ),
        understanding=QueryUnderstanding(
            intent="recommend_technique",
            query_text="Me distraigo mucho y aplazo el inicio",
            detected_entities=["pomodoro"],
            detected_techniques=["pomodoro"],
            detected_signals=["distraction"],
        ),
        chunks=[
            _chunk(
                chunk_id="technique.pomodoro::answer",
                entity_id="pomodoro",
                chunk_kind="answer_ready",
                content="## Respuesta corta reusable para RAG\nPomodoro ayuda a iniciar con foco.",
            )
        ],
        relations=[
            _relation(
                relation_id="rel-pomodoro-signal",
                source_id="pomodoro",
                relation_type="supports_signal",
                target_id="distraction",
                evidence_text="foco",
            ),
            _relation(
                relation_id="rel-mnemotecnia-signal",
                source_id="mnemotecnia",
                relation_type="supports_signal",
                target_id="distraction",
                evidence_text="memoria",
            ),
        ],
    )

    result = build_grounded_study_recommendation_result(package)

    assert result.recommended_techniques == ["pomodoro"]
    assert result.relations_used == ["rel-pomodoro-signal"]


def test_grounded_answer_returns_honest_fallback_without_sources() -> None:
    package = GroundedContextPackage(
        query=StudyRecommendationQuery(query_text="Como estudio esto?"),
        understanding=QueryUnderstanding(
            intent="recommend_technique",
            query_text="Como estudio esto?",
        ),
        selected_chunks=[],
        relations=[],
        citations=[],
        groundedness_notes=["fallback:no_chunks"],
    )

    result = build_grounded_study_recommendation_result(package)

    assert "No tengo suficientes fuentes internas" in result.answer
    assert result.source_chunks == []
    assert result.relations_used == []
    assert result.confidence == "baja"
    assert "answer:fallback" in result.groundedness_notes


def test_grounded_answer_blocks_explicit_contraindicated_combination() -> None:
    package = _package(
        query=StudyRecommendationQuery(
            query_text="Puedo combinar Pomodoro con Feynman?",
            intent="combine_techniques",
        ),
        understanding=QueryUnderstanding(
            intent="combine_techniques",
            query_text="Puedo combinar Pomodoro con Feynman?",
            detected_entities=["pomodoro", "feynman"],
            detected_techniques=["pomodoro", "feynman"],
        ),
        chunks=[
            _chunk(
                chunk_id="technique.pomodoro::combination",
                entity_id="pomodoro",
                chunk_kind="combination",
                content="## Combinaciones recomendadas\nPomodoro puede apoyar sesiones activas.",
            )
        ],
        relations=[
            _relation(
                relation_id="rel-block",
                source_id="pomodoro",
                relation_type="contraindicated_with",
                target_id="feynman",
                evidence_text="la combinacion rompe la explicacion profunda",
            ),
            _relation(
                relation_id="rel-recommended",
                source_id="pomodoro",
                relation_type="recommended_with",
                target_id="feynman",
                evidence_text="uso generico",
            ),
        ],
    )

    result = build_grounded_study_recommendation_result(package)

    assert result.answer.startswith("No recomiendo esa combinacion")
    assert result.combinations == []
    assert result.confidence == "baja"
    assert "rel-block" in result.relations_used
    assert result.cautions[0].startswith("Evitar combinar Pomodoro con Feynman")
    assert "combination:blocked_by_relation" in result.groundedness_notes


def test_grounded_answer_reports_low_evidence_in_structured_output() -> None:
    package = _package(
        query=StudyRecommendationQuery(
            query_text="Me recomiendas esta tecnica?",
            intent="recommend_technique",
        ),
        understanding=QueryUnderstanding(
            intent="recommend_technique",
            query_text="Me recomiendas esta tecnica?",
            detected_entities=["mnemotecnia"],
            detected_techniques=["mnemotecnia"],
        ),
        chunks=[
            _chunk(
                chunk_id="technique.mnemotecnia::answer",
                entity_id="mnemotecnia",
                chunk_kind="answer_ready",
                content="## Respuesta corta reusable para RAG\nLa mnemotecnia ayuda con datos exactos.",
                metadata={
                    "confidence_level": "bajo",
                    "evidence_level": "bajo",
                    "source_path": "raw/techniques/tecnica_mnemotecnia_rag.md",
                },
            )
        ],
    )

    result = build_grounded_study_recommendation_result(package)

    assert result.confidence == "baja"
    assert any("evidencia o confianza interna" in caution for caution in result.cautions)
    assert result.recommended_techniques == ["mnemotecnia"]


def test_clean_chunk_text_removes_markdown_heading_and_limits_text() -> None:
    text = clean_chunk_text(
        "## 24. Respuesta corta reusable para RAG\n"
        "**Pomodoro** organiza sesiones.\n"
        "- Evita sesiones largas sin pausa.",
        max_chars=48,
    )

    assert "##" not in text
    assert "**" not in text
    assert text.startswith("Pomodoro organiza")


def _package(
    *,
    query: StudyRecommendationQuery,
    understanding: QueryUnderstanding,
    chunks: list[RagRetrievedChunk],
    relations: list[RagRelation] | None = None,
) -> GroundedContextPackage:
    return GroundedContextPackage(
        query=query,
        understanding=understanding,
        selected_chunks=chunks,
        relations=relations or [],
        citations=[
            RagCitation(
                document_id=chunk.document_id,
                chunk_id=chunk.chunk_id,
                section_title=chunk.section_title,
                source_path=str(chunk.metadata.get("source_path") or ""),
            )
            for chunk in chunks
        ],
        groundedness_notes=["sources:" + str(len(chunks))],
    )


def _chunk(
    *,
    chunk_id: str,
    entity_id: str,
    chunk_kind: str,
    content: str,
    knowledge_type: str = "technique",
    metadata: dict[str, object] | None = None,
) -> RagRetrievedChunk:
    return RagRetrievedChunk(
        chunk_id=chunk_id,
        document_id=f"{knowledge_type}.{entity_id}",
        knowledge_type=knowledge_type,
        document_type=knowledge_type,
        entity_id=entity_id,
        section_title="Respuesta corta reusable para RAG",
        chunk_kind=chunk_kind,
        content=content,
        metadata=metadata
        or {
            "confidence_level": "alto",
            "evidence_level": "alto",
            "source_path": f"raw/{entity_id}.md",
        },
        token_estimate=30,
        final_score=3.2,
    )


def _relation(
    *,
    relation_id: str,
    source_id: str,
    relation_type: str,
    target_id: str,
    evidence_text: str,
) -> RagRelation:
    return RagRelation(
        relation_id=relation_id,
        source_type="technique",
        source_id=source_id,
        relation_type=relation_type,  # type: ignore[arg-type]
        target_type="technique",
        target_id=target_id,
        evidence_text=evidence_text,
        source_document_id=f"technique.{source_id}",
    )
