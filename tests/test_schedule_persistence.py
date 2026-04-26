"""Pruebas de persistencia del horario recurrente."""

from __future__ import annotations

from agents.support.dependencies import (
    set_outlook_fixed_schedule_sync_service,
    set_schedule_service,
)
from agents.support.nodes.persist_schedule.node import persist_schedule
from agents.support.nodes.sync_fixed_schedule.node import sync_fixed_schedule
from agents.support.state import AgentState
from repositories.scheduling.repository import InMemoryScheduleRepository
from services.scheduling import ScheduleService, WeeklyScheduleBlock


def _block() -> WeeklyScheduleBlock:
    return WeeklyScheduleBlock(
        block_type="academic",
        title="Calculo",
        day_of_week="monday",
        start_time="06:00",
        end_time="08:00",
        source_text="Lunes cálculo 6-8",
    )


def test_schedule_service_persists_schedule_in_memory() -> None:
    service = ScheduleService(repository=InMemoryScheduleRepository())

    result = service.persist_schedule(
        student_id=7,
        occupation="solo_estudio",
        timezone="America/Bogota",
        summary_text="resumen",
        blocks=[_block()],
        conflicts=[],
        conflicts_accepted=False,
        schedule_end_date=None,
    )

    assert result.persisted is True
    assert result.schedule_profile_id == 1
    assert result.block_count == 1


def test_persist_schedule_node_uses_schedule_service() -> None:
    service = ScheduleService(repository=InMemoryScheduleRepository())
    set_schedule_service(service)
    try:
        state = AgentState(
            phase="schedule_persist",
            student_profile={"persisted_student_id": 15, "occupation": "solo_estudio"},
            schedule={
                "blocks": [_block()],
                "summary_text": "resumen",
                "conflicts": [],
                "schedule_end_date": "2026-06-30",
            },
        )

        update = persist_schedule(state)

        assert update["phase"] == "schedule_sync"
        assert update["schedule"]["persisted_profile_id"] == 1
        assert update["schedule"]["schedule_end_date"] == "2026-06-30"
        assert "guardado correctamente" in update["messages"][0].content.lower()
    finally:
        set_schedule_service(None)


class _FixedScheduleSyncServiceStub:
    def sync_schedule_profile(
        self,
        *,
        student_id: int | None,
        schedule_profile_id: int | None,
        calendar_state: dict | None = None,
        calendar_id: str | None = None,
    ):
        assert student_id == 15
        assert schedule_profile_id == 9
        assert calendar_id == "calendar-1"

        class _Result:
            synced = True
            synced_event_map = {"block-1": "outlook:block-1"}

        return _Result()


def test_sync_fixed_schedule_node_marks_outlook_sync_success() -> None:
    set_outlook_fixed_schedule_sync_service(_FixedScheduleSyncServiceStub())
    try:
        state = AgentState(
            phase="schedule_sync",
            student_profile={"persisted_student_id": 15},
            schedule={"persisted_profile_id": 9, "schedule_end_date": "2026-06-30"},
            calendar={"calendar_id": "calendar-1"},
        )

        update = sync_fixed_schedule(state)

        assert update["phase"] == "study_profile"
        assert update["calendar"]["provider"] == "outlook"
        assert update["calendar"]["authorized"] is True
        assert update["calendar"]["synced_event_map"] == {"block-1": "outlook:block-1"}
        assert "30/06/2026" in update["messages"][0].content
    finally:
        set_outlook_fixed_schedule_sync_service(None)
