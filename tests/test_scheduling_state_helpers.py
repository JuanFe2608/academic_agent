"""Pruebas directas para los helpers tipados de scheduling."""

from __future__ import annotations

from agents.support.scheduling.state_helpers import (
    append_schedule_input_text,
    replace_schedule_input_text,
    reset_schedule_review_state,
    serialize_schedule_blocks_to_raw_inputs,
    update_scheduling_state,
    update_schedule_flow_state,
)
from agents.support.state import AgentState
from services.scheduling import ScheduleConflict, WeeklyScheduleBlock


def _academic_block() -> WeeklyScheduleBlock:
    return WeeklyScheduleBlock(
        block_type="academic",
        title="Calculo",
        day_of_week="monday",
        start_time="08:00",
        end_time="10:00",
        source_text="Lunes 08:00-10:00 Calculo",
    )


def test_update_schedule_flow_state_preserves_block_models() -> None:
    block = _academic_block()

    update = update_schedule_flow_state(
        {"blocks": [block], "review_stage": "idle"},
        review_stage="awaiting_confirmation",
    )

    assert update["review_stage"] == "awaiting_confirmation"
    assert isinstance(update["blocks"][0], WeeklyScheduleBlock)
    assert update["blocks"][0].title == "Calculo"


def test_reset_schedule_review_state_clears_review_artifacts() -> None:
    block = _academic_block()
    conflict = ScheduleConflict(
        day_of_week="monday",
        left_block_id=block.block_id,
        right_block_id="other",
        left_title=block.title,
        right_title="Trabajo",
        left_type="academic",
        right_type="work",
        overlap_start="09:00",
        overlap_end="10:00",
        accepted=True,
    )

    update = reset_schedule_review_state(
        {
            "blocks": [block],
            "conflicts": [conflict],
            "review_stage": "awaiting_correction_payload",
            "correction_target": "academic",
            "editing_block_id": block.block_id,
            "editing_block_ids": [block.block_id],
            "editing_field": "start_time",
            "pending_correction_text": "nuevo horario",
            "conflicts_accepted": True,
            "capture_target": "academic",
            "capture_stage": "awaiting_input",
        },
        [block],
    )

    assert update["review_stage"] == "idle"
    assert update["correction_target"] is None
    assert update["editing_block_id"] is None
    assert update["editing_block_ids"] == []
    assert update["editing_field"] is None
    assert update["pending_correction_text"] is None
    assert update["conflicts"] == []
    assert update["conflicts_accepted"] is False
    assert update["capture_target"] == "academic"
    assert update["capture_stage"] == "awaiting_input"


def test_raw_input_helpers_update_only_target_section() -> None:
    appended = append_schedule_input_text({}, "academic", "Lunes 08:00-10:00 Calculo")
    replaced = replace_schedule_input_text(appended, "work", "Lunes 09:00-18:00")
    serialized = serialize_schedule_blocks_to_raw_inputs(
        replaced,
        "academic",
        [_academic_block()],
    )

    assert appended["horario_academico_text"] == "Lunes 08:00-10:00 Calculo"
    assert replaced["horario_laboral_text"] == "Lunes 09:00-18:00"
    assert serialized["horario_academico_text"] == "Lunes 08:00-10:00 Calculo"
    assert serialized["horario_laboral_text"] == "Lunes 09:00-18:00"


def test_update_scheduling_state_resyncs_only_schedule_block_events() -> None:
    block = _academic_block()
    state = AgentState(
        events=[
            {
                "id": "study-plan-1",
                "dia": "Martes",
                "inicio": "14:00",
                "fin": "15:00",
                "titulo": "Sesion de estudio",
                "tipo": "confirmado",
                "categoria": "estudio",
                "origen": "study_planner",
                "timezone": "America/Bogota",
            }
        ],
        schedule={"blocks": []},
    )

    update = update_scheduling_state(
        state,
        schedule={"blocks": [block], "review_stage": "idle"},
    )

    assert "events" in update
    assert [event.origen for event in update["events"]] == [
        "schedule_block",
        "study_planner",
    ]
    assert update["events"][0].id == f"schedule-block:{block.block_id}"
    assert update["events"][0].titulo == "Calculo"
    assert update["events"][1].id == "study-plan-1"
