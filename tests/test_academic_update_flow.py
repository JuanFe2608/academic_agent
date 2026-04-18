"""Cobertura del flujo event-driven conectado al grafo."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from agents.support.agent import _route_handle_academic_update, _route_welcome
from agents.support.nodes.handle_academic_update import handle_academic_update
from agents.support.state import AgentState
from schemas.planning import SubjectItem


def test_end_phase_routes_academic_deadline_to_event_update() -> None:
    state = AgentState(
        phase="end",
        awaiting_user_input=False,
        user_message_count=0,
        subjects=[
            SubjectItem(
                nombre="Calculo",
                prioridad="media",
                dificultad=3,
                urgencia=None,
                carga_semanal_min=180,
                importance_rank_selected_by_student=1,
                computed_priority_score=0.55,
                is_priority_confirmed=True,
            )
        ],
        messages=[HumanMessage(content="Tengo parcial de calculo mañana")],
    )

    assert _route_welcome(state) == "handle_academic_update"

    update = handle_academic_update(state)
    next_state = AgentState(**{**state.model_dump(), **{k: v for k, v in update.items() if k != "messages"}})

    assert update["phase"] == "end"
    assert update["subjects"][0].urgency_type == "parcial"
    assert update["subjects"][0].urgencia == "alta"
    assert update["replan"]["trigger"] == "academic_deadline"
    assert _route_handle_academic_update(next_state) == "end"
