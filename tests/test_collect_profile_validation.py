"""Pruebas del nodo de onboarding del perfil."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from agents.support.dependencies import set_onboarding_service
from agents.support.agent import _route_collect_profile
from agents.support.nodes.collect_profile.node import collect_profile
from agents.support.nodes.persist_profile.node import persist_profile
from agents.support.onboarding.validators import validate_student_code
from agents.support.state import AgentState
from repositories.onboarding.repository import InMemoryOnboardingRepository
from services.onboarding import InMemoryEmailSender, OnboardingConfig, OnboardingService


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
    assert "que edad tienes" in update["messages"][0].content.lower()


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


def test_collect_profile_merges_multiple_onboarding_slots_and_asks_next_missing() -> None:
    state = AgentState(
        phase="profile",
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="Soy Andres Gomez, tengo 20 y voy en octavo.")],
    )

    update = collect_profile(state)

    assert update["student_profile"]["full_name"] == "Andres Gomez"
    assert update["student_profile"]["age"] == 20
    assert update["student_profile"]["semester"] == 8
    assert update["student_profile"]["student_code"] is None
    assert update["onboarding"]["current_field"] == "student_code"
    assert "codigo estudiantil" in update["messages"][0].content.lower()


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

    assert update["phase"] == "profile"
    assert update["awaiting_user_input"] is True
    assert "codigo estudiantil solo en numeros" in update["messages"][0].content.lower()


def test_collect_profile_records_slot_errors_by_field() -> None:
    state = AgentState(
        phase="profile",
        student_profile={
            "full_name": "Ana Maria Perez",
            "student_code": "67000912",
        },
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="tengo 99")],
    )

    update = collect_profile(state)

    assert update["phase"] == "profile"
    assert update["awaiting_user_input"] is True
    assert update["onboarding"]["slot_errors"]["age"] == "invalid_age"
    assert "necesito tu edad en numero" in update["messages"][0].content.lower()


def test_collect_profile_stores_email_unverified_and_continues_to_next_field() -> None:
    """El email queda sin verificar hasta que OAuth completa; el flujo pide los campos restantes."""
    state = AgentState(
        phase="profile",
        student_profile={
            "full_name": "Ana Maria Perez",
            "student_code": "67000912",
            "age": 20,
        },
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="ANA@OUTLOOK.COM")],
    )

    update = collect_profile(state)

    assert update["student_profile"]["institutional_email"] == "ana@outlook.com"
    assert update["student_profile"]["email_verified"] is False
    assert update["awaiting_user_input"] is True  # aun faltan semestre y promedio


def test_collect_profile_accepts_email_and_remaining_slots_then_routes_to_confirm() -> None:
    """Cuando todos los campos quedan llenos en un turno, el router avanza a confirm_profile."""
    state = AgentState(
        phase="profile",
        student_profile={
            "full_name": "Ana Maria Perez",
            "student_code": "67000912",
            "age": 20,
        },
        awaiting_user_input=True,
        user_message_count=0,
        messages=[
            HumanMessage(
                content=(
                    "Mi correo es ANA@OUTLOOK.COM, voy en octavo "
                    "semestre y mi promedio es 85"
                )
            )
        ],
    )

    update = collect_profile(state)
    payload = state.model_dump()
    payload.update(update)
    next_state = AgentState(**payload)

    assert update["student_profile"]["institutional_email"] == "ana@outlook.com"
    assert update["student_profile"]["email_verified"] is False
    assert update["student_profile"]["semester"] == 8
    assert update["student_profile"]["average_grade"] == 85.0
    assert update["awaiting_user_input"] is False
    assert _route_collect_profile(next_state) == "collect_profile"


def test_collect_profile_rejects_invalid_institutional_email() -> None:
    state = AgentState(
        phase="profile",
        student_profile={
            "full_name": "Ana Maria Perez",
            "student_code": "67000912",
            "age": 20,
        },
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="ana@example.com")],
    )

    update = collect_profile(state)

    assert update["phase"] == "profile"
    assert update["awaiting_user_input"] is True
    assert "ese dominio no esta permitido" in update["messages"][0].content.lower()
    assert update["student_profile"]["institutional_email"] is None


def test_collect_profile_accepts_microsoft_personal_email_and_continues_to_next_field() -> None:
    """Un correo personal de Microsoft se acepta y el flujo continua pidiendo campos restantes."""
    state = AgentState(
        phase="profile",
        student_profile={
            "full_name": "Ana Maria Perez",
            "student_code": "67000912",
            "age": 20,
        },
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="prueba@outlook.com")],
    )

    update = collect_profile(state)
    payload = state.model_dump()
    payload.update(update)
    next_state = AgentState(**payload)

    assert update["student_profile"]["institutional_email"] == "prueba@outlook.com"
    assert update["student_profile"]["email_verified"] is False
    assert update["awaiting_user_input"] is True  # aun faltan semestre y promedio


def test_collect_profile_prompts_scope_confirmation_for_wrong_prefix_code() -> None:
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

    assert update["user_status"] == "start"
    assert update["phase"] == "profile"
    assert update["awaiting_user_input"] is True
    assert "este codigo no corresponde a uno de ingenieria de sistemas" in update["messages"][0].content.lower()


def test_collect_profile_allows_retry_when_user_confirms_belonging_to_program() -> None:
    state = AgentState(
        phase="profile",
        onboarding={"pending_student_code_scope_confirmation": True},
        student_profile={"full_name": "Ana Maria Perez"},
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="si")],
    )

    update = collect_profile(state)

    assert update["phase"] == "profile"
    assert update["awaiting_user_input"] is True
    assert update["onboarding"]["pending_student_code_scope_confirmation"] is False
    assert "ahora necesito tu codigo estudiantil" in update["messages"][0].content.lower()


def test_collect_profile_sends_user_out_of_scope_when_program_is_not_supported() -> None:
    state = AgentState(
        phase="profile",
        onboarding={"pending_student_code_scope_confirmation": True},
        student_profile={"full_name": "Ana Maria Perez"},
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="no")],
    )

    update = collect_profile(state)

    assert update["user_status"] == "out_of_scope"
    assert update["phase"] == "end"
    assert "actualmente no puedo ayudarte" in update["messages"][0].content.lower()


def test_persist_profile_success_moves_to_schedule_capture() -> None:
    service = OnboardingService(
        config=OnboardingConfig(),
        repository=InMemoryOnboardingRepository(),
        email_sender=InMemoryEmailSender(),
    )
    set_onboarding_service(service)
    try:
        state = AgentState(
            phase="profile",
            onboarding={"profile_stage": "persisting"},
            student_profile={
                "full_name": "Ana Maria Perez",
                "student_code": "67000912",
                "age": 20,
                "institutional_email": "ana@ucatolica.edu.co",
                "email_verified": True,
                "academic_program": "Ingenieria de Sistemas y Computacion",
                "supported_program": True,
                "semester": 6,
                "average_grade": 85.0,
            },
        )

        update = persist_profile(state)

        assert update["phase"] == "schedules"
        assert update["awaiting_user_input"] is False
        assert update["student_profile"]["persisted_student_id"] == 1
        assert update["onboarding"]["persistence_error"] is None
    finally:
        set_onboarding_service(None)


def test_validate_student_code_only_accepts_supported_prefix_and_length() -> None:
    assert validate_student_code("67000912") is True
    assert validate_student_code("57000912") is False
    assert validate_student_code("6700912") is False
    assert validate_student_code("67A00912") is False
