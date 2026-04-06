"""Pruebas de partición tipada y compatibilidad incremental de AgentState."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from agents.support.runtime_state_helpers import update_conversation_state
from agents.support.scheduling.state_helpers import update_scheduling_state
from agents.support.state import AgentState, make_initial_state


def test_agent_state_field_groups_cover_all_top_level_fields_once() -> None:
    grouped_fields = [
        field_name
        for field_names in AgentState.field_groups().values()
        for field_name in field_names
    ]

    assert len(grouped_fields) == len(set(grouped_fields))
    assert set(grouped_fields) == set(AgentState.model_fields)


def test_agent_state_partitions_expose_typed_domain_views() -> None:
    state = AgentState(
        phase="schedules",
        student_profile={"full_name": "Ana Perez", "occupation": "solo_estudio"},
        raw_inputs={"horario_academico_text": "Lunes 08:00-10:00 Algebra"},
        schedule={"capture_target": "academic", "capture_stage": "awaiting_input"},
        study_profile={"status": "collecting", "current_question_index": 2},
        extras_has_any=True,
    )

    partitions = state.partitions

    assert partitions.conversation.phase == "schedules"
    assert partitions.onboarding.student_profile.full_name == "Ana Perez"
    assert partitions.scheduling.raw_inputs.horario_academico_text == "Lunes 08:00-10:00 Algebra"
    assert partitions.scheduling.extras_has_any is True
    assert partitions.scheduling.schedule.capture_target == "academic"
    assert partitions.planning.study_profile.status == "collecting"
    assert partitions.planning.study_profile.current_question_index == 2
    assert partitions.integrations.calendar.authorized is False


def test_restart_payload_for_new_attempt_resets_domain_state_without_breaking_runtime() -> None:
    state = AgentState(
        phase="end",
        user_status="out_of_scope",
        timezone="America/Lima",
        student_profile={"full_name": "Ana Perez"},
        raw_inputs={"horario_academico_text": "Lunes 08:00-10:00 Algebra"},
        study_profile={"status": "completed", "top_techniques": ["pomodoro"]},
        extras_has_any=True,
        profile_edit_target="awaiting_field",
    )

    payload = state.restart_payload_for_new_attempt(
        messages=[HumanMessage(content="quiero reiniciar")],
        user_message_count=3,
        last_user_text="quiero reiniciar",
    )

    assert payload["phase"] == "consent"
    assert payload["user_status"] == "start"
    assert payload["welcome_sent"] is True
    assert payload["awaiting_user_input"] is True
    assert payload["timezone"] == "America/Lima"
    assert payload["user_message_count"] == 3
    assert payload["last_user_text"] == "quiero reiniciar"
    assert payload["profile_edit_target"] is None
    assert payload["student_profile"]["full_name"] is None
    assert payload["raw_inputs"]["horario_academico_text"] is None
    assert payload["study_profile"]["status"] == "idle"
    assert payload["messages"][0].content == "quiero reiniciar"


def test_make_initial_state_accepts_timezone_override() -> None:
    state = make_initial_state(timezone="America/Lima")

    assert state.timezone == "America/Lima"
    assert state.partitions.conversation.timezone == "America/Lima"


def test_agent_state_exposes_derivation_candidates_for_legacy_fields() -> None:
    candidates = AgentState.derivation_candidates()

    assert set(candidates) == {"events", "events_validated", "extras_has_any"}
    assert "schedule.blocks" in candidates["events"]


def test_update_conversation_state_returns_only_requested_runtime_fields() -> None:
    state = AgentState(
        phase="profile",
        awaiting_user_input=True,
        user_message_count=1,
        last_user_text="hola",
        messages=[HumanMessage(content="hola")],
    )

    update = update_conversation_state(
        state,
        phase="schedules",
        awaiting_user_input=False,
        user_message_count=2,
        last_user_text="listo",
        messages=[HumanMessage(content="nuevo turno")],
    )

    assert set(update) == {
        "phase",
        "awaiting_user_input",
        "user_message_count",
        "last_user_text",
        "messages",
    }
    assert update["phase"] == "schedules"
    assert update["awaiting_user_input"] is False
    assert update["user_message_count"] == 2
    assert update["last_user_text"] == "listo"
    assert len(update["messages"]) == 1
    assert update["messages"][0].content == "nuevo turno"


def test_update_scheduling_state_validates_and_serializes_only_changed_fields() -> None:
    state = AgentState(
        raw_inputs={"horario_academico_text": "Lunes 08:00-10:00 Algebra"},
        schedule={"capture_target": "academic", "capture_stage": "awaiting_input"},
    )

    update = update_scheduling_state(
        state,
        raw_inputs={"horario_academico_text": "Martes 10:00-12:00 Fisica"},
        schedule={"capture_target": "work", "capture_stage": "awaiting_more"},
        extras_has_any=False,
        events=[
            {
                "id": "evt-1",
                "dia": "Martes",
                "inicio": "10:00",
                "fin": "12:00",
                "titulo": "Fisica",
                "tipo": "confirmado",
                "categoria": "academico",
                "origen": "draft",
                "timezone": "America/Bogota",
            }
        ],
        extras_pending_items=[
            {
                "nombre": "Gimnasio",
                "missing_fields": ["hora_fin"],
                "raw_text": "Gimnasio martes 18:00",
            }
        ],
    )

    assert set(update) == {
        "raw_inputs",
        "schedule",
        "extras_has_any",
        "events",
        "extras_pending_items",
    }
    assert update["raw_inputs"]["horario_academico_text"] == "Martes 10:00-12:00 Fisica"
    assert update["schedule"]["capture_target"] == "work"
    assert update["schedule"]["capture_stage"] == "awaiting_more"
    assert update["extras_has_any"] is False
    assert update["events"][0].titulo == "Fisica"
    assert update["extras_pending_items"][0].nombre == "Gimnasio"
