"""Pruebas del dominio de tracking de sesiones de estudio."""

from __future__ import annotations

from datetime import datetime as real_datetime

import agents.support.planning.materialization_service as materialization_module
from agents.support.planning.instances_repository import InMemoryStudyPlanInstancesRepository
from agents.support.planning.materialization_service import StudyPlanMaterializationService
from agents.support.planning.tracking_repository import InMemoryStudySessionTrackingRepository
from agents.support.planning.tracking_service import StudySessionTrackingService
from agents.support.state import Event


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


def _materialized_instance_payload():
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
    return instances_repository, instance_payload


def test_tracking_service_records_start_complete_and_feedback(monkeypatch) -> None:
    monkeypatch.setattr(materialization_module, "datetime", _FrozenDateTime)
    instances_repository, instance_payload = _materialized_instance_payload()
    tracking_repository = InMemoryStudySessionTrackingRepository(
        instances_repository=instances_repository
    )
    service = StudySessionTrackingService(repository=tracking_repository)

    started = service.start_session(
        student_id=7,
        study_plan_event_instance_id=int(instance_payload["id"]),
        reported_at=instance_payload["starts_at"],
        actual_start_at=instance_payload["starts_at"],
    )
    completed = service.complete_session(
        student_id=7,
        study_plan_event_instance_id=int(instance_payload["id"]),
        reported_at=instance_payload["ends_at"],
        actual_start_at=instance_payload["starts_at"],
        actual_end_at=instance_payload["ends_at"],
        completion_pct=85,
        comprehension_score=4,
        energy_score=3,
        notes="Buen avance",
    )
    feedback = service.record_feedback(
        student_id=7,
        study_plan_event_instance_id=int(instance_payload["id"]),
        notes="Necesito repasar derivadas",
        comprehension_score=3,
    )

    assert started.tracked is True
    assert started.resulting_status == "in_progress"
    assert completed.tracked is True
    assert completed.resulting_status == "completed"
    assert feedback.tracked is True
    assert feedback.resulting_status == "completed"
    assert instance_payload["status"] == "completed"
    assert instance_payload["completion_pct"] == 85
    assert len(tracking_repository._checkins_by_id) == 3
    latest = tracking_repository._checkins_by_id[feedback.checkin_id]
    assert latest["checkin_type"] == "feedback"
    assert latest["comprehension_score"] == 3


def test_tracking_service_can_skip_scheduled_session(monkeypatch) -> None:
    monkeypatch.setattr(materialization_module, "datetime", _FrozenDateTime)
    instances_repository, instance_payload = _materialized_instance_payload()
    tracking_repository = InMemoryStudySessionTrackingRepository(
        instances_repository=instances_repository
    )
    service = StudySessionTrackingService(repository=tracking_repository)

    skipped = service.skip_session(
        student_id=7,
        study_plan_event_instance_id=int(instance_payload["id"]),
        notes="Choque con otra actividad",
    )

    assert skipped.tracked is True
    assert skipped.resulting_status == "skipped"
    assert instance_payload["status"] == "skipped"
    assert instance_payload["completion_pct"] == 0
    checkin = tracking_repository._checkins_by_id[skipped.checkin_id]
    assert checkin["checkin_type"] == "skip"
    assert checkin["notes"] == "Choque con otra actividad"
