"""Pruebas de prompts en confirmacion de perfil."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from agents.support.nodes.confirm_profile.node import confirm_profile
from agents.support.state import AgentState


def test_confirm_profile_edit_name_prompt_has_no_intro_phrase() -> None:
    state = AgentState(
        phase="profile_confirm",
        awaiting_user_input=True,
        profile_edit_target="awaiting_field",
        user_message_count=0,
        messages=[HumanMessage(content="nombre")],
        student_profile={
            "nombre": "Ana Maria Perez Lopez",
            "edad": 20,
            "correo": "ana@gmail.com",
            "codigo": "12345",
            "programa": "Ingenieria de Sistemas y Computacion",
            "semestre": 6,
            "promedio": 85.0,
            "ocupacion": "solo_estudio",
        },
    )

    update = confirm_profile(state)
    prompt = update["messages"][0].content

    assert "Empecemos" not in prompt
    assert "nombre completo" in prompt.lower()
