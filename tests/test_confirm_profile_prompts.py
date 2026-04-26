"""Pruebas de prompts en confirmacion de perfil."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from agents.support.nodes.confirm_profile.node import confirm_profile
from agents.support.state import AgentState


def test_confirm_profile_edit_name_prompt_has_no_intro_phrase() -> None:
    state = AgentState(
        phase="profile",
        onboarding={"profile_stage": "confirming"},
        awaiting_user_input=True,
        profile_edit_target="awaiting_field",
        user_message_count=0,
        messages=[HumanMessage(content="nombre")],
        student_profile={
            "full_name": "Ana Maria Perez Lopez",
            "student_code": "67000912",
            "age": 20,
            "institutional_email": "ana@ucatolica.edu.co",
            "email_verified": True,
            "supported_program": True,
            "academic_program": "Ingenieria de Sistemas y Computacion",
            "semester": 6,
            "average_grade": 85.0,
        },
    )

    update = confirm_profile(state)
    prompt = update["messages"][0].content

    assert "Empecemos" not in prompt
    assert "como te llamas" in prompt.lower()


def test_confirm_profile_summary_includes_program() -> None:
    state = AgentState(
        phase="profile",
        onboarding={"profile_stage": "confirming"},
        student_profile={
            "full_name": "Ana Maria Perez",
            "student_code": "67000912",
            "age": 20,
            "institutional_email": "ana@outlook.com",
            "email_verified": True,
            "supported_program": True,
            "academic_program": "Ingenieria de Sistemas y Computacion",
            "semester": 6,
            "average_grade": 85.0,
        },
    )

    update = confirm_profile(state)
    prompt = update["messages"][0].content.lower()

    assert "programa" in prompt
    assert "ana maria perez" in prompt
    assert "correo" not in prompt
