"""Nodo fino para sincronizar el plan semanal de estudio."""

from __future__ import annotations

from agents.support.dependencies import get_study_plan_enrichment_service
from agents.support.flows.planning.persistence_support import (
    persist_planning_snapshot_for_update,
)
from agents.support.nodes.utils import append_message
from agents.support.planning.formatter import build_study_plan_summary
from agents.support.scheduling.state_helpers import ensure_schedule_flow_state
from agents.support.state import AgentState
from services.planning import (
    active_academic_activities,
    ensure_study_plan_state,
    study_plan_state_to_update,
    sync_subjects_and_study_plan,
)
from services.priorities import subject_items_to_update


def build_study_plan(state: AgentState) -> dict:
    """Sincroniza materias y plan semanal sin cargar lógica en el nodo."""
    schedule_state = ensure_schedule_flow_state(state.get("schedule", {}))
    messages = state.get("messages", [])
    study_profile = dict(state.get("study_profile", {}))
    academic_activities = list(state.get("academic_activities", []))

    try:
        result = sync_subjects_and_study_plan(
            schedule_blocks=list(schedule_state.blocks),
            subjects=list(state.get("subjects", [])),
            academic_activities=academic_activities,
            study_profile=study_profile,
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

    enrichment = get_study_plan_enrichment_service()
    study_plan = enrichment.fully_enrich(
        study_plan=result.study_plan,
        subjects=result.subjects,
        academic_activities=academic_activities,
        study_profile=study_profile,
    )

    update = {
        "subjects": subject_items_to_update(result.subjects),
        "study_plan": study_plan_state_to_update(study_plan),
        "phase": "running",
        "awaiting_user_input": False,
    }
    persisted_update = persist_planning_snapshot_for_update(state, update)
    persisted_update["messages"] = append_message(
        messages,
        "assistant",
        build_study_plan_summary(
            subject_items_to_update(persisted_update.get("subjects", result.subjects)),
            ensure_study_plan_state(persisted_update.get("study_plan", study_plan)),
            academic_activities=active_academic_activities(academic_activities),
            reminders=persisted_update.get("reminders", state.get("reminders", {})),
        ),
    )
    return persisted_update
