"""Nodo fino para captura conversacional de prioridades académicas."""

from __future__ import annotations

from agents.support.flows.planning.persistence_support import (
    persist_planning_snapshot_for_update,
)
from agents.support.flows.priorities.priority_capture_service import (
    handle_priorities_turn,
)
from agents.support.nodes.build_study_plan.node import build_study_plan as _build_study_plan
from agents.support.nodes.utils import append_message
from agents.support.priorities.config import is_post_radar_flow_enabled
from agents.support.state import AgentState
from services.planning import coerce_academic_activities


_NO_ACTIVITIES_REDIRECT = (
    "Para organizar tus prioridades necesito saber qué tienes pendiente esta semana. 📋\n\n"
    "¿Tienes algún parcial, tarea, quiz o entrega próxima? Puedes decirme algo como:\n"
    "- \"Tengo parcial de Cálculo el viernes\"\n"
    "- \"Debo entregar la tarea de Programación el lunes\"\n"
    "- \"Quiz de Física esta semana\"\n\n"
    "En cuanto registres la primera actividad, te ayudo a organizar tus prioridades."
)


def collect_priorities(state: AgentState) -> dict:
    """Lee estado, delega al servicio y devuelve el update final."""

    # Guard: priorizar tiene sentido solo cuando hay actividades pendientes con fechas reales.
    # Sin actividades, el agente no tiene nada concreto con qué comparar urgencias.
    activities = coerce_academic_activities(list(state.get("academic_activities", [])))
    has_pending = any(a.status == "pending" for a in activities)
    if not has_pending:
        messages = state.get("messages", [])
        return {
            "phase": "running",
            "awaiting_user_input": True,
            "messages": append_message(messages, "assistant", _NO_ACTIVITIES_REDIRECT),
        }

    update = handle_priorities_turn(state)
    priorities_state = dict(update.get("priorities") or state.get("priorities", {}))
    status = priorities_state.get("status")

    if status == "completed" and is_post_radar_flow_enabled():
        # Inyectar avatar de prioridades antes de crear el estado intermedio
        # para que el mensaje de confirmación ya tenga el avatar cuando
        # build_study_plan lea el historial.
        priority_final = dict(update)
        intermediate = state.model_copy(
            update={k: v for k, v in priority_final.items() if k in state.model_fields}
        )
        plan_result = _build_study_plan(intermediate)
        return {**priority_final, **plan_result}

    if status in {"completed", "skipped"}:
        return persist_planning_snapshot_for_update(state, update)

    return update
