"""Nodo para preguntas directas sobre tecnicas y metodos de estudio."""

from __future__ import annotations

from agents.support.dependencies import get_study_recommendation_service
from agents.support.nodes.utils import append_message, detect_new_input
from agents.support.state import AgentState
from schemas.rag import StudyRecommendationQuery
from services.study_recommendations import (
    AppliedStudyMethodService,
    build_applied_method_request_from_text,
    format_applied_study_method_for_user,
    is_applied_study_method_message,
)


def answer_study_recommendation(state: AgentState) -> dict:
    """Responde consultas pedagogicas puntuales usando el servicio RAG."""

    messages = state.get("messages", [])
    has_new_input, last_text, current_count = detect_new_input(
        messages,
        state.get("user_message_count", 0),
        state.get("awaiting_user_input", False),
        state.get("last_user_text"),
    )
    if not has_new_input:
        return {"phase": "end", "awaiting_user_input": False}

    study_profile = dict(state.get("study_profile", {}))
    try:
        recommendation_service = get_study_recommendation_service()
        applied_answer = _answer_applied_method_if_possible(
            text=last_text,
            study_profile=study_profile,
            recommendation_service=recommendation_service,
        )
        if applied_answer:
            answer = applied_answer
        else:
            result = recommendation_service.answer_query(
                StudyRecommendationQuery(
                    query_text=last_text,
                    student_signals=list(study_profile.get("weakness_tags") or []),
                    top_techniques=list(study_profile.get("top_techniques") or []),
                    max_chunks=4,
                )
            )
            if result.confidence == "baja":
                answer = _answer_academic_concept_with_llm(last_text) or result.answer.strip()
            else:
                answer = result.answer.strip()
    except Exception:
        answer = (
            "No pude preparar una respuesta confiable sobre esa tecnica en este momento. "
            "Puedes intentar de nuevo con una tecnica o metodo de estudio mas especifico."
        )

    # Si el nodo fue llamado durante un flujo activo (interrupción), reanudar esa fase.
    # Si vino desde "running" o sin fase, cerrar normalmente.
    current_phase = str(state.get("phase") or "end")
    return_phase = current_phase if current_phase not in {"running", "end", ""} else "end"

    return {
        "phase": return_phase,
        "user_message_count": current_count,
        "last_user_text": last_text,
        "awaiting_user_input": return_phase != "end",
        "messages": append_message(messages, "assistant", answer),
    }


def _answer_academic_concept_with_llm(text: str) -> str | None:
    """Responde una pregunta conceptual académica directamente con LLM cuando el RAG no tiene fuentes."""
    from integrations.ai._llm_impl import maybe_get_llm
    from langchain_core.messages import HumanMessage, SystemMessage

    llm = maybe_get_llm(temperature=0.3)
    if not llm:
        return None
    try:
        response = llm.bind(max_tokens=400).invoke([
            SystemMessage(content=(
                "Eres Lara, asistente académica universitaria. "
                "Explica el concepto académico de forma clara y concisa en 3 a 5 oraciones. "
                "NO resuelvas ejercicios, tareas ni evaluaciones. "
                "Si la pregunta pide resolver algo concreto, indica al estudiante que consulte a su docente."
            )),
            HumanMessage(content=str(text or "").strip()),
        ])
        content = getattr(response, "content", "") or ""
        return str(content).strip() or None
    except Exception:
        return None


def _answer_applied_method_if_possible(
    *,
    text: str,
    study_profile: dict,
    recommendation_service,
) -> str | None:
    if not is_applied_study_method_message(text):
        return None
    service = AppliedStudyMethodService(recommendation_service)
    request = build_applied_method_request_from_text(
        text,
        study_profile=study_profile,
    )
    result = service.apply_to_activity(request)
    if not result.applied:
        return None
    return format_applied_study_method_for_user(result)


__all__ = ["answer_study_recommendation"]
