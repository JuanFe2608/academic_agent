"""Pruebas del reinicio al volver desde estado out_of_scope."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from agents.support.agent import _route_welcome
from agents.support.nodes.welcome_consent.node import welcome_consent
from agents.support.state import AgentState


def test_out_of_scope_message_routes_back_to_welcome_on_new_input() -> None:
    state = AgentState(
        phase="end",
        user_status="out_of_scope",
        awaiting_user_input=False,
        user_message_count=0,
        messages=[HumanMessage(content="hola")],
    )

    assert _route_welcome(state) == "welcome_consent"


def test_welcome_consent_resets_state_after_out_of_scope() -> None:
    state = AgentState(
        phase="end",
        user_status="out_of_scope",
        awaiting_user_input=False,
        user_message_count=0,
        messages=[HumanMessage(content="quiero intentar de nuevo")],
        student_profile={"full_name": "Ana Maria Perez"},
        raw_inputs={"horario_academico_text": "lunes 6-8"},
    )

    update = welcome_consent(state)
    prompt = update["messages"][0].content.lower()

    assert update["user_status"] == "start"
    assert update["phase"] == "consent"
    assert update["awaiting_user_input"] is True
    assert update["student_profile"]["full_name"] is None
    assert update["raw_inputs"]["horario_academico_text"] is None
    assert "soy tu asistente académico inteligente" in prompt
