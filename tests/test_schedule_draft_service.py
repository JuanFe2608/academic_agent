"""Pruebas de regresión para la consolidación del draft de scheduling."""

from __future__ import annotations

from agents.support.flows.scheduling.schedule_draft_service import build_schedule_draft_turn
from agents.support.state import AgentState
from services.scheduling import WeeklyScheduleBlock


def _academic_block() -> WeeklyScheduleBlock:
    return WeeklyScheduleBlock(
        block_type="academic",
        title="Calculo",
        day_of_week="monday",
        start_time="08:00",
        end_time="10:00",
        source_text="Lunes 08:00-10:00 Calculo",
    )


def _work_block() -> WeeklyScheduleBlock:
    return WeeklyScheduleBlock(
        block_type="work",
        title="Trabajo",
        day_of_week="monday",
        start_time="09:00",
        end_time="18:00",
        source_text="Lunes 09:00-18:00 Trabajo",
    )


def test_build_schedule_draft_turn_detects_conflicts_and_prepares_validate() -> None:
    state = AgentState(
        phase="draft",
        schedule={"blocks": [_academic_block(), _work_block()]},
    )

    update = build_schedule_draft_turn(state)

    assert update["phase"] == "validate"
    assert update["events_validated"] is False
    assert update["schedule"]["review_stage"] == "idle"
    assert len(update["schedule"]["conflicts"]) == 1
    assert any(block.has_conflict for block in update["schedule"]["blocks"])
    assert update["schedule_preview"]["image_path"] is None
    assert "Calculo" in update["schedule_preview"]["text"]
    assert "Trabajo" in update["schedule_preview"]["text"]


def test_build_schedule_draft_turn_builds_clean_summary_without_conflicts() -> None:
    state = AgentState(
        phase="draft",
        schedule={"blocks": [_academic_block()]},
    )

    update = build_schedule_draft_turn(state)

    assert update["phase"] == "validate"
    assert update["schedule"]["conflicts"] == []
    assert update["schedule"]["blocks"][0].has_conflict is False
    assert update["schedule_preview"]["text"] == update["schedule"]["summary_text"]
    assert len(update["events"]) == 1
    assert update["events"][0].id == f"schedule-block:{update['schedule']['blocks'][0].block_id}"
    assert update["events"][0].origen == "schedule_block"
