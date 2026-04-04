"""Nodo fino para sincronizar el plan semanal de estudio."""

from __future__ import annotations

from agents.support.flows.planning.persistence_support import (
    persist_planning_snapshot_for_update,
)
from agents.support.nodes.utils import append_message
from agents.support.planning.formatter import build_study_plan_summary
from agents.support.scheduling.state_helpers import ensure_schedule_flow_state
from agents.support.state import AgentState
from services.planning import study_plan_state_to_update, sync_subjects_and_study_plan
from services.priorities import subject_items_to_update


def build_study_plan(state: AgentState) -> dict:
    """Sincroniza materias y plan semanal sin cargar lógica en el nodo."""

    schedule_state = ensure_schedule_flow_state(state.get("schedule", {}))
    messages = state.get("messages", [])
    try:
        result = sync_subjects_and_study_plan(
            schedule_blocks=list(schedule_state.blocks),
            subjects=list(state.get("subjects", [])),
            study_profile=state.get("study_profile", {}),
            constraints=state.get("constraints", {}),
            timezone=state.get("timezone", "America/Bogota"),
        )
    except Exception:
        return {
            "phase": "end",
            "awaiting_user_input": False,
            "messages": append_message(
                messages,
                "assistant",
                "No pude recalcular tu plan semanal en este momento, pero dejé tu base anterior intacta.",
            ),
        }

    update = {
        "subjects": subject_items_to_update(result.subjects),
        "study_plan": study_plan_state_to_update(result.study_plan),
        "phase": "end",
        "awaiting_user_input": False,
        "messages": append_message(
            messages,
            "assistant",
            build_study_plan_summary(result.subjects, result.study_plan),
        ),
    }
    return persist_planning_snapshot_for_update(state, update)
