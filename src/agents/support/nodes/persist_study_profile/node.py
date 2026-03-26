"""Nodo para persistir el resultado final de personalizacion academica."""

from __future__ import annotations

from agents.support.nodes.utils import append_message
from agents.support.personalization import build_personalization_summary
from agents.support.state import AgentState
from agents.support.tools.db import get_personalization_service


def persist_study_profile(state: AgentState) -> dict:
    """Guarda el resultado estructurado del cuestionario."""

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
                build_personalization_summary(study_profile),
            ),
        }

    study_profile["persistence_error"] = result.error_code
    if result.error_code == "personalization_permission_denied":
        message = (
            "No pude guardar la caracterizacion academica porque el usuario actual de la base de datos "
            "no tiene permisos sobre las tablas del modulo de personalizacion.\n"
            f"Detalle tecnico: {result.detail or 'desconocido'}"
        )
    else:
        message = (
            "No pude guardar la caracterizacion academica en la base de datos.\n"
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
