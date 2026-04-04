"""Pruebas de persistencia del horario recurrente."""

from __future__ import annotations

from agents.support.dependencies import set_schedule_service
from agents.support.nodes.persist_schedule.node import persist_schedule
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
            schedule={"blocks": [_block()], "summary_text": "resumen", "conflicts": []},
        )

        update = persist_schedule(state)

        assert update["phase"] == "sync"
        assert update["schedule"]["persisted_profile_id"] == 1
        assert "guardado correctamente" in update["messages"][0].content.lower()
    finally:
        set_schedule_service(None)
