"""Pruebas de regresión para el servicio de parsing de scheduling."""

from __future__ import annotations

from agents.support.scheduling.schedule_parsing_service import (
    ScheduleParsingPrompts,
    handle_schedule_parsing_turn,
)
from agents.support.state import AgentState


def _prompts() -> ScheduleParsingPrompts:
    return ScheduleParsingPrompts(
        academic_text_required="academic text required",
        work_text_required="work text required",
        work_request="work request",
        more_academic="more academic",
        more_work="more work",
    )


def test_handle_schedule_parsing_turn_requires_academic_text_when_only_image() -> None:
    state = AgentState(
        phase="schedules",
        raw_inputs={"horario_academico_img": "data:image/png;base64,abc"},
    )

    update = handle_schedule_parsing_turn(state, prompts=_prompts())

    assert update["phase"] == "schedules"
    assert update["awaiting_user_input"] is True
    assert update["messages"][0].content == "academic text required"


def test_handle_schedule_parsing_turn_prompts_work_for_ambos_after_valid_academic() -> None:
    state = AgentState(
        phase="schedules",
        student_profile={"occupation": "ambos"},
        raw_inputs={"horario_academico_text": "Lunes 08:00-10:00 Algebra"},
    )

    update = handle_schedule_parsing_turn(state, prompts=_prompts())

    assert update["phase"] == "schedules"
    assert update["awaiting_user_input"] is True
    assert update["schedule"]["capture_target"] == "work"
    assert update["messages"][0].content == "work request"


def test_handle_schedule_parsing_turn_moves_to_extras_when_complete() -> None:
    state = AgentState(
        phase="schedules",
        raw_inputs={"horario_academico_text": "Lunes 08:00-10:00 Algebra"},
    )

    update = handle_schedule_parsing_turn(state, prompts=_prompts())

    assert update["phase"] == "extras"
    assert update["awaiting_user_input"] is False
    assert update["academic_pending_items"] == []
    assert update["work_pending_items"] == []
    assert len(update["events"]) == 1
