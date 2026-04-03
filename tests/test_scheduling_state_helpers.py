"""Pruebas directas para los helpers tipados de scheduling."""

from __future__ import annotations

from agents.support.scheduling.models import ScheduleConflict, WeeklyScheduleBlock
from agents.support.scheduling.state_helpers import (
    append_schedule_input_text,
    replace_schedule_input_text,
    reset_schedule_review_state,
    serialize_schedule_blocks_to_raw_inputs,
    update_schedule_flow_state,
)


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
            "pending_correction_text": "nuevo horario",
            "conflicts_accepted": True,
            "capture_target": "academic",
            "capture_stage": "awaiting_input",
        },
        [block],
    )

    assert update["review_stage"] == "idle"
    assert update["correction_target"] is None
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
