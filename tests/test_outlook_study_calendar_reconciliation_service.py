"""Pruebas de reconciliación de sesiones de estudio contra Outlook."""

from __future__ import annotations

from datetime import datetime as real_datetime

from integrations.microsoft_graph.auth_client import (
    MicrosoftGraphStateTokenStore,
    MicrosoftOAuthClient,
    MicrosoftOAuthConfig,
)
from integrations.microsoft_graph.models import OutlookCalendarEventSnapshot
import services.planning.materialization_service as materialization_module
from repositories.microsoft_graph.state_repository import (
    InMemoryMicrosoftGraphStateRepository,
    OutlookCalendarEventLinkRecord,
)
from repositories.microsoft_graph.sync_repository import InMemoryMicrosoftGraphSyncRepository
from repositories.planning.instances_repository import InMemoryStudyPlanInstancesRepository
from schemas.scheduling import Event
from services.planning import StudyPlanMaterializationService
from services.sync.outlook_study_calendar_reconciliation_service import (
    OutlookStudyCalendarReconciliationService,
)


class _FrozenDateTime(real_datetime):
    @classmethod
    def now(cls, tz=None):
        base = real_datetime(2026, 1, 5, 8, 0)
        if tz is not None:
            return base.replace(tzinfo=tz)
        return base


class _FakeOutlookCalendarClient:
    def __init__(self, snapshots: dict[str, OutlookCalendarEventSnapshot | None]) -> None:
        self.snapshots = snapshots

    def get_event(
        self,
        *,
        access_token: str,
        calendar_id: str | None,
        external_event_id: str,
    ) -> OutlookCalendarEventSnapshot | None:
        assert access_token.startswith("access-token")
        assert calendar_id == "calendar-1"
        return self.snapshots.get(external_event_id)


def _study_event() -> Event:
    return Event(
        id="study-1",
        dia="Lunes",
        inicio="18:00",
        fin="18:25",
        titulo="Estudio Calculo",
        tipo="tentativo",
        categoria="estudio",
        origen="study_planner",
        prioridad="alta",
        dificultad=4,
        timezone="America/Bogota",
    )


def _oauth_client(state_repository: InMemoryMicrosoftGraphStateRepository) -> MicrosoftOAuthClient:
    client = MicrosoftOAuthClient(
        config=MicrosoftOAuthConfig(
            client_id="client-123",
            tenant_id="tenant-456",
            redirect_uri="https://example.com/oauth/callback",
        ),
        token_store=MicrosoftGraphStateTokenStore(state_repository),
    )
    client.save_manual_token(
        student_id=7,
        access_token="access-token-1234567890",
        refresh_token="refresh-token-1234567890",
        expires_in_seconds=3600,
        calendar_id="calendar-1",
        email="student@example.edu",
    )
    return client


def _materialized_repository(monkeypatch):
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
            "plan_events": [_study_event()],
            "rules": {"planner_version": "study_planner_v1", "status": "generated"},
        },
        timezone="America/Bogota",
    )
    return instances_repository


def _link_first_instance(
    instances_repository: InMemoryStudyPlanInstancesRepository,
    state_repository: InMemoryMicrosoftGraphStateRepository,
) -> dict:
    instance_payload = next(iter(instances_repository._instances_by_key.values()))
    state_repository.upsert_calendar_event_links(
        links=[
            OutlookCalendarEventLinkRecord(
                student_id=7,
                study_plan_event_instance_id=int(instance_payload["id"]),
                source_instance_key=instance_payload["source_instance_key"],
                calendar_id="calendar-1",
                external_event_id="outlook:study-1",
                external_change_key="ck:original",
            )
        ]
    )
    return instance_payload


def test_study_calendar_reconciliation_marks_aligned_sessions(monkeypatch) -> None:
    instances_repository = _materialized_repository(monkeypatch)
    state_repository = InMemoryMicrosoftGraphStateRepository()
    _link_first_instance(instances_repository, state_repository)
    service = OutlookStudyCalendarReconciliationService(
        repository=InMemoryMicrosoftGraphSyncRepository(instances_repository=instances_repository),
        state_repository=state_repository,
        auth_client=_oauth_client(state_repository),
        client=_FakeOutlookCalendarClient(
            {
                "outlook:study-1": OutlookCalendarEventSnapshot(
                    external_event_id="outlook:study-1",
                    subject="Estudio Calculo",
                    start={"dateTime": "2026-01-05T23:00:00Z", "timeZone": "UTC"},
                    end={"dateTime": "2026-01-05T23:25:00Z", "timeZone": "UTC"},
                    external_change_key="ck:original",
                )
            }
        ),
    )

    result = service.reconcile_student_calendar(
        student_id=7,
        calendar_id="calendar-1",
        study_plan_profile_id=31,
    )

    assert result.reconciled is True
    assert result.aligned_count == 1
    assert result.drifted_count == 0
    assert result.findings[0].status == "active"


def test_study_calendar_reconciliation_detects_manual_drift(monkeypatch) -> None:
    instances_repository = _materialized_repository(monkeypatch)
    state_repository = InMemoryMicrosoftGraphStateRepository()
    _link_first_instance(instances_repository, state_repository)
    service = OutlookStudyCalendarReconciliationService(
        repository=InMemoryMicrosoftGraphSyncRepository(instances_repository=instances_repository),
        state_repository=state_repository,
        auth_client=_oauth_client(state_repository),
        client=_FakeOutlookCalendarClient(
            {
                "outlook:study-1": OutlookCalendarEventSnapshot(
                    external_event_id="outlook:study-1",
                    subject="Estudio Calculo editado",
                    start={"dateTime": "2026-01-06T00:00:00Z", "timeZone": "UTC"},
                    end={"dateTime": "2026-01-06T00:30:00Z", "timeZone": "UTC"},
                    external_change_key="ck:manual",
                    web_link="https://outlook.office.com/calendar/item/1",
                )
            }
        ),
    )

    result = service.reconcile_student_calendar(
        student_id=7,
        calendar_id="calendar-1",
        study_plan_profile_id=31,
    )

    links = state_repository.list_calendar_event_links(student_id=7, calendar_id="calendar-1")
    assert result.reconciled is True
    assert result.drifted_count == 1
    assert result.findings[0].status == "drifted"
    assert "subject" in result.findings[0].drift_fields
    assert "start" in result.findings[0].drift_fields
    assert links[0].sync_status == "active"
    assert links[0].last_error == "manual_drift:subject,start,end,external_change_key"


def test_study_calendar_reconciliation_detects_missing_outlook_event(monkeypatch) -> None:
    instances_repository = _materialized_repository(monkeypatch)
    state_repository = InMemoryMicrosoftGraphStateRepository()
    _link_first_instance(instances_repository, state_repository)
    service = OutlookStudyCalendarReconciliationService(
        repository=InMemoryMicrosoftGraphSyncRepository(instances_repository=instances_repository),
        state_repository=state_repository,
        auth_client=_oauth_client(state_repository),
        client=_FakeOutlookCalendarClient({"outlook:study-1": None}),
    )

    result = service.reconcile_student_calendar(
        student_id=7,
        calendar_id="calendar-1",
        study_plan_profile_id=31,
    )

    links = state_repository.list_calendar_event_links(student_id=7, calendar_id="calendar-1")
    assert result.reconciled is True
    assert result.missing_count == 1
    assert result.findings[0].status == "missing"
    assert links[0].sync_status == "active"
    assert links[0].last_error == "manual_missing"
