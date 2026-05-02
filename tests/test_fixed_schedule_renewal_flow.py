"""Pruebas del subflujo de renovación del horario fijo vencido."""

from __future__ import annotations

from datetime import date

import agents.support.flows.scheduling.fixed_schedule_renewal_service as renewal_module
from agents.support.dependencies import (
    set_outlook_fixed_schedule_sync_service,
    set_schedule_service,
)
from agents.support.flows.scheduling.fixed_schedule_renewal_service import (
    handle_fixed_schedule_renewal_turn,
)
from agents.support.state import AgentState
from repositories.scheduling.repository import InMemoryScheduleRepository
from services.scheduling import ScheduleService, WeeklyScheduleBlock


def _block() -> WeeklyScheduleBlock:
    return WeeklyScheduleBlock(
        block_type="academic",
        title="Calculo",
        day_of_week="monday",
        start_time="07:00",
        end_time="09:00",
        source_text="Lunes cálculo 7-9",
    )


class _FixedScheduleSyncServiceStub:
    def sync_schedule_profile(
        self,
        *,
        student_id: int | None,
        schedule_profile_id: int | None,
        calendar_state: dict | None = None,
        calendar_id: str | None = None,
    ):
        class _Result:
            synced = True
            synced_event_map = {"block-1": "outlook:block-1"}

        return _Result()


def test_fixed_schedule_renewal_prompts_when_current_schedule_expired(monkeypatch) -> None:
    monkeypatch.setattr(renewal_module, "is_schedule_expired", lambda *_args, **_kwargs: True)
    service = ScheduleService(repository=InMemoryScheduleRepository())
    service.persist_schedule(
        student_id=11,
        occupation="solo_estudio",
        timezone="America/Bogota",
        summary_text="Horario fijo",
        blocks=[_block()],
        conflicts=[],
        conflicts_accepted=False,
        schedule_end_date=date(2026, 4, 1),
    )
    set_schedule_service(service)
    try:
        state = AgentState(
            phase="end",
            student_profile={"persisted_student_id": 11},
        )

        update = handle_fixed_schedule_renewal_turn(
            state,
            has_new_input=True,
            last_text="hola",
            current_count=1,
        )

        assert update["phase"] == "schedule_renewal"
        assert update["awaiting_user_input"] is True
        assert update["schedule"]["renewal_stage"] == "awaiting_decision"
        assert "fecha límite" in update["messages"][0].content.lower()
    finally:
        set_schedule_service(None)


def test_fixed_schedule_renewal_updates_end_date_and_resyncs(monkeypatch) -> None:
    monkeypatch.setattr(renewal_module, "is_schedule_expired", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        renewal_module,
        "parse_schedule_end_date",
        lambda *_args, **_kwargs: date(2026, 6, 30),
    )
    repository = InMemoryScheduleRepository()
    service = ScheduleService(repository=repository)
    persist_result = service.persist_schedule(
        student_id=15,
        occupation="solo_estudio",
        timezone="America/Bogota",
        summary_text="Horario fijo",
        blocks=[_block().model_copy(update={"block_id": "block-1"})],
        conflicts=[],
        conflicts_accepted=False,
        schedule_end_date=date(2026, 4, 1),
    )
    set_schedule_service(service)
    set_outlook_fixed_schedule_sync_service(_FixedScheduleSyncServiceStub())
    try:
        state = AgentState(
            phase="schedule_renewal",
            awaiting_user_input=True,
            student_profile={"persisted_student_id": 15},
            calendar={"calendar_id": "calendar-1"},
            schedule={
                "renewal_stage": "awaiting_end_date",
                "persisted_profile_id": persist_result.schedule_profile_id,
            },
        )

        update = handle_fixed_schedule_renewal_turn(
            state,
            has_new_input=True,
            last_text="2026-06-30",
            current_count=1,
        )

        lookup = service.get_current_schedule_profile(student_id=15)

        assert lookup.found is True
        assert lookup.profile is not None
        assert lookup.profile.schedule_end_date == date(2026, 6, 30)
        assert update["phase"] == "end"
        assert update["schedule"]["renewal_stage"] == "idle"
        assert update["schedule"]["schedule_end_date"] == "2026-06-30"
        assert update["calendar"]["provider"] == "outlook"
        assert "30/06/2026" in update["messages"][0].content
    finally:
        set_outlook_fixed_schedule_sync_service(None)
        set_schedule_service(None)


def test_fixed_schedule_renewal_accepts_compact_day_month_short_year(monkeypatch) -> None:
    monkeypatch.setattr(renewal_module, "is_schedule_expired", lambda *_args, **_kwargs: True)
    import services.scheduling.end_date_support as end_date_module

    monkeypatch.setattr(
        end_date_module,
        "current_local_date",
        lambda _timezone_name: date(2026, 5, 2),
    )
    repository = InMemoryScheduleRepository()
    service = ScheduleService(repository=repository)
    persist_result = service.persist_schedule(
        student_id=15,
        occupation="solo_estudio",
        timezone="America/Bogota",
        summary_text="Horario fijo",
        blocks=[_block().model_copy(update={"block_id": "block-1"})],
        conflicts=[],
        conflicts_accepted=False,
        schedule_end_date=date(2026, 4, 1),
    )
    set_schedule_service(service)
    set_outlook_fixed_schedule_sync_service(_FixedScheduleSyncServiceStub())
    try:
        state = AgentState(
            phase="schedule_renewal",
            awaiting_user_input=True,
            student_profile={"persisted_student_id": 15},
            calendar={"calendar_id": "calendar-1"},
            schedule={
                "renewal_stage": "awaiting_end_date",
                "persisted_profile_id": persist_result.schedule_profile_id,
            },
        )

        update = handle_fixed_schedule_renewal_turn(
            state,
            has_new_input=True,
            last_text="30 06 26",
            current_count=1,
        )

        lookup = service.get_current_schedule_profile(student_id=15)

        assert lookup.found is True
        assert lookup.profile is not None
        assert lookup.profile.schedule_end_date == date(2026, 6, 30)
        assert update["phase"] == "end"
        assert update["schedule"]["schedule_end_date"] == "2026-06-30"
    finally:
        set_outlook_fixed_schedule_sync_service(None)
        set_schedule_service(None)
