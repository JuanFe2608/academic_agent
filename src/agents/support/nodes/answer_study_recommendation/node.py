"""Nodo para preguntas directas sobre tecnicas y metodos de estudio."""

from __future__ import annotations

from agents.support.dependencies import get_study_recommendation_service
from agents.support.nodes.utils import append_message, detect_new_input
from agents.support.state import AgentState
from schemas.rag import StudyRecommendationQuery


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
        result = get_study_recommendation_service().answer_query(
            StudyRecommendationQuery(
                query_text=last_text,
                student_signals=list(study_profile.get("weakness_tags") or []),
                top_techniques=list(study_profile.get("top_techniques") or []),
                max_chunks=4,
            )
        )
        answer = result.answer.strip()
    except Exception:
        answer = (
            "No pude consultar las fuentes internas de tecnicas de estudio en este momento. "
            "Puedes intentar de nuevo con una tecnica o metodo mas especifico."
        )

    return {
        "phase": "end",
        "user_message_count": current_count,
        "last_user_text": last_text,
        "awaiting_user_input": False,
        "messages": append_message(messages, "assistant", answer),
    }


__all__ = ["answer_study_recommendation"]
