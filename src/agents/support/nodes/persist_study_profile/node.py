"""Nodo para persistir el resultado final de personalizacion academica."""

from __future__ import annotations

from agents.support.dependencies import (
    get_personalization_service,
    get_study_recommendation_service,
)
from agents.support.flows.planning.persistence_support import (
    persist_planning_snapshot_for_update,
)
from agents.support.nodes.utils import append_message
from agents.support.personalization.formatter import build_personalization_summary
from agents.support.priorities.config import is_priorities_enabled
from agents.support.scheduling.state_helpers import ensure_schedule_flow_state
from agents.support.state import AgentState
from services.planning import study_plan_state_to_update, sync_subjects_and_study_plan
from services.priorities import priorities_state_to_update, subject_items_to_update


def persist_study_profile(state: AgentState) -> dict:
    """Guarda el Radar final y deja sembrado un plan semanal inicial.

    La generación del `study_plan` se hace detrás de una capa de compatibilidad:
    si algo falla en esta fase nueva, el flujo visible del usuario sigue
    terminando igual que antes.
    """

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
        subjects_update = _build_subjects_update(state, study_profile)
        study_plan_update = _build_study_plan_update(state, study_profile, subjects_update)
        needs_priorities = is_priorities_enabled() and _needs_priorities_capture(subjects_update)
        update = {
            "study_profile": study_profile,
            "subjects": subjects_update,
            "priorities": priorities_state_to_update(
                {
                    "status": "collecting" if needs_priorities else "completed",
                    "source": "state.subjects" if subjects_update else None,
                    "last_error": None,
                }
            ),
            "study_plan": study_plan_update,
            "phase": "priorities" if needs_priorities else "end",
            "awaiting_user_input": False,
            "messages": append_message(
                messages,
                "assistant",
                _build_personalization_summary_with_rag(study_profile),
            ),
        }
        return persist_planning_snapshot_for_update(state, update)

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


def _build_study_plan_update(
    state: AgentState,
    study_profile: dict,
    subjects: list | None = None,
) -> dict[str, object]:
    """Construye el plan semanal inicial sin comprometer el flujo actual."""

    schedule_state = ensure_schedule_flow_state(state.get("schedule", {}))
    try:
        result = sync_subjects_and_study_plan(
            schedule_blocks=list(schedule_state.blocks),
            subjects=list(subjects or state.get("subjects", [])),
            study_profile=study_profile,
            constraints=state.get("constraints", {}),
            timezone=state.get("timezone", "America/Bogota"),
        )
    except Exception:
        return study_plan_state_to_update(state.get("study_plan", {}))
    return study_plan_state_to_update(result.study_plan)


def _build_subjects_update(state: AgentState, study_profile: dict) -> list:
    """Normaliza `subjects` para que planning no dependa solo del horario crudo."""

    schedule_state = ensure_schedule_flow_state(state.get("schedule", {}))
    try:
        result = sync_subjects_and_study_plan(
            schedule_blocks=list(schedule_state.blocks),
            subjects=list(state.get("subjects", [])),
            study_profile=study_profile,
            constraints=state.get("constraints", {}),
            timezone=state.get("timezone", "America/Bogota"),
        )
    except Exception:
        return list(state.get("subjects", []))
    return subject_items_to_update(result.subjects)


def _primary_technique_id(study_profile: dict) -> str | None:
    """Retorna la técnica principal actual del Radar, si existe."""

    techniques = list(study_profile.get("top_techniques") or [])
    return str(techniques[0]) if techniques else None


def _build_personalization_summary_with_rag(study_profile: dict) -> str:
    """Enriquece el cierre del Radar sin depender operacionalmente del RAG."""

    base_summary = build_personalization_summary(study_profile)
    primary_technique = _primary_technique_id(study_profile)
    if not primary_technique:
        return base_summary

    try:
        recommendation_service = get_study_recommendation_service()
        if not recommendation_service.status.ready:
            return base_summary
        result = recommendation_service.recommend_for_student(
            student_signals=list(study_profile.get("weakness_tags") or []),
            top_techniques=list(study_profile.get("top_techniques") or []),
            max_chunks=3,
        )
    except Exception:
        return base_summary

    if not result.source_chunks or not result.answer.strip():
        return base_summary

    lines = [
        base_summary,
        "",
        "Complemento pedagógico con fuentes internas:",
        _compact_rag_answer(result.answer),
    ]
    if result.cautions:
        lines.append(f"Cuidado: {_compact_rag_answer(result.cautions[0], max_chars=240)}")
    return "\n".join(lines).strip()


def _compact_rag_answer(text: str, *, max_chars: int = 520) -> str:
    """Mantiene el cierre del Radar breve para canales conversacionales."""

    cleaned = " ".join(str(text or "").split())
    if len(cleaned) <= max_chars:
        return cleaned
    cutoff = cleaned.rfind(".", 0, max_chars)
    if cutoff < int(max_chars * 0.55):
        cutoff = max_chars
    return cleaned[:cutoff].rstrip(" .,;:") + "..."


def _needs_priorities_capture(subjects: list) -> bool:
    """Indica si falta un snapshot semanal confirmado."""

    if not subjects:
        return True
    for item in subjects:
        load = (
            item.get("carga_semanal_min")
            if isinstance(item, dict)
            else getattr(item, "carga_semanal_min", None)
        )
        confirmed = (
            item.get("is_priority_confirmed")
            if isinstance(item, dict)
            else getattr(item, "is_priority_confirmed", False)
        )
        if load is None or not confirmed:
            return True
    return False
