"""Cobertura del flujo confirmable de sync de sesiones con Outlook."""

from __future__ import annotations

from datetime import datetime as real_datetime

from langchain_core.messages import HumanMessage

import services.planning.materialization_service as materialization_module
from agents.support.agent import _route_entry
from agents.support.dependencies import (
    set_outlook_calendar_sync_service,
    set_study_plan_materialization_service,
)
from agents.support.nodes.sync_study_calendar import sync_study_calendar
from agents.support.state import AgentState
from integrations.microsoft_graph.auth_client import (
    MicrosoftGraphStateTokenStore,
    MicrosoftOAuthClient,
    MicrosoftOAuthConfig,
)
from integrations.microsoft_graph.models import (
    OutlookCalendarEventUpsert,
    UpsertedOutlookCalendarEvent,
)
from repositories.microsoft_graph.state_repository import InMemoryMicrosoftGraphStateRepository
from repositories.microsoft_graph.sync_repository import InMemoryMicrosoftGraphSyncRepository
from repositories.planning.instances_repository import InMemoryStudyPlanInstancesRepository
from schemas.scheduling import Event
from services.planning import StudyPlanMaterializationService
from services.sync import OutlookCalendarSyncService


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


def _state() -> AgentState:
    return AgentState(
        phase="end",
        awaiting_user_input=False,
        user_message_count=0,
        student_profile={"persisted_student_id": 7},
        calendar={"provider": "outlook", "authorized": True, "calendar_id": "calendar-1"},
        study_plan={
            "plan_events": [_study_event("Lunes", "Estudio Calculo", "evt-calculo")],
            "rules": {"planner_version": "study_planner_v1", "status": "generated"},
            "persisted_profile_id": 31,
            "version_number": 1,
        },
        messages=[HumanMessage(content="Sincroniza mis sesiones de estudio con Outlook")],
    )


def _next_state(state: AgentState, update: dict, user_text: str) -> AgentState:
    payload = state.model_dump(mode="python")
    payload.update({key: value for key, value in update.items() if key != "messages"})
    payload["messages"] = list(state.messages) + list(update.get("messages") or []) + [
        HumanMessage(content=user_text)
    ]
    return AgentState(**payload)


def test_study_calendar_sync_requires_confirmation_before_outlook_calls(monkeypatch) -> None:
    monkeypatch.setattr(materialization_module, "datetime", _FrozenDateTime)
    instances_repository = InMemoryStudyPlanInstancesRepository()
    materialization_service = StudyPlanMaterializationService(
        repository=instances_repository,
        horizon_days=7,
    )
    state_repository = InMemoryMicrosoftGraphStateRepository()
    fake_client = _FakeOutlookCalendarClient()
    sync_service = OutlookCalendarSyncService(
        repository=InMemoryMicrosoftGraphSyncRepository(
            instances_repository=instances_repository
        ),
        state_repository=state_repository,
        auth_client=_oauth_client(state_repository),
        client=fake_client,
    )
    set_study_plan_materialization_service(materialization_service)
    set_outlook_calendar_sync_service(sync_service)
    state = _state()

    try:
        assert _route_entry(state) == "sync_study_calendar"
        preview_update = sync_study_calendar(state)
        assert fake_client.upserts == []

        confirmation_state = _next_state(state, preview_update, "si")
        final_update = sync_study_calendar(confirmation_state)
    finally:
        set_study_plan_materialization_service(None)
        set_outlook_calendar_sync_service(None)

    links = state_repository.list_calendar_event_links(student_id=7, calendar_id="calendar-1")
    assert preview_update["phase"] == "running"
    assert preview_update["awaiting_user_input"] is True
    assert preview_update["interaction"]["confirmation_pending"] is True
    assert preview_update["interaction"]["last_confirmation_payload"]["preview"]["create_count"] == 1
    assert "Confirmas que sincronice Outlook" in preview_update["messages"][0].content
    assert final_update["phase"] == "end"
    assert final_update["awaiting_user_input"] is False
    assert len(fake_client.upserts) == 1
    assert len(links) == 1
    assert final_update["calendar"]["authorized"] is True
    assert final_update["calendar"]["synced_event_map"]
    assert final_update["study_plan"]["rules"]["external_sync_status"] == "synced"


def test_study_calendar_sync_rejection_does_not_call_outlook(monkeypatch) -> None:
    monkeypatch.setattr(materialization_module, "datetime", _FrozenDateTime)
    instances_repository = InMemoryStudyPlanInstancesRepository()
    materialization_service = StudyPlanMaterializationService(
        repository=instances_repository,
        horizon_days=7,
    )
    state_repository = InMemoryMicrosoftGraphStateRepository()
    fake_client = _FakeOutlookCalendarClient()
    sync_service = OutlookCalendarSyncService(
        repository=InMemoryMicrosoftGraphSyncRepository(
            instances_repository=instances_repository
        ),
        state_repository=state_repository,
        auth_client=_oauth_client(state_repository),
        client=fake_client,
    )
    set_study_plan_materialization_service(materialization_service)
    set_outlook_calendar_sync_service(sync_service)
    state = _state()

    try:
        preview_update = sync_study_calendar(state)
        rejection_state = _next_state(state, preview_update, "no")
        final_update = sync_study_calendar(rejection_state)
    finally:
        set_study_plan_materialization_service(None)
        set_outlook_calendar_sync_service(None)

    assert final_update["phase"] == "end"
    assert final_update["study_plan"]["rules"]["external_sync_status"] == "rejected"
    assert fake_client.upserts == []
    assert state_repository.list_calendar_event_links(student_id=7, calendar_id="calendar-1") == []


def test_study_calendar_sync_missing_oauth_is_non_destructive(monkeypatch) -> None:
    monkeypatch.setattr(materialization_module, "datetime", _FrozenDateTime)
    instances_repository = InMemoryStudyPlanInstancesRepository()
    materialization_service = StudyPlanMaterializationService(
        repository=instances_repository,
        horizon_days=7,
    )
    state_repository = InMemoryMicrosoftGraphStateRepository()
    fake_client = _FakeOutlookCalendarClient()
    auth_client = MicrosoftOAuthClient(
        config=MicrosoftOAuthConfig(
            client_id="client-123",
            tenant_id="tenant-456",
            redirect_uri="https://example.com/oauth/callback",
        ),
        token_store=MicrosoftGraphStateTokenStore(state_repository),
    )
    sync_service = OutlookCalendarSyncService(
        repository=InMemoryMicrosoftGraphSyncRepository(
            instances_repository=instances_repository
        ),
        state_repository=state_repository,
        auth_client=auth_client,
        client=fake_client,
    )
    set_study_plan_materialization_service(materialization_service)
    set_outlook_calendar_sync_service(sync_service)

    try:
        update = sync_study_calendar(_state())
    finally:
        set_study_plan_materialization_service(None)
        set_outlook_calendar_sync_service(None)

    assert update["phase"] == "end"
    assert update["awaiting_user_input"] is False
    assert "conectes Microsoft 365" in update["messages"][0].content
    assert update["study_plan"]["rules"]["external_sync_status"] == "blocked_oauth"
    assert fake_client.upserts == []
