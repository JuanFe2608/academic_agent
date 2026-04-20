"""Build structured grounded answers from retrieved RAG context."""

from __future__ import annotations

from rag.retrieval.models import GroundedContextPackage
from schemas.rag import StudyRecommendationResult

from .context_package import build_grounded_prompt_context
from .llm_answer import GroundedAnswerGenerator
from .templates import render_fallback_answer, render_grounded_answer


def build_grounded_study_recommendation_result(
    package: GroundedContextPackage,
    *,
    answer_generator: GroundedAnswerGenerator | None = None,
) -> StudyRecommendationResult:
    """Convert grounded retrieval context into a structured recommendation result."""

    prompt_context = build_grounded_prompt_context(package)
    answer_notes: list[str] = []
    answer = ""
    if answer_generator is not None:
        try:
            answer = (
                answer_generator.generate(
                    package=package,
                    prompt_context=prompt_context,
                )
                or ""
            ).strip()
        except Exception as exc:  # noqa: BLE001 - synthesis fallback must be controlled
            answer_notes.append(f"answer_llm:error:{exc.__class__.__name__}")
    if answer:
        answer_notes.append(
            "answer:llm_no_context" if not package.has_sufficient_sources else "answer:llm_synthesis"
        )
    else:
        if not package.has_sufficient_sources:
            answer = render_fallback_answer(
                package.query,
                intent=package.understanding.intent,
            )
            answer_notes.append("answer:fallback")
        else:
            answer = render_grounded_answer(
                query=package.query,
                intent=package.understanding.intent,
                primary_text=prompt_context.primary_text,
                supporting_facts=prompt_context.supporting_facts,
                cautions=prompt_context.cautions,
                has_blocking_contraindication=prompt_context.has_blocking_contraindication,
            )
            answer_notes.append("answer:deterministic_template")
    return StudyRecommendationResult(
        answer=answer,
        recommended_techniques=prompt_context.recommended_techniques,
        recommended_methods=prompt_context.recommended_methods,
        cautions=prompt_context.cautions,
        combinations=prompt_context.combinations,
        source_chunks=prompt_context.source_chunks,
        relations_used=prompt_context.relations_used,
        confidence="baja" if not package.has_sufficient_sources else prompt_context.confidence,
        groundedness_notes=_unique(
            [
                *prompt_context.groundedness_notes,
                *answer_notes,
                "sources:missing" if not package.has_sufficient_sources else "sources:cited",
            ]
        ),
    )


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            unique.append(value)
    return unique


__all__ = ["build_grounded_study_recommendation_result"]
