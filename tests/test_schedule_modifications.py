"""Pruebas del nuevo flujo de revisión, cruces y corrección por sección."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from agents.support.nodes.apply_schedule_correction.node import apply_schedule_correction
from agents.support.nodes.validate_schedule.node import validate_schedule
from agents.support.scheduling.formatter import build_schedule_summary
from agents.support.scheduling.models import ScheduleConflict, WeeklyScheduleBlock
from agents.support.state import AgentState, StudentProfile


def _academic_block(title: str = "Calculo") -> WeeklyScheduleBlock:
    return WeeklyScheduleBlock(
        block_type="academic",
        title=title,
        day_of_week="monday",
        start_time="08:00",
        end_time="10:00",
        source_text="Lunes 08:00-10:00",
    )


def _work_block(title: str = "Trabajo") -> WeeklyScheduleBlock:
    return WeeklyScheduleBlock(
        block_type="work",
        title=title,
        day_of_week="monday",
        start_time="09:00",
        end_time="18:00",
        source_text="Lunes 09:00-18:00",
    )


def test_validate_schedule_accepts_conflict_then_moves_to_confirmation() -> None:
    academic = _academic_block()
    work = _work_block()
    conflict = ScheduleConflict(
        day_of_week="monday",
        left_block_id=academic.block_id,
        right_block_id=work.block_id,
        left_title=academic.title,
        right_title=work.title,
        left_type=academic.block_type,
        right_type=work.block_type,
        overlap_start="09:00",
        overlap_end="10:00",
    )
    state = AgentState(
        phase="validate",
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="dejarlo así")],
        schedule={
            "blocks": [
                academic.model_copy(update={"has_conflict": True}),
                work.model_copy(update={"has_conflict": True}),
            ],
            "conflicts": [conflict],
            "review_stage": "awaiting_conflict_decision",
        },
    )

    update = validate_schedule(state)

    assert update["schedule"]["conflicts_accepted"] is True
    assert update["schedule"]["review_stage"] == "awaiting_confirmation"
    assert update["awaiting_user_input"] is True


def test_validate_schedule_confirmation_yes_moves_to_persist() -> None:
    block = _academic_block()
    state = AgentState(
        phase="validate",
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="sí, está correcto")],
        schedule={"blocks": [block], "review_stage": "awaiting_confirmation"},
    )

    update = validate_schedule(state)

    assert update["phase"] == "schedule_persist"
    assert update["events_validated"] is True
    assert update["schedule"]["blocks"][0].user_confirmed is True


def test_validate_schedule_correction_menu_for_solo_estudio_hides_work() -> None:
    state = AgentState(
        phase="validate",
        awaiting_user_input=True,
        user_message_count=0,
        student_profile=StudentProfile(occupation="solo_estudio"),
        messages=[HumanMessage(content="no, quiero corregirlo")],
        schedule={"blocks": [_academic_block()], "review_stage": "awaiting_confirmation"},
    )

    update = validate_schedule(state)

    prompt = update["messages"][0].content.lower()
    assert "horario académico" in prompt
    assert "actividades extracurriculares" in prompt
    assert "horario laboral" not in prompt


def test_validate_schedule_correction_menu_for_ambos_shows_work() -> None:
    state = AgentState(
        phase="validate",
        awaiting_user_input=True,
        user_message_count=0,
        student_profile=StudentProfile(occupation="ambos"),
        messages=[HumanMessage(content="corregir")],
        schedule={"blocks": [_academic_block(), _work_block()], "review_stage": "awaiting_confirmation"},
    )

    update = validate_schedule(state)

    prompt = update["messages"][0].content.lower()
    assert "horario académico" in prompt
    assert "horario laboral" in prompt
    assert "actividades extracurriculares" in prompt


def test_validate_schedule_collects_correction_payload_and_moves_to_schedule_edit() -> None:
    state = AgentState(
        phase="validate",
        awaiting_user_input=True,
        user_message_count=0,
        student_profile=StudentProfile(occupation="ambos"),
        messages=[HumanMessage(content="lunes a viernes de 7 am a 6 pm")],
        schedule={
            "blocks": [_academic_block(), _work_block()],
            "review_stage": "awaiting_correction_payload",
            "correction_target": "work",
        },
    )

    update = validate_schedule(state)

    assert update["phase"] == "schedule_edit"
    assert update["schedule"]["pending_correction_text"] == "lunes a viernes de 7 am a 6 pm"


def test_apply_schedule_correction_replaces_academic_section_only() -> None:
    academic = _academic_block("Calculo")
    work = _work_block()
    state = AgentState(
        phase="schedule_edit",
        raw_inputs={"horario_academico_text": "Lunes 08:00-10:00 Calculo"},
        schedule={
            "blocks": [academic, work],
            "correction_target": "academic",
            "pending_correction_text": "Martes y jueves Programacion de 6 pm a 8 pm",
        },
    )

    update = apply_schedule_correction(state)

    assert update["phase"] == "draft"
    blocks = update["schedule"]["blocks"]
    assert any(block.block_type == "work" for block in blocks)
    assert any(block.title == "Programacion" for block in blocks)
    assert all(block.title != "Calculo" for block in blocks if block.block_type == "academic")


def test_apply_schedule_correction_can_clear_extracurricular_section() -> None:
    extracurricular = WeeklyScheduleBlock(
        block_type="extracurricular",
        title="Gimnasio",
        day_of_week="tuesday",
        start_time="19:00",
        end_time="20:30",
        source_text="Gimnasio martes 19:00-20:30",
    )
    state = AgentState(
        phase="schedule_edit",
        extras_has_any=True,
        extracurricular=[],
        schedule={
            "blocks": [_academic_block(), extracurricular],
            "correction_target": "extracurricular",
            "pending_correction_text": "ninguna",
        },
    )

    update = apply_schedule_correction(state)

    assert update["phase"] == "draft"
    assert update["extras_has_any"] is False
    assert all(block.block_type != "extracurricular" for block in update["schedule"]["blocks"])


def test_apply_schedule_correction_remembers_pending_extracurricular_context_between_turns() -> None:
    state = AgentState(
        phase="schedule_edit",
        schedule={
            "blocks": [_academic_block()],
            "correction_target": "extracurricular",
            "pending_correction_text": (
                "voy los dias sabados al gimnasio de 10 am a 12 pm, "
                "luego voy al centro comercial de 2 pm a 4 pm y los domingos voy a la iglesia"
            ),
            "review_stage": "idle",
        },
    )

    first_update = apply_schedule_correction(state)

    assert first_update["phase"] == "validate"
    assert first_update["awaiting_user_input"] is True
    assert len(first_update["extracurricular"]) == 2
    assert [item.nombre for item in first_update["extracurricular"]] == ["Gym", "Centro Comercial"]
    prompt = first_update["messages"][0].content.lower()
    assert "iglesia" in prompt
    assert "puedes responder solo con lo que falta" in prompt

    validate_state = AgentState(
        phase="validate",
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="el horario de la iglesia es de 7 am a 8 am")],
        schedule=first_update["schedule"],
        extracurricular=first_update["extracurricular"],
        extras_pending_items=first_update["extras_pending_items"],
    )

    validation_update = validate_schedule(validate_state)

    assert validation_update["phase"] == "schedule_edit"

    second_state = AgentState(
        phase="schedule_edit",
        extracurricular=first_update["extracurricular"],
        extras_pending_items=first_update["extras_pending_items"],
        schedule=validation_update["schedule"],
    )

    second_update = apply_schedule_correction(second_state)

    assert second_update["phase"] == "draft"
    assert second_update["extras_pending_items"] == []
    assert [item.nombre for item in second_update["extracurricular"]] == [
        "Gym",
        "Centro Comercial",
        "Iglesia",
    ]
    blocks = [block for block in second_update["schedule"]["blocks"] if block.block_type == "extracurricular"]
    assert [(block.title, block.day_of_week, block.start_time, block.end_time) for block in blocks] == [
        ("Gym", "saturday", "10:00", "12:00"),
        ("Centro Comercial", "saturday", "14:00", "16:00"),
        ("Iglesia", "sunday", "07:00", "08:00"),
    ]


def test_apply_schedule_correction_remembers_pending_work_context_between_turns() -> None:
    state = AgentState(
        phase="schedule_edit",
        raw_inputs={"horario_laboral_text": "Lunes 09:00-18:00"},
        schedule={
            "blocks": [_academic_block(), _work_block()],
            "correction_target": "work",
            "pending_correction_text": "Trabajo de lunes a viernes de 7 a 10",
            "review_stage": "idle",
        },
    )

    first_update = apply_schedule_correction(state)

    assert first_update["phase"] == "validate"
    assert first_update["awaiting_user_input"] is True
    assert len(first_update["work_pending_items"]) == 1
    prompt = first_update["messages"][0].content.lower()
    assert "trabajo" in prompt
    assert "puedes responder solo con lo que falta" in prompt

    validate_state = AgentState(
        phase="validate",
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="pm")],
        schedule=first_update["schedule"],
        work_pending_items=first_update["work_pending_items"],
        raw_inputs=state.raw_inputs,
    )

    validation_update = validate_schedule(validate_state)

    assert validation_update["phase"] == "schedule_edit"

    second_state = AgentState(
        phase="schedule_edit",
        raw_inputs=state.raw_inputs,
        work_pending_items=first_update["work_pending_items"],
        schedule=validation_update["schedule"],
    )

    second_update = apply_schedule_correction(second_state)

    assert second_update["phase"] == "draft"
    assert second_update["work_pending_items"] == []
    blocks = {
        (block.day_of_week, block.start_time, block.end_time)
        for block in second_update["schedule"]["blocks"]
        if block.block_type == "work"
    }
    assert blocks == {
        ("monday", "19:00", "22:00"),
        ("tuesday", "19:00", "22:00"),
        ("wednesday", "19:00", "22:00"),
        ("thursday", "19:00", "22:00"),
        ("friday", "19:00", "22:00"),
    }
