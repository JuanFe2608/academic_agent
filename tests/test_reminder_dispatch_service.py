"""Pruebas del servicio de recordatorios y del runner de dispatches."""

from __future__ import annotations

from datetime import datetime as real_datetime

import services.planning.materialization_service as materialization_module
import services.reminders.service as reminders_module
from repositories.planning.instances_repository import InMemoryStudyPlanInstancesRepository
from repositories.reminders.repository import (
    InMemoryRemindersRepository,
    ReminderDispatchSeed,
)
from schemas.scheduling import Event
from services.planning import StudyPlanMaterializationService
from services.reminders import ReminderDispatchRunner, StudyPlanRemindersService


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


def test_reminders_service_persists_default_policies_and_dispatches(monkeypatch) -> None:
    monkeypatch.setattr(materialization_module, "datetime", _FrozenDateTime)
    monkeypatch.setattr(reminders_module, "datetime", _FrozenDateTime)
    instances_repository = InMemoryStudyPlanInstancesRepository()
    materialization_service = StudyPlanMaterializationService(
        repository=instances_repository,
        horizon_days=7,
    )
    reminders_repository = InMemoryRemindersRepository(
        instances_repository=instances_repository
    )
    reminders_service = StudyPlanRemindersService(repository=reminders_repository)

    materialization_service.materialize_plan_instances(
        student_id=7,
        study_plan_profile_id=31,
        study_plan={
            "plan_events": [_study_event("Lunes", "Estudio Calculo", "evt-calculo")],
            "rules": {"planner_version": "study_planner_v1", "status": "generated"},
        },
        timezone="America/Bogota",
    )

    first = reminders_service.sync_reminders_for_study_plan(
        student_id=7,
        study_plan_profile_id=31,
        reminders_state={"enabled": True, "policy": {}},
        timezone="America/Bogota",
    )
    second = reminders_service.sync_reminders_for_study_plan(
        student_id=7,
        study_plan_profile_id=31,
        reminders_state={"enabled": True, "policy": {}},
        timezone="America/Bogota",
    )

    assert first.synced is True
    assert first.policy_count == 4
    assert len(first.persisted_policy_ids) == 4
    assert first.schedulable_instance_count == 1
    assert first.created_dispatch_count == 3
    assert first.canceled_dispatch_count == 0
    assert second.created_dispatch_count == 0
    assert len(reminders_repository._dispatches_by_id) == 3


def test_reminders_service_cancels_pending_dispatches_for_superseded_instances(
    monkeypatch,
) -> None:
    monkeypatch.setattr(materialization_module, "datetime", _FrozenDateTime)
    monkeypatch.setattr(reminders_module, "datetime", _FrozenDateTime)
    instances_repository = InMemoryStudyPlanInstancesRepository()
    materialization_service = StudyPlanMaterializationService(
        repository=instances_repository,
        horizon_days=7,
    )
    reminders_repository = InMemoryRemindersRepository(
        instances_repository=instances_repository
    )
    reminders_service = StudyPlanRemindersService(repository=reminders_repository)

    materialization_service.materialize_plan_instances(
        student_id=9,
        study_plan_profile_id=101,
        study_plan={
            "plan_events": [_study_event("Lunes", "Estudio Calculo", "evt-calculo")],
            "rules": {"planner_version": "study_planner_v1", "status": "generated"},
        },
        timezone="America/Bogota",
    )
    reminders_service.sync_reminders_for_study_plan(
        student_id=9,
        study_plan_profile_id=101,
        reminders_state={"enabled": True, "policy": {}},
        timezone="America/Bogota",
    )

    materialization_service.materialize_plan_instances(
        student_id=9,
        study_plan_profile_id=102,
        study_plan={
            "plan_events": [_study_event("Miercoles", "Estudio Progra", "evt-progra")],
            "rules": {"planner_version": "study_planner_v1", "status": "generated"},
        },
        timezone="America/Bogota",
    )
    second_sync = reminders_service.sync_reminders_for_study_plan(
        student_id=9,
        study_plan_profile_id=102,
        reminders_state={"enabled": True, "policy": {}},
        timezone="America/Bogota",
    )

    assert second_sync.synced is True
    assert second_sync.canceled_dispatch_count == 3
    canceled = [
        payload
        for payload in reminders_repository._dispatches_by_id.values()
        if payload["status"] == "canceled"
    ]
    assert len(canceled) == 3


def test_due_reminder_runner_marks_sent_and_failed() -> None:
    repository = InMemoryRemindersRepository()
    scheduled_for = real_datetime(2026, 1, 5, 7, 30)
    repository.sync_dispatches(
        dispatches=[
            ReminderDispatchSeed(
                student_id=1,
                reminder_policy_id=1,
                study_plan_event_instance_id=11,
                dispatch_type="pre_session_60m",
                channel="in_app",
                scheduled_for=scheduled_for,
                payload={"title": "Calculo"},
            ),
            ReminderDispatchSeed(
                student_id=1,
                reminder_policy_id=2,
                study_plan_event_instance_id=11,
                dispatch_type="pre_session_10m",
                channel="email",
                scheduled_for=scheduled_for,
                payload={"title": "Calculo"},
            ),
        ]
    )

    runner = ReminderDispatchRunner(repository=repository)
    result = runner.run_due_dispatches(
        as_of=real_datetime(2026, 1, 5, 8, 0),
        limit=10,
    )

    assert result.processed is True
    assert result.leased_count == 2
    assert result.sent_count == 1
    assert result.failed_count == 1
    statuses = {row["channel"]: row["status"] for row in repository._dispatches_by_id.values()}
    assert statuses == {"in_app": "sent", "email": "failed"}
