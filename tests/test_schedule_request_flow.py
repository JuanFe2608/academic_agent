"""Pruebas del flujo de captura inicial de horarios."""

from __future__ import annotations

from pathlib import Path

from langchain_core.messages import HumanMessage

import agents.support.nodes.parse_schedules_to_events.node as parse_node
from agents.support.agent import _route_collect_schedule
from agents.support.flows.scheduling.section_confirmation_service import (
    _build_section_confirmation_prompt,
)
from agents.support.nodes.request_schedules.node import request_schedules
from agents.support.state import AgentState


def _message_text(update: dict, idx: int = 0) -> str:
    content = update["messages"][idx].content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                return str(block.get("text", ""))
    return ""


def _message_image_url(update: dict, idx: int = 0) -> str:
    content = update["messages"][idx].content
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "image_url":
                image_url = block.get("image_url")
                if isinstance(image_url, dict):
                    return str(image_url.get("url") or "")
    return ""


def test_route_collect_schedule_requires_academic_first_for_ambos() -> None:
    state = AgentState(
        phase="schedules",
        student_profile={"occupation": "ambos"},
        raw_inputs={"horario_laboral_text": "Lunes a viernes de 7 am a 6 pm"},
    )

    assert _route_collect_schedule(state) == "collect_schedule"


def test_route_collect_schedule_continues_when_all_text_ready() -> None:
    state = AgentState(
        phase="schedules",
        student_profile={"occupation": "ambos"},
        raw_inputs={
            "horario_academico_text": "Lunes 08:00-10:00 Algebra",
            "horario_laboral_text": "Lunes a viernes de 7 am a 6 pm",
        },
    )

    assert _route_collect_schedule(state) == "collect_schedule"


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
    assert "escribe el número" in prompt


def test_section_confirmation_prompt_places_option_hint_under_question_for_all_types() -> None:
    blocks = [
        {
            "block_type": "academic",
            "title": "Algebra",
            "day_of_week": "monday",
            "start_time": "08:00",
            "end_time": "10:00",
            "source_text": "Lunes Algebra 08:00-10:00",
        },
        {
            "block_type": "work",
            "title": "Trabajo",
            "day_of_week": "tuesday",
            "start_time": "09:00",
            "end_time": "17:00",
            "source_text": "Martes Trabajo 09:00-17:00",
        },
        {
            "block_type": "extracurricular",
            "title": "Gimnasio",
            "day_of_week": "wednesday",
            "start_time": "18:00",
            "end_time": "19:00",
            "source_text": "Miércoles Gimnasio 18:00-19:00",
        },
    ]

    for target in ("academic", "work", "extracurricular"):
        prompt = _build_section_confirmation_prompt(blocks, target)
        lines = prompt.splitlines()
        question_index = lines.index("¿Está bien así?")
        hint_index = lines.index("(Escribe el número de la opción que quieres elegir)")

        assert hint_index == question_index + 1
        assert lines[hint_index + 1] == "1. Sí, está correcto"
        assert lines[hint_index + 2] == "2. No, quiero cambiar algo"
        assert "(Escribe el número de la opción que quieres elegir)" not in lines[
            :question_index
        ]


def test_parse_schedules_to_events_registers_pending_fixed_schedule_interaction() -> None:
    state = AgentState(
        phase="schedules",
        student_profile={"occupation": "solo_estudio"},
        raw_inputs={"horario_academico_text": "Miercoles Matematicas"},
        schedule={"capture_target": "academic", "capture_stage": "awaiting_input"},
    )

    update = parse_node.parse_schedules_to_events(state)

    assert update["phase"] == "schedules"
    assert update["awaiting_user_input"] is True
    assert update["academic_pending_items"]
    assert update["interaction"]["pending_entity_type"] == "fixed_schedule_item"
    assert update["interaction"]["pending_action"] == "complete_fixed_schedule_item"
    assert update["interaction"]["pending_entity_payload"]["schedule_type"] == "academic"
    assert update["interaction"]["missing_fields_json"] == ["time_range"]
    assert "responder solo con el rango horario" in update["messages"][0].content.lower()


def test_parse_schedules_to_events_missing_day_prompt_asks_only_for_day() -> None:
    state = AgentState(
        phase="schedules",
        student_profile={"occupation": "solo_estudio"},
        raw_inputs={"horario_academico_text": "Matematicas 9 a 11"},
        schedule={"capture_target": "academic", "capture_stage": "awaiting_input"},
    )

    update = parse_node.parse_schedules_to_events(state)

    assert update["interaction"]["missing_fields_json"] == ["day"]
    assert "responder solo con el día" in update["messages"][0].content.lower()


def test_request_schedules_resolves_fixed_schedule_pending_with_short_reply_and_clears_interaction() -> None:
    pending_state = AgentState(
        phase="schedules",
        student_profile={"occupation": "solo_estudio"},
        raw_inputs={"horario_academico_text": "Miercoles Matematicas"},
        schedule={"capture_target": "academic", "capture_stage": "awaiting_input"},
    )
    pending_update = parse_node.parse_schedules_to_events(pending_state)
    state_payload = pending_state.model_dump(mode="python")
    state_payload.update(pending_update)
    state_payload["messages"] = [HumanMessage(content="9 a 11")]
    state_payload["awaiting_user_input"] = True
    state_payload["user_message_count"] = 0

    update = request_schedules(AgentState(**state_payload))

    assert update["academic_pending_items"] == []
    assert update["schedule"]["capture_stage"] == "awaiting_more"
    assert update["interaction"]["pending_entity_type"] is None
    assert update["interaction"]["missing_fields_json"] == []
    blocks = [block for block in update["schedule"]["blocks"] if block.block_type == "academic"]
    assert [(block.title, block.day_of_week, block.start_time, block.end_time) for block in blocks] == [
        ("Matematicas", "wednesday", "09:00", "11:00"),
    ]


def test_request_schedules_allows_closing_academic_section_and_moves_to_work() -> None:
    state = AgentState(
        phase="schedules",
        awaiting_user_input=True,
        user_message_count=0,
        student_profile={"occupation": "ambos"},
        raw_inputs={"horario_academico_text": "Lunes 08:00-10:00 Algebra"},
        schedule={
            "capture_target": "academic",
            "capture_stage": "awaiting_more",
            "blocks": [
                {
                    "block_type": "academic",
                    "title": "Algebra",
                    "day_of_week": "monday",
                    "start_time": "08:00",
                    "end_time": "10:00",
                    "source_text": "Lunes 08:00-10:00 Algebra",
                }
            ],
        },
        messages=[HumanMessage(content="seguimos")],
    )

    update = request_schedules(state)

    assert update["phase"] == "schedules"
    assert update["awaiting_user_input"] is True
    assert update["schedule"]["capture_target"] == "academic"
    assert update["schedule"]["review_stage"] == "section_awaiting_confirmation"
    prompt = _message_text(update).lower()
    assert "horario académico actual" in prompt
    assert "está bien así" in prompt
    assert "- algebra" in prompt
    assert "1. algebra" not in prompt
    assert "1. sí, está correcto" in prompt
    assert "2. no, quiero cambiar algo" in prompt
    assert Path(_message_image_url(update)).exists()
    assert "schedule_preview" not in update


def test_request_schedules_section_confirmation_yes_moves_to_work_prompt() -> None:
    state = AgentState(
        phase="schedules",
        awaiting_user_input=True,
        user_message_count=0,
        student_profile={"occupation": "ambos"},
        raw_inputs={"horario_academico_text": "Lunes 08:00-10:00 Algebra"},
        schedule={
            "blocks": [
                {
                    "block_type": "academic",
                    "title": "Algebra",
                    "day_of_week": "monday",
                    "start_time": "08:00",
                    "end_time": "10:00",
                    "source_text": "Lunes 08:00-10:00 Algebra",
                }
            ],
            "capture_target": "academic",
            "capture_stage": "idle",
            "review_stage": "section_awaiting_confirmation",
            "correction_target": "academic",
        },
        messages=[HumanMessage(content="1")],
    )

    update = request_schedules(state)

    assert update["phase"] == "schedules"
    assert update["awaiting_user_input"] is True
    assert update["schedule"]["capture_target"] == "work"
    assert update["schedule"]["review_stage"] == "idle"
    assert "horario laboral" in update["messages"][0].content.lower()


def test_request_schedules_section_change_prompt_includes_schedule_image() -> None:
    state = AgentState(
        phase="schedules",
        awaiting_user_input=True,
        user_message_count=0,
        student_profile={"occupation": "solo_estudio"},
        raw_inputs={"horario_academico_text": "Lunes 08:00-10:00 Algebra"},
        schedule={
            "blocks": [
                {
                    "block_type": "academic",
                    "title": "Algebra",
                    "day_of_week": "monday",
                    "start_time": "08:00",
                    "end_time": "10:00",
                    "source_text": "Lunes 08:00-10:00 Algebra",
                    "block_id": "academic-1",
                }
            ],
            "capture_target": "academic",
            "capture_stage": "idle",
            "review_stage": "section_awaiting_confirmation",
            "correction_target": "academic",
        },
        messages=[HumanMessage(content="2")],
    )

    update = request_schedules(state)

    assert update["schedule"]["review_stage"] == "section_awaiting_item_selection"
    prompt = _message_text(update).lower()
    assert "horario académico actual" in prompt
    assert "¿qué quieres hacer?" in prompt
    assert "editar una materia" in prompt
    assert "añadir" in prompt
    assert "cancelar" in prompt
    assert Path(_message_image_url(update)).exists()


def test_request_schedules_section_edit_revalidates_conflicts_after_change(monkeypatch, tmp_path) -> None:
    rendered_path = tmp_path / "schedule.png"
    rendered_path.write_bytes(b"fake image")
    monkeypatch.setattr(
        "agents.support.flows.scheduling.section_confirmation_service.build_rendered_schedule_message_content",
        lambda text, _blocks, **_kwargs: (
            [
                {"type": "text", "text": text},
                {"type": "image_url", "image_url": {"url": str(rendered_path)}},
            ],
            str(rendered_path),
        ),
    )
    state = AgentState(
        phase="schedules",
        awaiting_user_input=True,
        user_message_count=0,
        student_profile={"occupation": "ambos"},
        raw_inputs={
            "horario_academico_text": "Lunes 08:00-10:00 Algebra",
            "horario_laboral_text": "Lunes 09:00-18:00",
        },
        schedule={
            "blocks": [
                {
                    "block_type": "academic",
                    "title": "Algebra",
                    "day_of_week": "monday",
                    "start_time": "08:00",
                    "end_time": "10:00",
                    "source_text": "Lunes 08:00-10:00 Algebra",
                    "block_id": "academic-1",
                },
                {
                    "block_type": "work",
                    "title": "Trabajo",
                    "day_of_week": "monday",
                    "start_time": "09:00",
                    "end_time": "18:00",
                    "source_text": "Lunes 09:00-18:00",
                    "block_id": "work-1",
                },
            ],
            "capture_target": "academic",
            "capture_stage": "idle",
            "review_stage": "section_awaiting_field_value",
            "correction_target": "academic",
            "editing_block_id": "academic-1",
            "editing_field": "time_range",
        },
        messages=[HumanMessage(content="9:30 am a 10:30 am")],
    )

    update = request_schedules(state)

    assert update["phase"] == "schedules"
    assert update["schedule"]["review_stage"] == "section_awaiting_item_confirmation"
    assert len(update["schedule"]["conflicts"]) == 1
    text = update["messages"][0].content[0]["text"].lower()
    assert "genera un cruce" in text
    assert "9:30" in text
    rendered_image = update["messages"][0].content[1]["image_url"]["url"]
    assert not rendered_image.startswith("data:image")
    assert Path(rendered_image).exists()


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
    assert "Martes 10:00-12:00 Fisica" in update["raw_inputs"]["horario_academico_text"]
    assert "Jueves 10:00-12:00 Fisica" in update["raw_inputs"]["horario_academico_text"]
    assert "messages" not in update or not update["messages"]


def test_request_schedules_awaiting_more_strips_option_text_from_inline_academic_payload() -> None:
    state = AgentState(
        phase="schedules",
        awaiting_user_input=True,
        user_message_count=0,
        student_profile={"occupation": "solo_estudio"},
        raw_inputs={"horario_academico_text": "Martes - Algebra - 08:00 a 10:00"},
        schedule={"capture_target": "academic", "capture_stage": "awaiting_more"},
        messages=[
            HumanMessage(
                content="Sí, quiero agregar más materias\nLunes - Calulo - 7am a 9 am"
            )
        ],
    )

    update = request_schedules(state)

    assert update["awaiting_user_input"] is False
    raw_text = update["raw_inputs"]["horario_academico_text"]
    assert "quiero agregar más materias" not in raw_text.lower()
    assert "Lunes 07:00-09:00 Calulo" in raw_text


def test_request_schedules_numeric_more_then_new_subject_keeps_original_and_adds_new_one() -> None:
    initial_raw_text = "\n".join(
        [
            "Problem Discovery & Solution Design With Artificial Intelligence",
            "Martes de 4:00 p.m. a 6:00 p.m.",
        ]
    )
    first_state = AgentState(
        phase="schedules",
        awaiting_user_input=True,
        user_message_count=0,
        student_profile={"occupation": "solo_estudio"},
        raw_inputs={"horario_academico_text": initial_raw_text},
        schedule={"capture_target": "academic", "capture_stage": "awaiting_more"},
        messages=[HumanMessage(content="1")],
    )

    first_update = request_schedules(first_state)

    assert first_update["awaiting_user_input"] is True
    assert first_update["schedule"]["capture_stage"] == "awaiting_input"

    second_state = AgentState(
        phase=first_update.get("phase", "schedules"),
        awaiting_user_input=True,
        user_message_count=1,
        student_profile={"occupation": "solo_estudio"},
        raw_inputs=first_update["raw_inputs"],
        schedule=first_update["schedule"],
        messages=[HumanMessage(content="Lunes - Cálculo - 07:00 a 09:00")],
    )

    second_update = request_schedules(second_state)
    parse_update = parse_node.parse_schedules_to_events(
        AgentState(
            phase=second_update.get("phase", "schedules"),
            student_profile={"occupation": "solo_estudio"},
            raw_inputs=second_update["raw_inputs"],
            schedule=second_update["schedule"],
        )
    )

    academic_blocks = [
        block
        for block in parse_update["schedule"]["blocks"]
        if block.block_type == "academic"
    ]
    assert {
        (block.title, block.day_of_week, block.start_time, block.end_time)
        for block in academic_blocks
    } == {
        (
            "Problem Discovery & Solution Design With Artificial Intelligence",
            "tuesday",
            "16:00",
            "18:00",
        ),
        ("Cálculo", "monday", "07:00", "09:00"),
    }


def test_request_schedules_more_subject_parses_new_payload_without_inheriting_previous_title() -> None:
    state = AgentState(
        phase="schedules",
        awaiting_user_input=True,
        user_message_count=0,
        student_profile={"occupation": "solo_estudio"},
        raw_inputs={"horario_academico_text": "Lunes 06:00-07:00 Data Science Fundamentals"},
        schedule={
            "capture_target": "academic",
            "capture_stage": "awaiting_more",
            "blocks": [
                {
                    "block_type": "academic",
                    "title": "Data Science Fundamentals",
                    "day_of_week": "monday",
                    "start_time": "06:00",
                    "end_time": "07:00",
                    "source_text": "Lunes 06:00-07:00 Data Science Fundamentals",
                }
            ],
        },
        messages=[HumanMessage(content="Lunes Android de 2 pm a 6 pm")],
    )

    update = request_schedules(state)

    assert update["awaiting_user_input"] is False
    raw_text = update["raw_inputs"]["horario_academico_text"]
    assert "Lunes 14:00-18:00 Android" in raw_text
    assert "Lunes 14:00-18:00 Data Science Fundamentals" not in raw_text

    parse_update = parse_node.parse_schedules_to_events(
        AgentState(
            phase=update.get("phase", "schedules"),
            student_profile={"occupation": "solo_estudio"},
            raw_inputs=update["raw_inputs"],
            schedule=update["schedule"],
        )
    )
    academic_blocks = {
        (block.title, block.day_of_week, block.start_time, block.end_time)
        for block in parse_update["schedule"]["blocks"]
        if block.block_type == "academic"
    }
    assert ("Android", "monday", "14:00", "18:00") in academic_blocks
    assert ("Data Science Fundamentals", "monday", "14:00", "18:00") not in academic_blocks


def test_request_schedules_more_subject_with_missing_day_asks_only_for_missing_data() -> None:
    state = AgentState(
        phase="schedules",
        awaiting_user_input=True,
        user_message_count=0,
        student_profile={"occupation": "solo_estudio"},
        raw_inputs={"horario_academico_text": "Lunes 06:00-07:00 Data Science Fundamentals"},
        schedule={
            "capture_target": "academic",
            "capture_stage": "awaiting_more",
            "blocks": [
                {
                    "block_type": "academic",
                    "title": "Data Science Fundamentals",
                    "day_of_week": "monday",
                    "start_time": "06:00",
                    "end_time": "07:00",
                    "source_text": "Lunes 06:00-07:00 Data Science Fundamentals",
                }
            ],
        },
        messages=[HumanMessage(content="Android de 2 pm a 6 pm")],
    )

    update = request_schedules(state)

    assert update["awaiting_user_input"] is True
    assert update["schedule"]["capture_stage"] == "awaiting_input"
    assert update["academic_pending_items"]
    assert update["interaction"]["missing_fields_json"] == ["day"]
    assert "me falta: dia o dias exactos" in update["messages"][0].content.lower()
    assert update["raw_inputs"]["horario_academico_text"] == (
        "Lunes 06:00-07:00 Data Science Fundamentals"
    )


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
    assert "Sabado 08:00-12:00" in update["raw_inputs"]["horario_laboral_text"]
    assert "messages" not in update or not update["messages"]


def test_request_schedules_field_selection_includes_delete_option() -> None:
    state = AgentState(
        phase="schedules",
        awaiting_user_input=True,
        user_message_count=0,
        student_profile={"occupation": "solo_estudio"},
        schedule={
            "blocks": [
                {
                    "block_type": "academic",
                    "title": "Algebra",
                    "day_of_week": "monday",
                    "start_time": "08:00",
                    "end_time": "10:00",
                    "source_text": "Lunes 08:00-10:00 Algebra",
                    "block_id": "academic-1",
                }
            ],
            "review_stage": "section_awaiting_item_selection",
            "correction_target": "academic",
        },
        messages=[HumanMessage(content="1")],
    )

    update = request_schedules(state)

    prompt = update["messages"][0].content.lower()
    assert "escribe el número del cambio" in prompt
    assert "3. horario" in prompt
    assert "eliminar materia" in prompt


def test_request_schedules_accepts_multi_item_selection_with_commas_and_spaces() -> None:
    state = AgentState(
        phase="schedules",
        awaiting_user_input=True,
        user_message_count=0,
        student_profile={"occupation": "solo_estudio"},
        schedule={
            "blocks": [
                {
                    "block_type": "academic",
                    "title": "Data Science Fundamentals",
                    "day_of_week": "monday",
                    "start_time": "06:00",
                    "end_time": "07:00",
                    "source_text": "Lunes 06:00-07:00 Data Science Fundamentals",
                    "block_id": "academic-1",
                },
                {
                    "block_type": "academic",
                    "title": "Data Science Fundamentals",
                    "day_of_week": "tuesday",
                    "start_time": "06:00",
                    "end_time": "07:00",
                    "source_text": "Martes 06:00-07:00 Data Science Fundamentals",
                    "block_id": "academic-2",
                },
                {
                    "block_type": "academic",
                    "title": "Data Science Fundamentals",
                    "day_of_week": "wednesday",
                    "start_time": "06:00",
                    "end_time": "07:00",
                    "source_text": "Miercoles 06:00-07:00 Data Science Fundamentals",
                    "block_id": "academic-3",
                },
            ],
            "review_stage": "section_awaiting_item_selection",
            "correction_target": "academic",
        },
        messages=[HumanMessage(content="1,2 3")],
    )

    update = request_schedules(state)

    assert update["schedule"]["review_stage"] == "section_awaiting_field_selection"
    assert update["schedule"]["editing_block_id"] == "academic-1"
    assert update["schedule"]["editing_block_ids"] == [
        "academic-1",
        "academic-2",
        "academic-3",
    ]
    prompt = update["messages"][0].content.lower()
    assert "vas a editar estos 3 registros" in prompt
    assert "6. reemplazar todos los datos" not in prompt


def test_request_schedules_multi_item_time_edit_updates_raw_inputs_and_preview(
    monkeypatch,
    tmp_path,
) -> None:
    rendered_path = tmp_path / "schedule.png"
    rendered_path.write_bytes(b"fake image")
    monkeypatch.setattr(
        "agents.support.flows.scheduling.section_confirmation_service.build_rendered_schedule_message_content",
        lambda text, _blocks, **_kwargs: (
            [
                {"type": "text", "text": text},
                {"type": "image_url", "image_url": {"url": str(rendered_path)}},
            ],
            str(rendered_path),
        ),
    )
    state = AgentState(
        phase="schedules",
        awaiting_user_input=True,
        user_message_count=0,
        student_profile={"occupation": "solo_estudio"},
        raw_inputs={
            "horario_academico_text": (
                "Lunes 06:00-07:00 Data Science Fundamentals\n"
                "Martes 06:00-07:00 Data Science Fundamentals\n"
                "Miercoles 06:00-07:00 Data Science Fundamentals\n"
                "Jueves 11:00-13:00 Android"
            )
        },
        schedule={
            "blocks": [
                {
                    "block_type": "academic",
                    "title": "Data Science Fundamentals",
                    "day_of_week": "monday",
                    "start_time": "06:00",
                    "end_time": "07:00",
                    "source_text": "Lunes 06:00-07:00 Data Science Fundamentals",
                    "block_id": "academic-1",
                },
                {
                    "block_type": "academic",
                    "title": "Data Science Fundamentals",
                    "day_of_week": "tuesday",
                    "start_time": "06:00",
                    "end_time": "07:00",
                    "source_text": "Martes 06:00-07:00 Data Science Fundamentals",
                    "block_id": "academic-2",
                },
                {
                    "block_type": "academic",
                    "title": "Data Science Fundamentals",
                    "day_of_week": "wednesday",
                    "start_time": "06:00",
                    "end_time": "07:00",
                    "source_text": "Miercoles 06:00-07:00 Data Science Fundamentals",
                    "block_id": "academic-3",
                },
                {
                    "block_type": "academic",
                    "title": "Android",
                    "day_of_week": "thursday",
                    "start_time": "11:00",
                    "end_time": "13:00",
                    "source_text": "Jueves 11:00-13:00 Android",
                    "block_id": "academic-4",
                },
            ],
            "review_stage": "section_awaiting_field_value",
            "correction_target": "academic",
            "editing_block_id": "academic-1",
            "editing_block_ids": ["academic-1", "academic-2", "academic-3"],
            "editing_field": "time_range",
        },
        messages=[HumanMessage(content="7:00 am a 8:00 am")],
    )

    update = request_schedules(state)

    updated_blocks = {block.block_id: block for block in update["schedule"]["blocks"]}
    for block_id in ("academic-1", "academic-2", "academic-3"):
        assert updated_blocks[block_id].start_time == "07:00"
        assert updated_blocks[block_id].end_time == "08:00"
    assert updated_blocks["academic-4"].start_time == "11:00"
    raw_text = update["raw_inputs"]["horario_academico_text"]
    assert "Lunes 07:00-08:00 Data Science Fundamentals" in raw_text
    assert "Martes 07:00-08:00 Data Science Fundamentals" in raw_text
    assert "Miercoles 07:00-08:00 Data Science Fundamentals" in raw_text
    text = update["messages"][0].content[0]["text"].lower()
    assert "así quedaron actualizados estos registros" in text
    assert Path(update["messages"][0].content[1]["image_url"]["url"]).exists()


def test_request_schedules_multi_work_time_edit_updates_work_raw_input(
    monkeypatch,
    tmp_path,
) -> None:
    rendered_path = tmp_path / "work-schedule.png"
    rendered_path.write_bytes(b"fake image")
    monkeypatch.setattr(
        "agents.support.flows.scheduling.section_confirmation_service.build_rendered_schedule_message_content",
        lambda text, _blocks, **_kwargs: (
            [
                {"type": "text", "text": text},
                {"type": "image_url", "image_url": {"url": str(rendered_path)}},
            ],
            str(rendered_path),
        ),
    )
    state = AgentState(
        phase="schedules",
        awaiting_user_input=True,
        user_message_count=0,
        student_profile={"occupation": "ambos"},
        raw_inputs={"horario_laboral_text": "Lunes 09:00-17:00\nMartes 09:00-17:00"},
        schedule={
            "blocks": [
                {
                    "block_type": "work",
                    "title": "Trabajo",
                    "day_of_week": "monday",
                    "start_time": "09:00",
                    "end_time": "17:00",
                    "source_text": "Lunes 09:00-17:00",
                    "block_id": "work-1",
                },
                {
                    "block_type": "work",
                    "title": "Trabajo",
                    "day_of_week": "tuesday",
                    "start_time": "09:00",
                    "end_time": "17:00",
                    "source_text": "Martes 09:00-17:00",
                    "block_id": "work-2",
                },
            ],
            "review_stage": "section_awaiting_field_value",
            "correction_target": "work",
            "editing_block_id": "work-1",
            "editing_block_ids": ["work-1", "work-2"],
            "editing_field": "time_range",
        },
        messages=[HumanMessage(content="10 am a 6 pm")],
    )

    update = request_schedules(state)

    assert update["raw_inputs"]["horario_laboral_text"] == (
        "Lunes 10:00-18:00\nMartes 10:00-18:00"
    )
    updated_blocks = {block.block_id: block for block in update["schedule"]["blocks"]}
    assert updated_blocks["work-1"].start_time == "10:00"
    assert updated_blocks["work-2"].end_time == "18:00"


def test_request_schedules_item_selection_cancel_returns_to_section_confirmation() -> None:
    state = AgentState(
        phase="schedules",
        awaiting_user_input=True,
        user_message_count=0,
        student_profile={"occupation": "solo_estudio"},
        schedule={
            "blocks": [
                {
                    "block_type": "academic",
                    "title": "Algebra",
                    "day_of_week": "monday",
                    "start_time": "08:00",
                    "end_time": "10:00",
                    "source_text": "Lunes 08:00-10:00 Algebra",
                    "block_id": "academic-1",
                }
            ],
            "review_stage": "section_awaiting_item_selection",
            "correction_target": "academic",
        },
        messages=[HumanMessage(content="cancelar")],
    )

    update = request_schedules(state)

    assert update["schedule"]["review_stage"] == "section_awaiting_confirmation"
    assert update["schedule"]["editing_block_id"] is None
    assert update["schedule"]["editing_block_ids"] == []
    prompt = _message_text(update).lower()
    assert "no hice cambios" in prompt
    assert "¿está bien así?" in prompt
    assert Path(_message_image_url(update)).exists()


def test_request_schedules_rejects_incoherent_time_range_in_shared_editor() -> None:
    state = AgentState(
        phase="schedules",
        awaiting_user_input=True,
        user_message_count=0,
        student_profile={"occupation": "solo_estudio"},
        schedule={
            "blocks": [
                {
                    "block_type": "academic",
                    "title": "Algebra",
                    "day_of_week": "monday",
                    "start_time": "08:00",
                    "end_time": "10:00",
                    "source_text": "Lunes 08:00-10:00 Algebra",
                    "block_id": "academic-1",
                }
            ],
            "review_stage": "section_awaiting_field_value",
            "correction_target": "academic",
            "editing_block_id": "academic-1",
            "editing_field": "time_range",
        },
        messages=[HumanMessage(content="10:30 am a 9:30 am")],
    )

    update = request_schedules(state)

    assert update["phase"] == "schedules"
    assert update["awaiting_user_input"] is True
    assert update["schedule"]["review_stage"] == "section_awaiting_field_value"
    assert "inicio debe quedar antes" in update["messages"][0].content.lower()


def test_request_schedules_option_three_redirects_with_friendly_message() -> None:
    state = AgentState(
        phase="schedules",
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="3")],
    )

    update = request_schedules(state)

    assert update["phase"] == "schedules"
    assert update["awaiting_user_input"] is True
    assert update["student_profile"]["occupation"] is None
    message_text = update["messages"][0].content.lower()
    assert "soy un asistente especializado" in message_text
    assert "elige una opción" in message_text


def test_parse_schedules_to_events_rejects_academic_image_only_input() -> None:
    state = AgentState(
        phase="schedules",
        raw_inputs={"horario_academico_img": "data:image/png;base64,abc"},
    )

    update = parse_node.parse_schedules_to_events(state)

    assert update["phase"] == "schedules"
    assert update["awaiting_user_input"] is True
    assert "horario académico por escrito" in update["messages"][0].content.lower()


def test_request_schedules_extracts_academic_schedule_from_student_image(monkeypatch) -> None:
    monkeypatch.setattr(
        "agents.support.flows.scheduling.schedule_capture_service.llm_extract_schedule_from_image",
        lambda image_ref, schedule_hint=None: {
            "is_schedule": True,
            "schedule_type": schedule_hint,
            "extracted_text": "Lunes 08:00-10:00 Algebra",
        },
    )
    state = AgentState(
        phase="schedules",
        awaiting_user_input=True,
        user_message_count=0,
        student_profile={"occupation": "solo_estudio"},
        schedule={"capture_target": "academic", "capture_stage": "awaiting_input"},
        messages=[
            HumanMessage(
                content=[
                    {"type": "input_image", "image_url": {"url": "data:image/png;base64,abc"}}
                ]
            )
        ],
    )

    update = request_schedules(state)

    image_ref = update["raw_inputs"]["horario_academico_img"]
    assert update["awaiting_user_input"] is False
    assert update["raw_inputs"]["horario_academico_text"] == "Lunes 08:00-10:00 Algebra"
    assert not image_ref.startswith("data:image")
    assert Path(image_ref).exists()
    assert update["last_user_images"] == [image_ref]


def test_request_schedules_extracts_whatsapp_image_from_state_reference(monkeypatch) -> None:
    monkeypatch.setattr(
        "agents.support.flows.scheduling.schedule_capture_service.llm_extract_schedule_from_image",
        lambda image_ref, schedule_hint=None: {
            "is_schedule": True,
            "schedule_type": schedule_hint,
            "extracted_text": "Lunes 08:00-10:00 Algebra",
        },
    )
    state = AgentState(
        phase="schedules",
        awaiting_user_input=True,
        user_message_count=0,
        student_profile={"occupation": "solo_estudio"},
        schedule={"capture_target": "academic", "capture_stage": "awaiting_input"},
        messages=[HumanMessage(content=[{"type": "text", "text": "[imagen recibida]"}])],
        last_user_images=["data:image/png;base64,abc"],
    )

    update = request_schedules(state)

    image_ref = update["raw_inputs"]["horario_academico_img"]
    assert update["awaiting_user_input"] is False
    assert update["raw_inputs"]["horario_academico_text"] == "Lunes 08:00-10:00 Algebra"
    assert not image_ref.startswith("data:image")
    assert Path(image_ref).exists()
    assert update["last_user_images"] == [image_ref]


def test_request_schedules_keeps_student_image_as_file_when_unreadable(monkeypatch) -> None:
    monkeypatch.setattr(
        "agents.support.flows.scheduling.schedule_capture_service.llm_extract_schedule_from_image",
        lambda image_ref, schedule_hint=None: None,
    )
    state = AgentState(
        phase="schedules",
        awaiting_user_input=True,
        user_message_count=0,
        student_profile={"occupation": "solo_estudio"},
        schedule={"capture_target": "academic", "capture_stage": "awaiting_input"},
        messages=[
            HumanMessage(
                content=[
                    {"type": "input_image", "image_url": {"url": "data:image/png;base64,abc"}}
                ]
            )
        ],
    )

    update = request_schedules(state)

    image_ref = update["raw_inputs"]["horario_academico_img"]
    assert update["awaiting_user_input"] is True
    assert "puedo recibir imagenes" in update["messages"][0].content.lower()
    assert not image_ref.startswith("data:image")
    assert Path(image_ref).exists()


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
