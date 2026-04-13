"""Pruebas del subflujo conversacional de reparación del horario fijo."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from agents.support.dependencies import (
    set_outlook_fixed_schedule_repair_service,
    set_schedule_service,
)
from agents.support.flows.scheduling.fixed_schedule_repair_service import (
    handle_fixed_schedule_repair_turn,
)
from agents.support.state import AgentState
from repositories.scheduling.repository import (
    InMemoryScheduleRepository,
    RecurringScheduleBlockSyncUpdate,
)
from services.scheduling import ScheduleService, WeeklyScheduleBlock


class _FixedScheduleRepairServiceStub:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def repair_schedule_profile(self, **kwargs):
        self.calls.append(dict(kwargs))
        return SimpleNamespace(
            repaired=True,
            repairable_count=1,
            restored_count=1,
            recreated_count=0,
            synced_event_map={"block-1": "outlook:block-1"},
            error_code=None,
            detail=None,
        )


def _block() -> WeeklyScheduleBlock:
    return WeeklyScheduleBlock(
        block_id="block-1",
        block_type="academic",
        title="Calculo",
        day_of_week="monday",
        start_time="07:00",
        end_time="09:00",
        timezone="America/Bogota",
        source_text="Lunes cálculo 7-9",
        user_confirmed=True,
    )


def _schedule_service_with_drifted_block() -> tuple[ScheduleService, int]:
    repository = InMemoryScheduleRepository()
    service = ScheduleService(repository=repository)
    persist_result = service.persist_schedule(
        student_id=21,
        occupation="solo_estudio",
        timezone="America/Bogota",
        summary_text="Horario fijo",
        blocks=[_block()],
        conflicts=[],
        conflicts_accepted=False,
        schedule_end_date=date(2026, 6, 30),
    )
    persisted_block = repository.list_student_schedule_blocks(student_id=21)[0]
    repository.update_block_sync_metadata(
        updates=[
            RecurringScheduleBlockSyncUpdate(
                block_id=persisted_block.id,
                external_provider="outlook",
                external_series_id="outlook:block-1",
                external_event_id="outlook:block-1",
                external_sync_status="drifted",
                external_sync_metadata={},
            )
        ]
    )
    return service, int(persist_result.schedule_profile_id)


def test_fixed_schedule_repair_prompts_when_drift_is_pending() -> None:
    service, profile_id = _schedule_service_with_drifted_block()
    set_schedule_service(service)
    try:
        state = AgentState(
            phase="end",
            student_profile={"persisted_student_id": 21},
        )

        update = handle_fixed_schedule_repair_turn(
            state,
            has_new_input=True,
            last_text="hola",
            current_count=1,
        )

        assert update["phase"] == "schedule_repair"
        assert update["awaiting_user_input"] is True
        assert update["schedule"]["repair_stage"] == "awaiting_decision"
        assert update["schedule"]["persisted_profile_id"] == profile_id
        assert "cambios manuales" in update["messages"][0].content
    finally:
        set_schedule_service(None)


def test_fixed_schedule_repair_restores_outlook_after_confirmation() -> None:
    service, profile_id = _schedule_service_with_drifted_block()
    repair_service = _FixedScheduleRepairServiceStub()
    set_schedule_service(service)
    set_outlook_fixed_schedule_repair_service(repair_service)
    try:
        state = AgentState(
            phase="schedule_repair",
            awaiting_user_input=True,
            student_profile={"persisted_student_id": 21},
            calendar={"calendar_id": "calendar-1"},
            schedule={
                "repair_stage": "awaiting_decision",
                "persisted_profile_id": profile_id,
            },
        )

        update = handle_fixed_schedule_repair_turn(
            state,
            has_new_input=True,
            last_text="1",
            current_count=1,
        )

        assert update["phase"] == "end"
        assert update["awaiting_user_input"] is False
        assert update["schedule"]["repair_stage"] == "idle"
        assert update["calendar"]["provider"] == "outlook"
        assert update["calendar"]["synced_event_map"] == {"block-1": "outlook:block-1"}
        assert repair_service.calls[0]["schedule_profile_id"] == profile_id
    finally:
        set_outlook_fixed_schedule_repair_service(None)
        set_schedule_service(None)
