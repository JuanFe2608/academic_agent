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


def test_parse_schedules_to_events_accepts_work_schedule_excluding_plural_weekends() -> None:
    state = AgentState(
        phase="schedules",
        raw_inputs={
            "horario_laboral_text": "Trabajo todos los dias menos los sabados y domingos de 7 pm a 10 pm",
        },
    )

    update = parse_node.parse_schedules_to_events(state)

    assert update["phase"] == "extras"
    assert update["awaiting_user_input"] is False
    work_blocks = [block for block in update["schedule"]["blocks"] if block.block_type == "work"]
    assert [block.day_of_week for block in work_blocks] == [
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
    ]
    assert all(block.start_time == "19:00" for block in work_blocks)
    assert all(block.end_time == "22:00" for block in work_blocks)


def test_schedule_request_flow_remembers_pending_academic_context_between_turns() -> None:
    first_state = AgentState(
        phase="schedules",
        student_profile={"occupation": "ambos"},
        raw_inputs={
            "horario_academico_text": (
                "Lunes 08:00-10:00 Algebra\n"
                "Martes y jueves Programacion de 6 a 8"
            ),
            "horario_laboral_text": "Lunes a viernes de 7 pm a 10 pm",
        },
    )

    first_update = parse_node.parse_schedules_to_events(first_state)

    assert first_update["phase"] == "schedules"
    assert first_update["awaiting_user_input"] is True
    assert len(first_update["academic_pending_items"]) == 1
    prompt = first_update["messages"][0].content.lower()
    assert "programacion" in prompt
    assert "puedes responder solo con lo que falta" in prompt
    assert any(
        block.block_type == "academic"
        and block.title == "Algebra"
        and block.day_of_week == "monday"
        for block in first_update["schedule"]["blocks"]
    )

    reply_state = AgentState(
        phase="schedules",
        awaiting_user_input=True,
        user_message_count=0,
        student_profile={"occupation": "ambos"},
        raw_inputs=first_update["raw_inputs"],
        schedule=first_update["schedule"],
        academic_pending_items=first_update["academic_pending_items"],
        work_pending_items=first_update["work_pending_items"],
        messages=[HumanMessage(content="pm")],
    )

    reply_update = request_schedules(reply_state)

    assert reply_update["awaiting_user_input"] is False
    assert reply_update["academic_pending_items"] == []
    assert "Programacion" in reply_update["raw_inputs"]["horario_academico_text"]

    final_state = AgentState(
        phase="schedules",
        student_profile={"occupation": "ambos"},
        raw_inputs=reply_update["raw_inputs"],
        schedule=reply_update["schedule"],
    )

    final_update = parse_node.parse_schedules_to_events(final_state)

    assert final_update["phase"] == "extras"
    academic_blocks = {
        (block.title, block.day_of_week, block.start_time, block.end_time)
        for block in final_update["schedule"]["blocks"]
        if block.block_type == "academic"
    }
    assert academic_blocks == {
        ("Algebra", "monday", "08:00", "10:00"),
        ("Programacion", "tuesday", "18:00", "20:00"),
        ("Programacion", "thursday", "18:00", "20:00"),
    }
