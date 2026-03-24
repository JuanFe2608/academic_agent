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

    prompt = update["messages"][0].content.lower()
    assert update["phase"] == "schedules"
    assert update["awaiting_user_input"] is True
    assert "horario académico" in prompt
    assert "si usas formato normal, escribe am o pm" in prompt
    assert "asumiré que usas horario militar" in prompt


def test_request_schedules_consumes_occupation_choice_before_asking_for_academic_schedule() -> None:
    state = AgentState(
        phase="schedules",
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="1")],
    )

    update = request_schedules(state)

    assert update["phase"] == "schedules"
    assert update["student_profile"]["occupation"] == "solo_estudio"
    assert update["awaiting_user_input"] is True
    assert not update["raw_inputs"].get("horario_academico_text")
    assert update["schedule"]["capture_target"] == "academic"
    prompt = update["messages"][0].content.lower()
    assert "horario académico" in prompt


def test_request_schedules_accepts_multiline_occupation_selection_with_schedule_payload() -> None:
    state = AgentState(
        phase="schedules",
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="1\nLunes 08:00-10:00 Algebra")],
    )

    update = request_schedules(state)

    assert update["student_profile"]["occupation"] == "solo_estudio"
    assert update["awaiting_user_input"] is False
    assert update["raw_inputs"]["horario_academico_text"] == "Lunes 08:00-10:00 Algebra"
    assert "messages" not in update or not update["messages"]


def test_request_schedules_ambos_after_academic_triggers_parse_before_work_prompt() -> None:
    state = AgentState(
        phase="schedules",
        awaiting_user_input=True,
        student_profile={"occupation": "ambos"},
        user_message_count=0,
        messages=[HumanMessage(content="Lunes 08:00-10:00 Algebra")],
    )

    update = request_schedules(state)

    assert update["raw_inputs"]["horario_academico_text"].startswith("Lunes 08:00-10:00")
    assert update["awaiting_user_input"] is False
    assert "messages" not in update or not update["messages"]


def test_parse_schedules_to_events_for_ambos_prompts_work_after_academic_is_valid() -> None:
    state = AgentState(
        phase="schedules",
        student_profile={"occupation": "ambos"},
        raw_inputs={"horario_academico_text": "Lunes 08:00-10:00 Algebra"},
    )

    update = parse_node.parse_schedules_to_events(state)

    assert update["phase"] == "schedules"
    assert update["awaiting_user_input"] is True
    assert update["academic_pending_items"] == []
    prompt = update["messages"][0].content.lower()
    assert "horario laboral" in prompt
    assert "si usas formato normal, escribe am o pm" in prompt


def test_parse_schedules_to_events_prompts_to_add_more_before_moving_on() -> None:
    state = AgentState(
        phase="schedules",
        student_profile={"occupation": "ambos"},
        raw_inputs={"horario_academico_text": "Lunes 08:00-10:00 Algebra"},
        schedule={"capture_target": "academic", "capture_stage": "awaiting_input"},
    )

    update = parse_node.parse_schedules_to_events(state)

    assert update["phase"] == "schedules"
    assert update["awaiting_user_input"] is True
    assert update["schedule"]["capture_stage"] == "awaiting_more"
    prompt = update["messages"][0].content.lower()
    assert "agregar más materias" in prompt
    assert "seguimos" in prompt


def test_request_schedules_allows_closing_academic_section_and_moves_to_work() -> None:
    state = AgentState(
        phase="schedules",
        awaiting_user_input=True,
        user_message_count=0,
        student_profile={"occupation": "ambos"},
        raw_inputs={"horario_academico_text": "Lunes 08:00-10:00 Algebra"},
        schedule={"capture_target": "academic", "capture_stage": "awaiting_more"},
        messages=[HumanMessage(content="seguimos")],
    )

    update = request_schedules(state)

    assert update["phase"] == "schedules"
    assert update["awaiting_user_input"] is True
    assert update["schedule"]["capture_target"] == "work"
    prompt = update["messages"][0].content.lower()
    assert "horario laboral" in prompt


def test_request_schedules_awaiting_more_accepts_new_academic_content_with_fisica() -> None:
    state = AgentState(
        phase="schedules",
        awaiting_user_input=True,
        user_message_count=0,
        student_profile={"occupation": "solo_estudio"},
        raw_inputs={"horario_academico_text": "Lunes - Calculo - 07:00 a 09:00"},
        schedule={"capture_target": "academic", "capture_stage": "awaiting_more"},
        messages=[HumanMessage(content="Martes y jueves - Fisica - 10 a 12")],
    )

    update = request_schedules(state)

    assert update["phase"] == "schedules"
    assert update["awaiting_user_input"] is False
    assert "Martes y jueves - Fisica - 10 a 12" in update["raw_inputs"]["horario_academico_text"]
    assert "messages" not in update or not update["messages"]


def test_request_schedules_awaiting_more_accepts_new_work_content() -> None:
    state = AgentState(
        phase="schedules",
        awaiting_user_input=True,
        user_message_count=0,
        student_profile={"occupation": "ambos"},
        raw_inputs={"horario_laboral_text": "Lunes a viernes - Trabajo - 07:00 a 18:00"},
        schedule={"capture_target": "work", "capture_stage": "awaiting_more"},
        messages=[HumanMessage(content="Sabado - Trabajo - 8 am a 12 pm")],
    )

    update = request_schedules(state)

    assert update["phase"] == "schedules"
    assert update["awaiting_user_input"] is False
    assert "Sabado - Trabajo - 8 am a 12 pm" in update["raw_inputs"]["horario_laboral_text"]
    assert "messages" not in update or not update["messages"]


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


def test_parse_schedules_to_events_accepts_work_schedule_without_meridiem_as_military_time() -> None:
    state = AgentState(
        phase="schedules",
        student_profile={"occupation": "ambos"},
        raw_inputs={
            "horario_academico_text": "Lunes 18:00-21:00 Algebra",
            "horario_laboral_text": "Trabajo de lunes a viernes de 9 a 10",
        },
    )

    update = parse_node.parse_schedules_to_events(state)

    assert update["phase"] == "extras"
    assert update["awaiting_user_input"] is False
    work_blocks = [block for block in update["schedule"]["blocks"] if block.block_type == "work"]
    assert len(work_blocks) == 5
    assert all(block.start_time == "09:00" for block in work_blocks)
    assert all(block.end_time == "10:00" for block in work_blocks)


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
                "Martes y jueves de 6 a 8"
            ),
            "horario_laboral_text": "Lunes a viernes de 7 pm a 10 pm",
        },
    )

    first_update = parse_node.parse_schedules_to_events(first_state)

    assert first_update["phase"] == "schedules"
    assert first_update["awaiting_user_input"] is True
    assert len(first_update["academic_pending_items"]) == 1
    prompt = first_update["messages"][0].content.lower()
    assert "nombre de la materia" in prompt
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
        messages=[HumanMessage(content="Programacion")],
    )

    reply_update = request_schedules(reply_state)

    assert reply_update["awaiting_user_input"] is True
    assert reply_update["academic_pending_items"] == []
    assert "Programacion" in reply_update["raw_inputs"]["horario_academico_text"]

    final_state = AgentState(
        phase="schedules",
        student_profile={"occupation": "ambos"},
        raw_inputs=reply_update["raw_inputs"],
        schedule={**reply_update["schedule"], "capture_target": None, "capture_stage": "idle"},
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
        ("Programacion", "tuesday", "06:00", "08:00"),
        ("Programacion", "thursday", "06:00", "08:00"),
    }


def test_parse_schedules_to_events_accepts_university_email_schedule_with_date_ranges() -> None:
    state = AgentState(
        phase="schedules",
        raw_inputs={
            "horario_academico_text": (
                "DATA SCIENCE FUNDAMENTALS\n"
                "3.0 créditos, Grupo D-740\n"
                "LUN,MAR,MIE 06:00:00-07:00:00, LUN,MAR,MIE 06:00:00-07:00:00,\n"
                "02-02-2026- 27-05-2026\n"
                "GERENCIA DE PROYECTOS DE TI\n"
                "3.0 créditos, Grupo D-2\n"
                "MAR,VIE 07:00:00-09:00:00, MAR,VIE 07:00:00-09:00:00,\n"
                "03-02-2026- 29-05-2026\n"
                "TRABAJO DE GRADO II\n"
                "4.0 créditos, Grupo D-5\n"
                "MIE 07:00:00-11:00:00, MIE 07:00:00-11:00:00,\n"
                "04-02-2026- 27-05-2026\n"
                "Programación para dispositivos Android\n"
                "3.0 créditos, Grupo D-651\n"
                "MAR,JUE 11:00:00-13:00:00, MAR,JUE 11:00:00-13:00:00,\n"
                "03-02-2026- 28-05-2026\n"
                "PROBLEM DISCOVERY & SOLUTION DESIGN WITH ARTIFICIAL INTELLIGENCE\n"
                "3.0 créditos, Grupo D-537\n"
                "MAR 16:00:00-18:00:00, MAR 16:00:00-18:00:00,\n"
                "03-02-2026- 26-05-2026"
            )
        },
    )

    update = parse_node.parse_schedules_to_events(state)

    assert update["phase"] == "extras"
    assert update["awaiting_user_input"] is False
    assert update["academic_pending_items"] == []
    academic_blocks = [block for block in update["schedule"]["blocks"] if block.block_type == "academic"]
    assert len(academic_blocks) == 9
