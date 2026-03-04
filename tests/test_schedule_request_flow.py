"""Pruebas del flujo de solicitud de horarios solo por texto."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

import agents.support.nodes.parse_schedules_to_events.node as parse_node
from agents.support.agent import _route_request_schedules
from agents.support.nodes.request_schedules.node import request_schedules
from agents.support.state import AgentState


def test_route_request_schedules_requires_academic_first_for_ambos() -> None:
    state = AgentState(
        phase="schedules",
        student_profile={"ocupacion": "ambos"},
        raw_inputs={
            "horario_laboral_tipo": "fijo",
            "horario_laboral_text": "L-V 07:00-16:00",
        },
    )

    assert _route_request_schedules(state) == "request_schedules"


def test_route_request_schedules_requires_work_type_after_academic_for_ambos() -> None:
    state = AgentState(
        phase="schedules",
        student_profile={"ocupacion": "ambos"},
        raw_inputs={"horario_academico_text": "Lunes 08:00-10:00 Algebra"},
    )

    assert _route_request_schedules(state) == "request_schedules"


def test_route_request_schedules_when_all_text_ready_goes_parse() -> None:
    state = AgentState(
        phase="schedules",
        student_profile={"ocupacion": "ambos"},
        raw_inputs={
            "horario_academico_text": "Lunes 08:00-10:00 Algebra",
            "horario_laboral_tipo": "fijo",
            "horario_laboral_text": "L-V 07:00-16:00",
        },
    )

    assert _route_request_schedules(state) == "parse_schedules_to_events"


def test_request_schedules_ambos_prompts_academic_first() -> None:
    state = AgentState(
        phase="schedules",
        student_profile={"ocupacion": "ambos"},
    )

    update = request_schedules(state)

    assert update["phase"] == "schedules"
    assert update["awaiting_user_input"] is True
    assert "horario academico" in update["messages"][0].content.lower()


def test_request_schedules_ambos_after_academic_prompts_work_type() -> None:
    state = AgentState(
        phase="schedules",
        awaiting_user_input=True,
        student_profile={"ocupacion": "ambos"},
        user_message_count=0,
        messages=[HumanMessage(content="Lunes 08:00-10:00 Algebra")],
    )

    update = request_schedules(state)

    assert update["raw_inputs"]["horario_academico_text"].startswith("Lunes 08:00-10:00")
    assert update["awaiting_user_input"] is True
    assert "fijo o flexible" in update["messages"][0].content.lower()


def test_parse_schedules_to_events_rejects_academic_image_only_input() -> None:
    state = AgentState(
        phase="schedules",
        raw_inputs={"horario_academico_img": "data:image/png;base64,abc"},
    )

    update = parse_node.parse_schedules_to_events(state)

    assert update["phase"] == "schedules"
    assert update["awaiting_user_input"] is True
    assert "solo acepto horario academico en texto" in update["messages"][0].content.lower()
