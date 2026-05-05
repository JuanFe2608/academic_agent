"""Pruebas del servicio de recordatorios y del runner de dispatches."""

from __future__ import annotations

from datetime import datetime as real_datetime

import services.planning.materialization_service as materialization_module
import services.reminders.service as reminders_module
from integrations.whatsapp import WhatsAppClientError, WhatsAppMessageSend
from repositories.planning.instances_repository import InMemoryStudyPlanInstancesRepository
from repositories.reminders.repository import (
    InMemoryRemindersRepository,
    LeasedReminderDispatch,
    ReminderDispatchSeed,
)
from schemas.planning import AcademicActivity
from schemas.scheduling import Event
from services.channels import WhatsAppChannelService
from services.planning import StudyPlanMaterializationService
from services.reminders import (
    ReminderDispatchRunner,
    StudyPlanRemindersService,
    WhatsAppReminderSender,
    render_whatsapp_reminder_message,
)


class _FrozenDateTime(real_datetime):
    @classmethod
    def now(cls, tz=None):
        base = real_datetime(2026, 1, 5, 8, 0)
        if tz is not None:
            return base.replace(tzinfo=tz)
        return base


class _StaticRecipientResolver:
    def __init__(self, recipient_id: str | None) -> None:
        self.recipient_id = recipient_id

    def recipient_for(self, dispatch) -> str | None:
        return self.recipient_id


class _FakeWhatsAppClient:
    def __init__(self) -> None:
        self.texts: list[tuple[str, str]] = []

    def send_text(self, to: str, text: str) -> WhatsAppMessageSend:
        self.texts.append((to, text))
        return WhatsAppMessageSend(message_id=f"wamid.{len(self.texts)}", raw_payload={})


class _FailingWhatsAppClient:
    def __init__(self, *, status_code: int | None = 500) -> None:
        self.status_code = status_code
        self.calls = 0

    def send_text(self, to: str, text: str) -> WhatsAppMessageSend:
        self.calls += 1
        raise WhatsAppClientError(
            "WhatsApp temporalmente no disponible.",
            status_code=self.status_code,
        )


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
    assert first.created_dispatch_count == 4
    assert first.canceled_dispatch_count == 0
    assert second.created_dispatch_count == 0
    assert len(reminders_repository._dispatches_by_id) == 4
    assert {
        row["dispatch_type"] for row in reminders_repository._dispatches_by_id.values()
    } == {
        "pre_session_60m",
        "pre_session_10m",
        "followup_15m",
        "missed_session_30m",
    }
    assert {row["status"] for row in reminders_repository._dispatches_by_id.values()} == {
        "pending"
    }


def test_reminders_service_schedules_academic_activity_dispatches(monkeypatch) -> None:
    monkeypatch.setattr(reminders_module, "datetime", _FrozenDateTime)
    reminders_repository = InMemoryRemindersRepository()
    reminders_service = StudyPlanRemindersService(repository=reminders_repository)

    result = reminders_service.sync_reminders_for_academic_activities(
        student_id=7,
        activities=[
            AcademicActivity(
                activity_id="act-parcial-calculo",
                activity_type="parcial",
                subject_name="Calculo",
                activity_title="Parcial 1",
                due_date="2026-01-06",
                due_time="12:00",
                priority_level="alta",
            )
        ],
        reminders_state={"enabled": True, "policy": {"channels": ["in_app"]}},
        timezone="America/Bogota",
    )

    assert result.synced is True
    assert result.policy_count == 5
    assert result.schedulable_instance_count == 1
    assert result.created_dispatch_count == 5
    assert result.canceled_dispatch_count == 0
    assert len(reminders_repository._dispatches_by_id) == 5
    dispatch_types = {
        row["dispatch_type"] for row in reminders_repository._dispatches_by_id.values()
    }
    assert "daily_agenda_2026-01-06" in dispatch_types
    assert any(item.startswith("activity_due_180m_") for item in dispatch_types)
    assert any(item.startswith("activity_due_60m_") for item in dispatch_types)
    assert any(item.startswith("activity_due_15m_") for item in dispatch_types)
    assert any(item.startswith("activity_overdue_15m_") for item in dispatch_types)
    assert {
        row["payload"]["reminder_domain"]
        for row in reminders_repository._dispatches_by_id.values()
    } == {"academic_activity"}


def test_reminders_service_cancels_activity_dispatches_when_completed(monkeypatch) -> None:
    monkeypatch.setattr(reminders_module, "datetime", _FrozenDateTime)
    reminders_repository = InMemoryRemindersRepository()
    reminders_service = StudyPlanRemindersService(repository=reminders_repository)
    activity = AcademicActivity(
        activity_id="act-tarea-fisica",
        activity_type="tarea",
        subject_name="Fisica",
        activity_title="Tarea de laboratorio",
        due_date="2026-01-06",
        due_time="12:00",
    )

    first = reminders_service.sync_reminders_for_academic_activities(
        student_id=7,
        activities=[activity],
        reminders_state={"enabled": True, "policy": {"channels": ["in_app"]}},
        timezone="America/Bogota",
    )
    second = reminders_service.sync_reminders_for_academic_activities(
        student_id=7,
        activities=[activity.model_copy(update={"status": "completed"})],
        reminders_state={"enabled": True, "policy": {"channels": ["in_app"]}},
        timezone="America/Bogota",
    )

    assert first.created_dispatch_count == 5
    assert second.created_dispatch_count == 0
    assert second.canceled_dispatch_count == 5
    assert {
        row["status"] for row in reminders_repository._dispatches_by_id.values()
    } == {"canceled"}


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
    assert second_sync.canceled_dispatch_count == 4
    canceled = [
        payload
        for payload in reminders_repository._dispatches_by_id.values()
        if payload["status"] == "canceled"
    ]
    assert len(canceled) == 4


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
    assert result.channel_counts == {"in_app": 1, "email": 1}
    assert result.dispatch_type_counts == {
        "pre_session_60m": 1,
        "pre_session_10m": 1,
    }
    statuses = {row["channel"]: row["status"] for row in repository._dispatches_by_id.values()}
    assert statuses == {"in_app": "sent", "email": "failed"}


def test_due_reminder_runner_sends_whatsapp_and_avoids_duplicate_dispatch() -> None:
    repository = InMemoryRemindersRepository()
    scheduled_for = real_datetime(2026, 1, 5, 7, 30)
    repository.sync_dispatches(
        dispatches=[
            ReminderDispatchSeed(
                student_id=1,
                reminder_policy_id=3,
                study_plan_event_instance_id=11,
                dispatch_type="pre_session_60m",
                channel="whatsapp",
                scheduled_for=scheduled_for,
                payload={
                    "title": "Calculo",
                    "reminder_type": "pre_session",
                    "lead_minutes": 60,
                    "starts_at": "2026-01-05T08:30:00-05:00",
                    "ends_at": "2026-01-05T09:20:00-05:00",
                    "timezone": "America/Bogota",
                },
            )
        ]
    )
    client = _FakeWhatsAppClient()
    sender = WhatsAppReminderSender(
        channel_service=WhatsAppChannelService(client),  # type: ignore[arg-type]
        recipient_resolver=_StaticRecipientResolver("573001112233"),
    )
    runner = ReminderDispatchRunner(
        repository=repository,
        whatsapp_sender=sender,
    )

    result = runner.run_due_dispatches(
        as_of=real_datetime(2026, 1, 5, 8, 0),
        limit=10,
    )
    second = runner.run_due_dispatches(
        as_of=real_datetime(2026, 1, 5, 8, 0),
        limit=10,
    )

    assert result.processed is True
    assert result.leased_count == 1
    assert result.sent_count == 1
    assert result.failed_count == 0
    assert result.retryable_count == 0
    assert second.leased_count == 0
    assert client.texts == [
        (
            "573001112233",
            "Recordatorio de estudio\n"
            "Sesion: Calculo\n"
            "Inicio: 2026-01-05 08:30\n"
            "Faltan 1 hora.\n"
            "Prepara el material y protege este bloque.",
        )
    ]
    row = next(iter(repository._dispatches_by_id.values()))
    assert row["status"] == "sent"
    assert row["provider_message_id"] == "wamid.1"


def test_due_reminder_runner_can_filter_by_channel() -> None:
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
                dispatch_type="pre_session_60m",
                channel="whatsapp",
                scheduled_for=scheduled_for,
                payload={"title": "Calculo"},
            ),
        ]
    )
    runner = ReminderDispatchRunner(repository=repository)

    result = runner.run_due_dispatches(
        as_of=real_datetime(2026, 1, 5, 8, 0),
        limit=10,
        channels={"whatsapp"},
    )

    assert result.leased_count == 1
    assert result.channel_counts == {"whatsapp": 1}
    statuses = {
        row["channel"]: row["status"]
        for row in repository._dispatches_by_id.values()
    }
    assert statuses == {"in_app": "pending", "whatsapp": "failed"}


def test_whatsapp_renderer_handles_activity_due_and_overdue_messages() -> None:
    due_dispatch = LeasedReminderDispatch(
        id=1,
        student_id=7,
        reminder_policy_id=1,
        study_plan_event_instance_id=None,
        dispatch_type="activity_due_180m_act",
        channel="whatsapp",
        scheduled_for=real_datetime(2026, 1, 6, 9, 0),
        payload={
            "kind": "activity_due",
            "reminder_type": "activity_due",
            "title": "Parcial 1",
            "lead_minutes": 180,
            "due_at": "2026-01-06T12:00:00-05:00",
            "starts_at": "2026-01-06T12:00:00-05:00",
            "timezone": "America/Bogota",
        },
    )
    overdue_dispatch = LeasedReminderDispatch(
        id=2,
        student_id=7,
        reminder_policy_id=2,
        study_plan_event_instance_id=None,
        dispatch_type="activity_overdue_15m_act",
        channel="whatsapp",
        scheduled_for=real_datetime(2026, 1, 6, 12, 15),
        payload={
            "kind": "activity_overdue",
            "reminder_type": "activity_overdue",
            "title": "Parcial 1",
            "lead_minutes": 15,
            "due_at": "2026-01-06T12:00:00-05:00",
            "starts_at": "2026-01-06T12:00:00-05:00",
            "timezone": "America/Bogota",
        },
    )

    due_message = render_whatsapp_reminder_message(due_dispatch)
    overdue_message = render_whatsapp_reminder_message(overdue_dispatch)

    assert "Recordatorio de actividad academica" in due_message
    assert "Faltan 3 horas." in due_message
    assert "Seguimiento de actividad vencida" in overdue_message
    assert "¿La completaste?" in overdue_message
    assert "complete Parcial 1" in overdue_message


def test_due_reminder_runner_retries_retryable_whatsapp_failures() -> None:
    repository = InMemoryRemindersRepository()
    scheduled_for = real_datetime(2026, 1, 5, 7, 30)
    repository.sync_dispatches(
        dispatches=[
            ReminderDispatchSeed(
                student_id=1,
                reminder_policy_id=3,
                study_plan_event_instance_id=11,
                dispatch_type="followup_15m",
                channel="whatsapp",
                scheduled_for=scheduled_for,
                payload={
                    "title": "Calculo",
                    "reminder_type": "followup",
                    "starts_at": "2026-01-05T08:30:00-05:00",
                    "ends_at": "2026-01-05T09:20:00-05:00",
                    "timezone": "America/Bogota",
                },
            )
        ]
    )
    client = _FailingWhatsAppClient(status_code=500)
    sender = WhatsAppReminderSender(
        channel_service=WhatsAppChannelService(client),  # type: ignore[arg-type]
        recipient_resolver=_StaticRecipientResolver("573001112233"),
    )
    runner = ReminderDispatchRunner(
        repository=repository,
        whatsapp_sender=sender,
        max_attempts=2,
        retry_delay_minutes=15,
    )

    first = runner.run_due_dispatches(
        as_of=real_datetime(2026, 1, 5, 8, 0),
        limit=10,
    )
    immediate_retry = runner.run_due_dispatches(
        as_of=real_datetime(2026, 1, 5, 8, 0),
        limit=10,
    )
    final = runner.run_due_dispatches(
        as_of=real_datetime(2026, 1, 5, 8, 15),
        limit=10,
    )

    row = next(iter(repository._dispatches_by_id.values()))
    assert first.retryable_count == 1
    assert first.failed_count == 0
    assert immediate_retry.leased_count == 0
    assert final.failed_count == 1
    assert final.retryable_count == 0
    assert client.calls == 2
    assert row["status"] == "failed"
    assert row["failure_reason"] == "whatsapp_send_error"
    assert row["attempt_count"] == 2


def test_due_reminder_runner_logs_sent_dispatch(caplog) -> None:
    import logging

    repository = InMemoryRemindersRepository()
    scheduled_for = real_datetime(2026, 1, 5, 7, 30)
    repository.sync_dispatches(
        dispatches=[
            ReminderDispatchSeed(
                student_id=5,
                reminder_policy_id=1,
                study_plan_event_instance_id=10,
                dispatch_type="pre_session_60m",
                channel="in_app",
                scheduled_for=scheduled_for,
                payload={"title": "Calculo"},
            )
        ]
    )
    runner = ReminderDispatchRunner(repository=repository)

    with caplog.at_level(logging.INFO, logger="services.reminders.dispatcher"):
        runner.run_due_dispatches(as_of=real_datetime(2026, 1, 5, 8, 0), limit=10)

    messages = [r.message for r in caplog.records]
    sent_logs = [m for m in messages if "reminder_dispatch_sent" in m]
    assert len(sent_logs) == 1
    assert "student_id=5" in sent_logs[0]
    assert "channel=in_app" in sent_logs[0]
    assert "dispatch_type=pre_session_60m" in sent_logs[0]


def test_due_reminder_runner_logs_failed_dispatch(caplog) -> None:
    import logging

    repository = InMemoryRemindersRepository()
    scheduled_for = real_datetime(2026, 1, 5, 7, 30)
    repository.sync_dispatches(
        dispatches=[
            ReminderDispatchSeed(
                student_id=5,
                reminder_policy_id=2,
                study_plan_event_instance_id=10,
                dispatch_type="pre_session_10m",
                channel="email",
                scheduled_for=scheduled_for,
                payload={"title": "Calculo"},
            )
        ]
    )
    runner = ReminderDispatchRunner(repository=repository)

    with caplog.at_level(logging.WARNING, logger="services.reminders.dispatcher"):
        runner.run_due_dispatches(as_of=real_datetime(2026, 1, 5, 8, 0), limit=10)

    messages = [r.message for r in caplog.records]
    failed_logs = [m for m in messages if "reminder_dispatch_failed" in m]
    assert len(failed_logs) == 1
    assert "student_id=5" in failed_logs[0]
    assert "channel=email" in failed_logs[0]
    assert "error_code=" in failed_logs[0]


def test_due_reminder_runner_logs_retryable_dispatch(caplog) -> None:
    import logging

    repository = InMemoryRemindersRepository()
    scheduled_for = real_datetime(2026, 1, 5, 7, 30)
    repository.sync_dispatches(
        dispatches=[
            ReminderDispatchSeed(
                student_id=5,
                reminder_policy_id=3,
                study_plan_event_instance_id=10,
                dispatch_type="followup_15m",
                channel="whatsapp",
                scheduled_for=scheduled_for,
                payload={"title": "Calculo"},
            )
        ]
    )
    client = _FailingWhatsAppClient(status_code=500)
    sender = WhatsAppReminderSender(
        channel_service=WhatsAppChannelService(client),  # type: ignore[arg-type]
        recipient_resolver=_StaticRecipientResolver("573001112233"),
    )
    runner = ReminderDispatchRunner(
        repository=repository,
        whatsapp_sender=sender,
        max_attempts=3,
        retry_delay_minutes=15,
    )

    with caplog.at_level(logging.WARNING, logger="services.reminders.dispatcher"):
        runner.run_due_dispatches(as_of=real_datetime(2026, 1, 5, 8, 0), limit=10)

    messages = [r.message for r in caplog.records]
    retryable_logs = [m for m in messages if "reminder_dispatch_retryable" in m]
    assert len(retryable_logs) == 1
    assert "student_id=5" in retryable_logs[0]
    assert "channel=whatsapp" in retryable_logs[0]
    assert "retry_at=" in retryable_logs[0]


def test_due_reminder_runner_logs_batch_summary(caplog) -> None:
    import logging

    repository = InMemoryRemindersRepository()
    scheduled_for = real_datetime(2026, 1, 5, 7, 30)
    repository.sync_dispatches(
        dispatches=[
            ReminderDispatchSeed(
                student_id=5,
                reminder_policy_id=1,
                study_plan_event_instance_id=10,
                dispatch_type="pre_session_60m",
                channel="in_app",
                scheduled_for=scheduled_for,
                payload={"title": "Calculo"},
            ),
            ReminderDispatchSeed(
                student_id=5,
                reminder_policy_id=2,
                study_plan_event_instance_id=10,
                dispatch_type="pre_session_10m",
                channel="email",
                scheduled_for=scheduled_for,
                payload={"title": "Calculo"},
            ),
        ]
    )
    runner = ReminderDispatchRunner(repository=repository)

    with caplog.at_level(logging.INFO, logger="services.reminders.dispatcher"):
        runner.run_due_dispatches(as_of=real_datetime(2026, 1, 5, 8, 0), limit=10)

    messages = [r.message for r in caplog.records]
    start_logs = [m for m in messages if "reminder_dispatch_batch_start" in m]
    done_logs = [m for m in messages if "reminder_dispatch_batch_done" in m]
    assert len(start_logs) == 1
    assert "leased=2" in start_logs[0]
    assert len(done_logs) == 1
    assert "sent=1" in done_logs[0]
    assert "failed=1" in done_logs[0]
