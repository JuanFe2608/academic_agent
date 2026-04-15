"""Pruebas del reinicio al volver desde estado out_of_scope."""

from __future__ import annotations

from pathlib import Path

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
    messages = update["messages"]
    prompt = messages[0].content.lower()
    image_url = messages[1].content[0]["image_url"]["url"]
    consent = messages[2].content.lower()

    assert update["user_status"] == "start"
    assert update["phase"] == "consent"
    assert update["awaiting_user_input"] is True
    assert update["student_profile"]["full_name"] is None
    assert update["raw_inputs"]["horario_academico_text"] is None
    assert "soy lara, tu asistente académico inteligente" in prompt
    assert not image_url.startswith("data:image")
    assert Path(image_url).exists()
    assert "autorización para el tratamiento de datos personales" in consent


def test_welcome_consent_sends_welcome_image_and_consent_separately() -> None:
    state = AgentState()

    update = welcome_consent(state)
    messages = update["messages"]

    assert len(messages) == 3
    assert "Soy Lara" in messages[0].content
    assert messages[1].content[0]["type"] == "image_url"
    image_url = messages[1].content[0]["image_url"]["url"]
    assert not image_url.startswith("data:image")
    assert Path(image_url).exists()
    assert messages[2].content.startswith("AUTORIZACIÓN")
