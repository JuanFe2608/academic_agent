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


def _bad_block(day_of_week: str = "Inglés") -> dict:
    return {
        "block_id": "bad-1",
        "block_type": "academic",
        "title": "Inglés",
        "day_of_week": day_of_week,
        "start_time": "10:00",
        "end_time": "12:00",
        "frequency": "weekly",
        "timezone": "America/Bogota",
        "source_text": "inglés lunes 10-12",
        "normalized_title": "Inglés",
        "original_title": "Inglés",
        "confidence": 0.8,
        "ambiguity_flags": [],
        "needs_clarification": False,
        "is_active": True,
        "user_confirmed": True,
        "has_conflict": False,
        "conflict_accepted": False,
    }


def test_persist_schedule_skips_invalid_day_of_week_block() -> None:
    service = ScheduleService(repository=InMemoryScheduleRepository())
    valid = _block()
    invalid = _bad_block(day_of_week="Inglés")

    result = service.persist_schedule(
        student_id=7,
        occupation="solo_estudio",
        timezone="America/Bogota",
        summary_text="test",
        blocks=[valid, invalid],
        conflicts=[],
        conflicts_accepted=False,
    )

    assert result.persisted is True
    assert result.block_count == 1
    assert len(result.invalid_blocks) == 1
    assert "inglés" in result.invalid_blocks[0].lower()


def test_persist_schedule_returns_no_valid_blocks_when_all_invalid() -> None:
    service = ScheduleService(repository=InMemoryScheduleRepository())

    result = service.persist_schedule(
        student_id=7,
        occupation="solo_estudio",
        timezone="America/Bogota",
        summary_text="test",
        blocks=[_bad_block("Inglés"), _bad_block("Física")],
        conflicts=[],
        conflicts_accepted=False,
    )

    assert result.persisted is False
    assert result.error_code == "no_valid_blocks"
    assert len(result.invalid_blocks) == 2


class _StubScheduleServicePartialSave:
    """Simula un servicio que persiste con bloques inválidos omitidos."""

    def persist_schedule(self, **kwargs):
        from services.scheduling.service import PersistScheduleResult
        return PersistScheduleResult(
            persisted=True,
            schedule_profile_id=1,
            block_count=1,
            invalid_blocks=("'Inglés' 10:00-12:00 (día no reconocido: 'inglés')",),
        )


class _StubScheduleServiceAllInvalid:
    """Simula un servicio que no puede persistir ningún bloque."""

    def persist_schedule(self, **kwargs):
        from services.scheduling.service import PersistScheduleResult
        return PersistScheduleResult(
            persisted=False,
            error_code="no_valid_blocks",
            invalid_blocks=("'Inglés' 10:00-12:00 (día no reconocido: 'inglés')",),
        )


def test_persist_schedule_node_shows_friendly_partial_save_message() -> None:
    set_schedule_service(_StubScheduleServicePartialSave())
    try:
        state = AgentState(
            phase="schedule_persist",
            student_profile={"persisted_student_id": 15, "occupation": "solo_estudio"},
            schedule={
                "blocks": [_block()],
                "summary_text": "test",
                "conflicts": [],
            },
        )

        update = persist_schedule(state)

        assert update["phase"] == "schedule_sync"
        msg = update["messages"][0].content.lower()
        assert "guardado" in msg
        assert "omití" in msg or "omiti" in msg
    finally:
        set_schedule_service(None)


def test_persist_schedule_node_shows_friendly_message_when_all_blocks_invalid() -> None:
    set_schedule_service(_StubScheduleServiceAllInvalid())
    try:
        state = AgentState(
            phase="schedule_persist",
            student_profile={"persisted_student_id": 15, "occupation": "solo_estudio"},
            schedule={
                "blocks": [_block()],
                "summary_text": "test",
                "conflicts": [],
            },
        )

        update = persist_schedule(state)

        assert update["phase"] == "end"
        msg = update["messages"][0].content.lower()
        assert "detalle técnico" not in msg
        assert "no_valid_blocks" not in msg
        assert "formato" in msg or "válido" in msg or "valido" in msg
    finally:
        set_schedule_service(None)


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
