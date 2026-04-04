"""Pruebas del proceso batch para marcar sesiones perdidas."""

from __future__ import annotations

from datetime import datetime as real_datetime

import services.planning.materialization_service as materialization_module
from repositories.planning.instances_repository import InMemoryStudyPlanInstancesRepository
from repositories.planning.tracking_repository import InMemoryStudySessionTrackingRepository
from schemas.scheduling import Event
from services.planning import StudyPlanMaterializationService, StudySessionTrackingService


class _FrozenDateTime(real_datetime):
    @classmethod
    def now(cls, tz=None):
        base = real_datetime(2026, 1, 5, 8, 0)
        if tz is not None:
            return base.replace(tzinfo=tz)
        return base


def _study_event(day: str, title: str, source_id: str) -> Event:
    return Event(
        id=source_id,
        dia=day,
        inicio="18:00",
        fin="18:25",
        titulo=title,
        tipo="tentativo",
        categoria="estudio",
        origen="study_planner",
        prioridad="alta",
        dificultad=4,
        timezone="America/Bogota",
    )


def test_mark_due_sessions_missed_is_idempotent(monkeypatch) -> None:
    monkeypatch.setattr(materialization_module, "datetime", _FrozenDateTime)
    instances_repository = InMemoryStudyPlanInstancesRepository()
    materialization_service = StudyPlanMaterializationService(
        repository=instances_repository,
        horizon_days=7,
    )
    materialization_service.materialize_plan_instances(
        student_id=7,
        study_plan_profile_id=31,
        study_plan={
            "plan_events": [_study_event("Lunes", "Estudio Calculo", "evt-calculo")],
            "rules": {"planner_version": "study_planner_v1", "status": "generated"},
        },
        timezone="America/Bogota",
    )
    instance_payload = next(iter(instances_repository._instances_by_key.values()))
    tracking_repository = InMemoryStudySessionTrackingRepository(
        instances_repository=instances_repository
    )
    service = StudySessionTrackingService(repository=tracking_repository)

    first = service.mark_due_sessions_missed(
        student_id=7,
        as_of="2026-01-05T19:00:00-05:00",
        grace_minutes=30,
        limit=10,
    )
    second = service.mark_due_sessions_missed(
        student_id=7,
        as_of="2026-01-05T19:00:00-05:00",
        grace_minutes=30,
        limit=10,
    )

    assert first.processed is True
    assert first.marked_count == 1
    assert first.instance_ids == [int(instance_payload["id"])]
    assert second.processed is True
    assert second.marked_count == 0
    assert instance_payload["status"] == "missed"
    assert instance_payload["completion_pct"] == 0
    assert len(tracking_repository._checkins_by_id) == 1
    checkin = next(iter(tracking_repository._checkins_by_id.values()))
    assert checkin["checkin_type"] == "missed_confirmation"
    assert checkin["actor_type"] == "system"
