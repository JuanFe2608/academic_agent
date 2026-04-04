"""Pruebas de regresión para los servicios de aplicación de scheduling."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from agents.support.flows.scheduling.schedule_capture_service import (
    ScheduleCapturePrompts,
    handle_schedule_capture_turn,
)
from agents.support.flows.scheduling.schedule_review_service import (
    apply_schedule_correction_turn,
    handle_schedule_review_turn,
)
from agents.support.state import AgentState
from schemas.onboarding import StudentProfile
from schemas.scheduling import PendingScheduleItem
from services.scheduling import WeeklyScheduleBlock


def _capture_prompts() -> ScheduleCapturePrompts:
    return ScheduleCapturePrompts(
        occupation="occupation",
        academic="academic",
        work="work",
        none="none",
        more_academic="more academic",
        more_work="more work",
    )


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


def test_handle_schedule_capture_turn_prompts_for_more_after_last_pending_item() -> None:
    state = AgentState(
        phase="schedules",
        awaiting_user_input=True,
        student_profile={"occupation": "solo_estudio"},
        schedule={"blocks": [], "capture_target": "academic", "capture_stage": "awaiting_input"},
        academic_pending_items=[
            PendingScheduleItem(
                schedule_type="academic",
                days=["martes", "jueves"],
                missing_fields=["nombre de la materia o actividad"],
                raw_text="Martes y jueves de 6 a 8",
            )
        ],
        messages=[HumanMessage(content="Programacion")],
    )

    update = handle_schedule_capture_turn(
        state,
        has_new_input=True,
        last_text="Programacion",
        current_count=1,
        prompts=_capture_prompts(),
    )

    assert update["phase"] == "schedules"
    assert update["awaiting_user_input"] is True
    assert update["schedule"]["capture_stage"] == "awaiting_more"
    assert update["messages"][0].content == "more academic"
    assert "Programacion" in update["raw_inputs"]["horario_academico_text"]


def test_handle_schedule_review_turn_opens_correction_menu_from_confirmation() -> None:
    state = AgentState(
        phase="validate",
        awaiting_user_input=True,
        student_profile=StudentProfile(occupation="ambos"),
        schedule={"blocks": [_academic_block(), _work_block()], "review_stage": "awaiting_confirmation"},
        messages=[HumanMessage(content="corregir")],
    )

    update = handle_schedule_review_turn(
        state,
        has_new_input=True,
        last_text="corregir",
        current_count=1,
    )

    assert update["phase"] == "validate"
    assert update["schedule"]["review_stage"] == "awaiting_correction_target"
    assert update["awaiting_user_input"] is True
    prompt = update["messages"][0].content.lower()
    assert "horario académico" in prompt
    assert "horario laboral" in prompt
    assert "actividades extracurriculares" in prompt


def test_apply_schedule_correction_turn_updates_only_requested_section() -> None:
    state = AgentState(
        phase="schedule_edit",
        raw_inputs={"horario_academico_text": "Lunes 08:00-10:00 Calculo"},
        schedule={
            "blocks": [_academic_block("Calculo"), _work_block()],
            "correction_target": "academic",
            "pending_correction_text": "Martes y jueves Programacion de 6 pm a 8 pm",
        },
    )

    update = apply_schedule_correction_turn(state)

    assert update["phase"] == "draft"
    blocks = update["schedule"]["blocks"]
    assert any(block.block_type == "work" for block in blocks)
    assert any(block.title == "Programacion" for block in blocks)
    assert all(block.title != "Calculo" for block in blocks if block.block_type == "academic")
