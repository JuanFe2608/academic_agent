"""Pruebas del flujo de solicitud de horarios solo por texto."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

import agents.support.nodes.parse_schedules_to_events.node as parse_node
from agents.support.agent import _route_request_schedules
from agents.support.nodes.request_schedules.node import request_schedules
from agents.support.state import AgentState, Event, new_event_id


def test_route_request_schedules_requires_academic_first_for_ambos() -> None:
    state = AgentState(
        phase="schedules",
        student_profile={"occupation": "ambos"},
        raw_inputs={
            "horario_laboral_text": "L-V 07:00-16:00",
        },
    )

    assert _route_request_schedules(state) == "request_schedules"


def test_route_request_schedules_requires_work_type_after_academic_for_ambos() -> None:
    state = AgentState(
        phase="schedules",
        student_profile={"occupation": "ambos"},
        raw_inputs={"horario_academico_text": "Lunes 08:00-10:00 Algebra"},
    )

    assert _route_request_schedules(state) == "request_schedules"


def test_route_request_schedules_when_all_text_ready_goes_parse() -> None:
    state = AgentState(
        phase="schedules",
        student_profile={"occupation": "ambos"},
        raw_inputs={
            "horario_academico_text": "Lunes 08:00-10:00 Algebra",
            "horario_laboral_text": "L-V 07:00-16:00",
        },
    )

    assert _route_request_schedules(state) == "parse_schedules_to_events"


def test_request_schedules_prompts_for_occupation_when_missing() -> None:
    state = AgentState(phase="schedules")

    update = request_schedules(state)

    assert update["phase"] == "schedules"
    assert update["awaiting_user_input"] is True
    assert "elige una opcion" in update["messages"][0].content.lower()


def test_request_schedules_ambos_prompts_academic_first() -> None:
    state = AgentState(
        phase="schedules",
        student_profile={"occupation": "ambos"},
    )

    update = request_schedules(state)

    assert update["phase"] == "schedules"
    assert update["awaiting_user_input"] is True
    assert "horario academico" in update["messages"][0].content.lower()


def test_request_schedules_ambos_after_academic_prompts_work_text() -> None:
    state = AgentState(
        phase="schedules",
        awaiting_user_input=True,
        student_profile={"occupation": "ambos"},
        user_message_count=0,
        messages=[HumanMessage(content="Lunes 08:00-10:00 Algebra")],
    )

    update = request_schedules(state)

    assert update["raw_inputs"]["horario_academico_text"].startswith("Lunes 08:00-10:00")
    assert update["awaiting_user_input"] is True
    assert "horario laboral" in update["messages"][0].content.lower()
    assert "fijo o flexible" not in update["messages"][0].content.lower()


def test_parse_schedules_to_events_rejects_academic_image_only_input() -> None:
    state = AgentState(
        phase="schedules",
        raw_inputs={"horario_academico_img": "data:image/png;base64,abc"},
    )

    update = parse_node.parse_schedules_to_events(state)

    assert update["phase"] == "schedules"
    assert update["awaiting_user_input"] is True
    assert "horario academico por escrito" in update["messages"][0].content.lower()


def test_parse_schedules_to_events_keeps_academic_when_work_fails() -> None:
    state = AgentState(
        phase="schedules",
        raw_inputs={
            "horario_academico_text": "Lunes 18:00-21:00 Algebra",
            "horario_laboral_text": "Trabajo de lunes a viernes de 9 a 10",
        },
        events=[
            Event(
                id=new_event_id(),
                dia="Viernes",
                inicio="10:00",
                fin="11:00",
                titulo="Gym",
                tipo="confirmado",
                categoria="extracurricular",
                origen="user_text",
                timezone="America/Bogota",
            )
        ],
    )

    update = parse_node.parse_schedules_to_events(state)

    assert update["phase"] == "schedules"
    assert update["awaiting_user_input"] is True
    assert any(event.categoria == "academico" for event in update["events"])
    assert any(event.categoria == "extracurricular" for event in update["events"])
    assert "horario laboral" in update["messages"][0].content.lower()
