"""Pruebas del dominio de tracking de sesiones de estudio."""

from __future__ import annotations

from datetime import datetime as real_datetime

import services.planning.materialization_service as materialization_module
from repositories.planning.instances_repository import InMemoryStudyPlanInstancesRepository
from repositories.planning.tracking_repository import InMemoryStudySessionTrackingRepository
from schemas.scheduling import Event
from services.planning import (
    StudyPlanMaterializationService,
    StudySessionTrackingService,
    apply_study_session_tracking_text,
)


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


def test_conversational_tracking_completes_session_by_subject(monkeypatch) -> None:
    monkeypatch.setattr(materialization_module, "datetime", _FrozenDateTime)
    instances_repository, instance_payload = _materialized_instance_payload()
    tracking_repository = InMemoryStudySessionTrackingRepository(
        instances_repository=instances_repository
    )
    service = StudySessionTrackingService(repository=tracking_repository)

    result = apply_study_session_tracking_text(
        "Ya termine la sesion de calculo",
        student_id=7,
        tracking_service=service,
        timezone="America/Bogota",
        as_of=real_datetime.fromisoformat("2026-01-05T19:00:00-05:00"),
    )

    assert result.detected is True
    assert result.applied is True
    assert result.action == "complete"
    assert result.instance_id == int(instance_payload["id"])
    assert result.resulting_status == "completed"
    assert instance_payload["status"] == "completed"
    checkin = next(iter(tracking_repository._checkins_by_id.values()))
    assert checkin["checkin_type"] == "complete"
    assert checkin["completion_pct"] == 100


def test_conversational_tracking_marks_missed_session_for_replan(monkeypatch) -> None:
    monkeypatch.setattr(materialization_module, "datetime", _FrozenDateTime)
    instances_repository, instance_payload = _materialized_instance_payload()
    tracking_repository = InMemoryStudySessionTrackingRepository(
        instances_repository=instances_repository
    )
    service = StudySessionTrackingService(repository=tracking_repository)

    result = apply_study_session_tracking_text(
        "No pude estudiar hoy",
        student_id=7,
        tracking_service=service,
        timezone="America/Bogota",
        as_of=real_datetime.fromisoformat("2026-01-05T19:00:00-05:00"),
    )

    assert result.detected is True
    assert result.applied is True
    assert result.action == "missed"
    assert result.replan_required is True
    assert result.replan_payload["trigger"] == "missed_study_session"
    assert result.replan_payload["study_plan_event_instance_id"] == int(instance_payload["id"])
    assert instance_payload["status"] == "missed"
    checkin = next(iter(tracking_repository._checkins_by_id.values()))
    assert checkin["checkin_type"] == "missed_confirmation"
    assert checkin["actor_type"] == "student"
