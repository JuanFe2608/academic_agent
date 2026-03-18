"""Pruebas del flujo de captura inicial de horarios."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

import agents.support.nodes.parse_schedules_to_events.node as parse_node
from agents.support.agent import _route_request_schedules
from agents.support.nodes.request_schedules.node import request_schedules
from agents.support.state import AgentState


def test_route_request_schedules_requires_academic_first_for_ambos() -> None:
    state = AgentState(
        phase="schedules",
        student_profile={"occupation": "ambos"},
        raw_inputs={"horario_laboral_text": "Lunes a viernes de 7 am a 6 pm"},
    )

    assert _route_request_schedules(state) == "request_schedules"


def test_route_request_schedules_when_all_text_ready_goes_parse() -> None:
    state = AgentState(
        phase="schedules",
        student_profile={"occupation": "ambos"},
        raw_inputs={
            "horario_academico_text": "Lunes 08:00-10:00 Algebra",
            "horario_laboral_text": "Lunes a viernes de 7 am a 6 pm",
        },
    )

    assert _route_request_schedules(state) == "parse_schedules_to_events"


def test_request_schedules_prompts_for_three_options_when_missing() -> None:
    update = request_schedules(AgentState(phase="schedules"))

    prompt = update["messages"][0].content.lower()
    assert update["phase"] == "schedules"
    assert update["awaiting_user_input"] is True
    assert "solo estudio" in prompt
    assert "estudio y trabajo" in prompt
    assert "ninguna de las anteriores" in prompt


def test_request_schedules_ambos_prompts_academic_first() -> None:
    update = request_schedules(
        AgentState(phase="schedules", student_profile={"occupation": "ambos"})
    )

    assert update["phase"] == "schedules"
    assert update["awaiting_user_input"] is True
    assert "horario académico" in update["messages"][0].content.lower()


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


def test_request_schedules_option_three_closes_with_specialized_message() -> None:
    state = AgentState(
        phase="schedules",
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="3")],
    )

    update = request_schedules(state)

    assert update["phase"] == "end"
    assert "soy un agente especializado" in update["messages"][0].content.lower()


def test_parse_schedules_to_events_rejects_academic_image_only_input() -> None:
    state = AgentState(
        phase="schedules",
        raw_inputs={"horario_academico_img": "data:image/png;base64,abc"},
    )

    update = parse_node.parse_schedules_to_events(state)

    assert update["phase"] == "schedules"
    assert update["awaiting_user_input"] is True
    assert "horario académico por escrito" in update["messages"][0].content.lower()


def test_parse_schedules_to_events_keeps_academic_when_work_needs_clarification() -> None:
    state = AgentState(
        phase="schedules",
        student_profile={"occupation": "ambos"},
        raw_inputs={
            "horario_academico_text": "Lunes 18:00-21:00 Algebra",
            "horario_laboral_text": "Trabajo de lunes a viernes de 9 a 10",
        },
    )

    update = parse_node.parse_schedules_to_events(state)

    assert update["phase"] == "schedules"
    assert update["awaiting_user_input"] is True
    assert any(block.block_type == "academic" for block in update["schedule"]["blocks"])
    assert "am o pm" in update["messages"][0].content.lower()
