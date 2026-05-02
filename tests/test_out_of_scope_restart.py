"""Pruebas del reinicio al volver desde estado out_of_scope."""

from __future__ import annotations

from pathlib import Path

from langchain_core.messages import HumanMessage

from agents.support.agent import _route_entry
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

    assert _route_entry(state) == "welcome_consent"


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
    assert "aceptas el tratamiento de tus datos personales" in consent
    assert "/legal/habeas-data" in consent


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
    assert "¿Aceptas el tratamiento de tus datos personales" in messages[2].content
    assert "Consulta la política completa aquí:" in messages[2].content
    assert "/legal/habeas-data" in messages[2].content


def test_welcome_consent_inlines_welcome_image_for_debugger(monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_INLINE_PREVIEW", "true")
    state = AgentState()

    update = welcome_consent(state)

    image_url = update["messages"][1].content[0]["image_url"]["url"]
    assert image_url.startswith("data:image/")


def test_welcome_consent_sends_welcome_first_for_any_initial_user_message() -> None:
    state = AgentState(
        messages=[HumanMessage(content="quiero crear mi horario")],
        user_message_count=0,
        awaiting_user_input=False,
        welcome_sent=False,
    )

    update = welcome_consent(state)
    messages = update["messages"]

    assert update["phase"] == "consent"
    assert update["awaiting_user_input"] is True
    assert update["welcome_sent"] is True
    assert update["user_message_count"] == 1
    assert update["last_user_text"] == "quiero crear mi horario"
    assert "Soy Lara" in messages[0].content
    assert messages[1].content[0]["type"] == "image_url"
    assert "¿Aceptas el tratamiento de tus datos personales" in messages[2].content
    assert "/legal/habeas-data" in messages[2].content


def test_welcome_consent_does_not_accept_initial_yes_before_welcome() -> None:
    state = AgentState(
        messages=[HumanMessage(content="sí")],
        user_message_count=0,
        awaiting_user_input=False,
        welcome_sent=False,
    )

    update = welcome_consent(state)

    assert update["phase"] == "consent"
    assert update["awaiting_user_input"] is True
    assert "consent" not in update
    assert "Soy Lara" in update["messages"][0].content


def test_welcome_consent_accepts_consent_after_welcome_was_sent() -> None:
    state = AgentState(
        messages=[HumanMessage(content="sí")],
        user_message_count=0,
        awaiting_user_input=True,
        welcome_sent=True,
    )

    update = welcome_consent(state)

    assert update["phase"] == "profile"
    assert update["consent"]["accepted"] is True
    assert update["consent"]["policy_version"] == "habeas-data-v1"
    assert update["consent"]["policy_url"].endswith("/legal/habeas-data")
    assert update["consent"]["channel"] == "whatsapp"
    assert update["awaiting_user_input"] is False
    assert "continuemos con tu perfil" in update["messages"][0].content.lower()


def test_welcome_consent_rejects_consent_after_welcome_was_sent() -> None:
    state = AgentState(
        messages=[HumanMessage(content="no")],
        user_message_count=0,
        awaiting_user_input=True,
        welcome_sent=True,
    )

    update = welcome_consent(state)

    assert update["phase"] == "end"
    assert update["consent"]["accepted"] is False
    assert update["consent"]["policy_version"] == "habeas-data-v1"
    assert update["consent"]["policy_url"].endswith("/legal/habeas-data")
    assert update["consent"]["channel"] == "whatsapp"
    assert update["awaiting_user_input"] is False
    assert "sin consentimiento no puedo continuar" in update["messages"][0].content.lower()
