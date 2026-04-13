"""Pruebas del nuevo flujo de revisión, cruces y corrección por sección."""

from __future__ import annotations

from datetime import date

from langchain_core.messages import HumanMessage

from agents.support.nodes.apply_schedule_correction.node import apply_schedule_correction
from agents.support.nodes.validate_schedule.node import validate_schedule
from agents.support.state import AgentState
from schemas.onboarding import StudentProfile
from services.scheduling import ScheduleConflict, WeeklyScheduleBlock


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


def test_validate_schedule_confirmation_yes_requests_schedule_end_date() -> None:
    block = _academic_block()
    state = AgentState(
        phase="validate",
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="sí, está correcto")],
        schedule={"blocks": [block], "review_stage": "awaiting_confirmation"},
    )

    update = validate_schedule(state)

    assert update["phase"] == "validate"
    assert update["awaiting_user_input"] is True
    assert update["schedule"]["review_stage"] == "awaiting_schedule_end_date"
    assert update["schedule"]["blocks"][0].user_confirmed is True
    assert "fecha límite" in update["messages"][0].content.lower()


def test_validate_schedule_schedule_end_date_moves_to_persist(monkeypatch) -> None:
    block = _academic_block().model_copy(update={"user_confirmed": True})
    state = AgentState(
        phase="validate",
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="2026-06-30")],
        schedule={"blocks": [block], "review_stage": "awaiting_schedule_end_date"},
    )

    import agents.support.flows.scheduling.schedule_review_service as review_module

    monkeypatch.setattr(
        review_module,
        "parse_schedule_end_date",
        lambda *_args, **_kwargs: date(2026, 6, 30),
    )
    update = validate_schedule(state)

    assert update["phase"] == "schedule_persist"
    assert update["events_validated"] is True
    assert update["schedule"]["schedule_end_date"] == "2026-06-30"


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


def test_validate_schedule_correction_target_opens_shared_item_editor_for_work() -> None:
    state = AgentState(
        phase="validate",
        awaiting_user_input=True,
        user_message_count=0,
        student_profile=StudentProfile(occupation="ambos"),
        messages=[HumanMessage(content="2")],
        schedule={
            "blocks": [_academic_block(), _work_block()],
            "review_stage": "awaiting_correction_target",
        },
    )

    update = validate_schedule(state)

    assert update["phase"] == "validate"
    assert update["schedule"]["review_stage"] == "section_awaiting_item_selection"
    assert update["schedule"]["correction_target"] == "work"
    prompt = update["messages"][0].content.lower()
    assert "horario laboral actual" in prompt
    assert "trabajo" in prompt
    assert "elige el número" in prompt
    assert "envíame de nuevo solo tu horario laboral" not in prompt


def test_validate_schedule_correction_target_opens_shared_item_editor_for_extracurricular() -> None:
    state = AgentState(
        phase="validate",
        awaiting_user_input=True,
        user_message_count=0,
        student_profile=StudentProfile(occupation="ambos"),
        extracurricular=[
            {
                "nombre": "Gimnasio",
                "es_variable": False,
                "detalle": "Martes 19:00-20:30",
                "dias": ["Martes"],
                "hora_inicio": "19:00",
                "hora_fin": "20:30",
            }
        ],
        messages=[HumanMessage(content="3")],
        schedule={
            "blocks": [
                _academic_block(),
                WeeklyScheduleBlock(
                    block_type="extracurricular",
                    title="Gimnasio",
                    day_of_week="tuesday",
                    start_time="19:00",
                    end_time="20:30",
                    source_text="Martes Gimnasio 19:00-20:30",
                ),
            ],
            "review_stage": "awaiting_correction_target",
        },
    )

    update = validate_schedule(state)

    assert update["phase"] == "validate"
    assert update["schedule"]["review_stage"] == "section_awaiting_item_selection"
    assert update["schedule"]["correction_target"] == "extracurricular"
    prompt = update["messages"][0].content.lower()
    assert "horario extracurricular actual" in prompt
    assert "gimnasio" in prompt
    assert "elige el número" in prompt
    assert "envíame de nuevo solo las actividades" not in prompt


def test_validate_schedule_no_input_does_not_duplicate_conflict_prompt() -> None:
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
        awaiting_user_input=False,
        user_message_count=0,
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

    assert update["awaiting_user_input"] is True
    assert "messages" not in update


def test_validate_schedule_shared_item_edit_routes_to_draft_for_rerender() -> None:
    academic = _academic_block("Calculo")
    state = AgentState(
        phase="validate",
        awaiting_user_input=True,
        user_message_count=0,
        raw_inputs={"horario_academico_text": "Lunes 08:00-10:00 Calculo"},
        messages=[HumanMessage(content="9:30 am a 10:30 am")],
        schedule={
            "blocks": [academic],
            "review_stage": "section_awaiting_field_value",
            "correction_target": "academic",
            "editing_block_id": academic.block_id,
            "editing_field": "time_range",
        },
    )

    update = validate_schedule(state)

    assert update["phase"] == "draft"
    assert update["awaiting_user_input"] is False
    assert update["schedule"]["review_stage"] == "idle"
    assert update["schedule"]["blocks"][0].start_time == "09:30"
    assert update["schedule"]["blocks"][0].end_time == "10:30"


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
    assert [item.nombre for item in first_update["extracurricular"]] == ["Gimnasio", "Centro Comercial"]
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
        "Gimnasio",
        "Centro Comercial",
        "Iglesia",
    ]
    blocks = [block for block in second_update["schedule"]["blocks"] if block.block_type == "extracurricular"]
    assert [(block.title, block.day_of_week, block.start_time, block.end_time) for block in blocks] == [
        ("Gimnasio", "saturday", "10:00", "12:00"),
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

    assert first_update["phase"] == "draft"
    assert first_update["work_pending_items"] == []
    blocks = {
        (block.day_of_week, block.start_time, block.end_time)
        for block in first_update["schedule"]["blocks"]
        if block.block_type == "work"
    }
    assert blocks == {
        ("monday", "07:00", "10:00"),
        ("tuesday", "07:00", "10:00"),
        ("wednesday", "07:00", "10:00"),
        ("thursday", "07:00", "10:00"),
        ("friday", "07:00", "10:00"),
    }
