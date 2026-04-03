"""Pruebas del sync durable hacia Outlook Calendar."""

from __future__ import annotations

from datetime import datetime as real_datetime

import agents.support.planning.materialization_service as materialization_module
from auth.microsoft_auth import MicrosoftGraphStateTokenStore, MicrosoftOAuthClient, MicrosoftOAuthConfig
from agents.support.planning.instances_repository import InMemoryStudyPlanInstancesRepository
from agents.support.planning.materialization_service import StudyPlanMaterializationService
from agents.support.state import Event
from agents.support.tools.calendar_outlook import OutlookCalendarSyncService
from agents.support.tools.microsoft_graph_clients import (
    OutlookCalendarEventUpsert,
    UpsertedOutlookCalendarEvent,
)
from agents.support.tools.microsoft_graph_state_repository import (
    InMemoryMicrosoftGraphStateRepository,
    OutlookCalendarEventLinkRecord,
)
from agents.support.tools.microsoft_graph_sync_repository import (
    InMemoryMicrosoftGraphSyncRepository,
)


class _FrozenDateTime(real_datetime):
    @classmethod
    def now(cls, tz=None):
        base = real_datetime(2026, 1, 5, 8, 0)
        if tz is not None:
            return base.replace(tzinfo=tz)
        return base


class _FakeOutlookCalendarClient:
    def __init__(self) -> None:
        self.upserts: list[OutlookCalendarEventUpsert] = []
        self.deletes: list[str] = []

    def upsert_events(
        self,
        *,
        access_token: str,
        calendar_id: str | None,
        events: list[OutlookCalendarEventUpsert],
    ) -> list[UpsertedOutlookCalendarEvent]:
        assert access_token.startswith("access-token")
        assert calendar_id == "calendar-1"
        self.upserts.extend(events)
        return [
            UpsertedOutlookCalendarEvent(
                external_key=event.external_key,
                external_event_id=f"outlook:{event.external_key}",
                external_change_key=f"ck:{event.external_key}",
            )
            for event in events
        ]

    def delete_events(
        self,
        *,
        access_token: str,
        calendar_id: str | None,
        external_event_ids: list[str],
    ) -> list[str]:
        assert access_token.startswith("access-token")
        assert calendar_id == "calendar-1"
        self.deletes.extend(external_event_ids)
        return list(external_event_ids)


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


def test_outlook_calendar_sync_service_upserts_materialized_instances(monkeypatch) -> None:
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

    state_repository = InMemoryMicrosoftGraphStateRepository()
    client = _FakeOutlookCalendarClient()
    service = OutlookCalendarSyncService(
        repository=InMemoryMicrosoftGraphSyncRepository(
            instances_repository=instances_repository
        ),
        state_repository=state_repository,
        auth_client=_oauth_client(state_repository),
        client=client,
    )
    result = service.sync_student_calendar(
        student_id=7,
        calendar_id="calendar-1",
        study_plan_profile_id=31,
    )

    persisted_links = state_repository.list_calendar_event_links(
        student_id=7,
        calendar_id="calendar-1",
    )
    assert result.synced is True
    assert result.upserted_count == 1
    assert result.deleted_count == 0
    assert len(client.upserts) == 1
    assert client.upserts[0].subject == "Estudio Calculo"
    assert result.synced_event_map
    assert len(persisted_links) == 1
    assert persisted_links[0].external_event_id.startswith("outlook:")


def test_outlook_calendar_sync_service_deletes_superseded_instances(monkeypatch) -> None:
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
    state_repository = InMemoryMicrosoftGraphStateRepository()
    auth_client = _oauth_client(state_repository)
    state_repository.upsert_calendar_event_links(
        links=[
            OutlookCalendarEventLinkRecord(
                student_id=7,
                study_plan_event_instance_id=int(instance_payload["id"]),
                source_instance_key=instance_payload["source_instance_key"],
                calendar_id="calendar-1",
                external_event_id="outlook:old-event",
                external_change_key="ck:old",
            )
        ]
    )
    instance_payload["status"] = "superseded"

    client = _FakeOutlookCalendarClient()
    service = OutlookCalendarSyncService(
        repository=InMemoryMicrosoftGraphSyncRepository(
            instances_repository=instances_repository
        ),
        state_repository=state_repository,
        auth_client=auth_client,
        client=client,
    )
    result = service.sync_student_calendar(
        student_id=7,
        calendar_id="calendar-1",
        study_plan_profile_id=31,
    )

    assert result.synced is True
    assert result.upserted_count == 0
    assert result.deleted_count == 1
    assert client.deletes == ["outlook:old-event"]
    assert result.synced_event_map == {}
