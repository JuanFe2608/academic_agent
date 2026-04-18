"""Nodo para persistir el resultado final de personalizacion academica."""

from __future__ import annotations

from agents.support.dependencies import (
    get_personalization_service,
    get_study_recommendation_service,
)
from agents.support.nodes.utils import append_message
from agents.support.personalization.formatter import build_personalization_summary
from agents.support.state import AgentState


def persist_study_profile(state: AgentState) -> dict:
    """Guarda el Radar final y cierra el flujo de personalizacion."""

    messages = state.get("messages", [])
    profile = dict(state.get("student_profile", {}))
    schedule_state = dict(state.get("schedule", {}))
    study_profile = dict(state.get("study_profile", {}))

    result = get_personalization_service().persist_study_profile(
        student_id=profile.get("persisted_student_id"),
        schedule_profile_id=schedule_state.get("persisted_profile_id"),
        study_profile=study_profile,
    )

    if result.persisted:
        study_profile["persisted_profile_id"] = result.personalization_profile_id
        study_profile["persistence_error"] = None
        return {
            "study_profile": study_profile,
            "phase": "end",
            "awaiting_user_input": False,
            "messages": append_message(
                messages,
                "assistant",
                _build_personalization_summary_with_rag(study_profile),
            ),
        }

    study_profile["persistence_error"] = result.error_code
    if result.error_code == "personalization_permission_denied":
        message = (
            "No pude guardar tu Radar de estudio porque el usuario actual de la base de datos "
            "no tiene permisos sobre las tablas del modulo de personalizacion.\n"
            f"Detalle tecnico: {result.detail or 'desconocido'}"
        )
    else:
        message = (
            "No pude guardar tu Radar de estudio en la base de datos.\n"
            f"Detalle tecnico: {result.detail or result.error_code or 'desconocido'}"
        )
    return {
        "study_profile": study_profile,
        "phase": "end",
        "awaiting_user_input": False,
        "messages": append_message(
            messages,
            "assistant",
            message,
        ),
    }


def _primary_technique_id(study_profile: dict) -> str | None:
    """Retorna la técnica principal actual del Radar, si existe."""

    techniques = list(study_profile.get("top_techniques") or [])
    return str(techniques[0]) if techniques else None


def _build_personalization_summary_with_rag(study_profile: dict) -> str:
    """Enriquece el cierre del Radar sin exponer detalles internos del RAG."""

    primary_technique = _primary_technique_id(study_profile)
    if not primary_technique:
        return build_personalization_summary(study_profile)

    try:
        recommendation_service = get_study_recommendation_service()
        if not recommendation_service.status.ready:
            return build_personalization_summary(study_profile)
        result = recommendation_service.recommend_for_student(
            student_signals=list(study_profile.get("weakness_tags") or []),
            top_techniques=list(study_profile.get("top_techniques") or []),
            max_chunks=3,
        )
    except Exception:
        return build_personalization_summary(study_profile)

    if not result.source_chunks or not result.answer.strip():
        return build_personalization_summary(study_profile)

    return build_personalization_summary(
        study_profile,
        pedagogical_guidance=_compact_rag_answer(result.answer),
    )


def _compact_rag_answer(text: str, *, max_chars: int = 520) -> str:
    """Mantiene el cierre del Radar breve sin cortar frases a medias."""

    cleaned = " ".join(str(text or "").split())
    if len(cleaned) <= max_chars:
        return cleaned
    cutoff = cleaned.rfind(".", 0, max_chars)
    if cutoff >= int(max_chars * 0.55):
        return cleaned[: cutoff + 1].strip()
    return cleaned
