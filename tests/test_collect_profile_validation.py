"""Pruebas para validacion estricta del perfil."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from agents.support.nodes.collect_profile.node import collect_profile
from agents.support.state import AgentState


def test_collect_profile_skips_program_and_moves_from_codigo_to_semestre() -> None:
    state = AgentState(
        phase="profile",
        student_profile={
            "nombre": "Ana Maria",
            "edad": 20,
            "correo": "ana@gmail.com",
        },
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="123456")],
    )

    update = collect_profile(state)

    assert update["student_profile"]["codigo"] == "123456"
    assert "semestre" in update["messages"][0].content.lower()
    assert "programa" not in update["messages"][0].content.lower()


def test_collect_profile_rejects_name_with_special_characters() -> None:
    state = AgentState(
        phase="profile",
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="Ana# Maria")],
    )

    update = collect_profile(state)

    assert "nombre solo puede contener letras y espacios" in update["messages"][0].content.lower()


def test_collect_profile_rejects_name_with_embedded_numbers() -> None:
    state = AgentState(
        phase="profile",
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="me llamo Ana123 Maria")],
    )

    update = collect_profile(state)

    assert "nombre solo puede contener letras y espacios" in update["messages"][0].content.lower()


def test_collect_profile_rejects_non_numeric_codigo() -> None:
    state = AgentState(
        phase="profile",
        student_profile={
            "nombre": "Ana Maria",
            "edad": 20,
            "correo": "ana@gmail.com",
        },
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="ABC123")],
    )

    update = collect_profile(state)

    assert "codigo debe ser numerico" in update["messages"][0].content.lower()
