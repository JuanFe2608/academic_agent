"""Pruebas del nodo de onboarding del perfil."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from agents.support.agent import _route_collect_profile
from agents.support.nodes.collect_profile.node import collect_profile
from agents.support.onboarding.validators import validate_student_code
from agents.support.state import AgentState


def test_collect_profile_accepts_student_code_and_prompts_age() -> None:
    state = AgentState(
        phase="profile",
        student_profile={
            "full_name": "Ana Maria Perez",
        },
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="67000912")],
    )

    update = collect_profile(state)

    assert update["student_profile"]["student_code"] == "67000912"
    assert update["student_profile"]["academic_program"] == "Ingenieria de Sistemas y Computacion"
    assert update["student_profile"]["supported_program"] is True
    assert update["user_status"] == "valid"
    assert "cuantos anos tienes" in update["messages"][0].content.lower()


def test_collect_profile_rejects_name_with_special_characters() -> None:
    state = AgentState(
        phase="profile",
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="Ana# Maria")],
    )

    update = collect_profile(state)

    assert "ese nombre no me quedo claro" in update["messages"][0].content.lower()


def test_collect_profile_rejects_name_with_embedded_numbers() -> None:
    state = AgentState(
        phase="profile",
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="me llamo Ana123 Maria")],
    )

    update = collect_profile(state)

    assert "ese nombre no me quedo claro" in update["messages"][0].content.lower()


def test_collect_profile_rejects_non_numeric_student_code() -> None:
    state = AgentState(
        phase="profile",
        student_profile={
            "full_name": "Ana Maria Perez",
        },
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="ABC123")],
    )

    update = collect_profile(state)

    assert update["user_status"] == "out_of_scope"
    assert update["phase"] == "end"
    assert "disenado unicamente para estudiantes de ingenieria de sistemas y computacion" in update["messages"][0].content.lower()


def test_collect_profile_moves_to_email_verification_after_valid_institutional_email() -> None:
    state = AgentState(
        phase="profile",
        student_profile={
            "full_name": "Ana Maria Perez",
            "student_code": "67000912",
            "age": 20,
        },
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="ANA@UCATOLICA.EDU.CO")],
    )

    update = collect_profile(state)
    payload = state.model_dump()
    payload.update(update)
    next_state = AgentState(**payload)

    assert update["student_profile"]["institutional_email"] == "ana@ucatolica.edu.co"
    assert update["student_profile"]["email_verified"] is False
    assert update["awaiting_user_input"] is False
    assert _route_collect_profile(next_state) == "send_email_verification"


def test_collect_profile_marks_wrong_prefix_code_as_out_of_scope() -> None:
    state = AgentState(
        phase="profile",
        student_profile={
            "full_name": "Ana Maria Perez"
        },
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="57000912")],
    )

    update = collect_profile(state)

    assert update["user_status"] == "out_of_scope"
    assert update["phase"] == "end"
    assert "actualmente no puedo ayudarte" in update["messages"][0].content.lower()


def test_validate_student_code_only_accepts_supported_prefix_and_length() -> None:
    assert validate_student_code("67000912") is True
    assert validate_student_code("57000912") is False
    assert validate_student_code("6700912") is False
    assert validate_student_code("67A00912") is False
