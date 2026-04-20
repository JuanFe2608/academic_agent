"""Cobertura del flujo confirmable de sync de pendientes con Microsoft To Do."""

from __future__ import annotations

from datetime import datetime as real_datetime

from langchain_core.messages import HumanMessage

import services.planning.materialization_service as materialization_module
from agents.support.agent import _route_welcome
from agents.support.dependencies import set_microsoft_todo_sync_service
from agents.support.nodes.sync_study_todo import sync_study_todo
from agents.support.state import AgentState
from integrations.microsoft_graph.auth_client import (
    MicrosoftGraphStateTokenStore,
    MicrosoftOAuthClient,
    MicrosoftOAuthConfig,
)
from integrations.microsoft_graph.models import (
    MicrosoftTodoTaskUpsert,
    UpsertedMicrosoftTodoTask,
)
from repositories.microsoft_graph.state_repository import InMemoryMicrosoftGraphStateRepository
from repositories.microsoft_graph.sync_repository import InMemoryMicrosoftGraphSyncRepository
from repositories.planning.instances_repository import InMemoryStudyPlanInstancesRepository
from repositories.planning.tracking_repository import InMemoryStudySessionTrackingRepository
from schemas.scheduling import Event
from services.planning import StudyPlanMaterializationService, StudySessionTrackingService
from services.sync import MicrosoftTodoSyncService


class _FrozenDateTime(real_datetime):
    @classmethod
    def now(cls, tz=None):
        base = real_datetime(2026, 1, 5, 8, 0)
        if tz is not None:
            return base.replace(tzinfo=tz)
        return base


class _FakeMicrosoftTodoClient:
    def __init__(self) -> None:
        self.upserts: list[MicrosoftTodoTaskUpsert] = []
        self.deletes: list[str] = []

    def list_task_lists(self, *, access_token: str):
        assert access_token.startswith("access-token")
        return []

    def upsert_tasks(
        self,
        *,
        access_token: str,
        task_list_id: str,
        tasks: list[MicrosoftTodoTaskUpsert],
    ) -> list[UpsertedMicrosoftTodoTask]:
        assert access_token.startswith("access-token")
        assert task_list_id == "todo-list-1"
        self.upserts.extend(tasks)
        return [
            UpsertedMicrosoftTodoTask(
                external_key=task.external_key,
                external_task_id=f"todo:{task.external_key}",
            )
            for task in tasks
        ]

    def delete_tasks(
        self,
        *,
        access_token: str,
        task_list_id: str,
        external_task_ids: list[str],
    ) -> list[str]:
        assert access_token.startswith("access-token")
        assert task_list_id == "todo-list-1"
        self.deletes.extend(external_task_ids)
        return list(external_task_ids)


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
        todo_task_list_id="todo-list-1",
        email="student@example.edu",
    )
    return client


def _state() -> AgentState:
    return AgentState(
        phase="end",
        awaiting_user_input=False,
        user_message_count=0,
        student_profile={"persisted_student_id": 7},
        study_plan={
            "plan_events": [_study_event("Lunes", "Estudio Calculo", "evt-calculo")],
            "rules": {"planner_version": "study_planner_v1", "status": "generated"},
            "persisted_profile_id": 31,
            "version_number": 1,
        },
        messages=[HumanMessage(content="Sincroniza mis pendientes de estudio con Microsoft To Do")],
    )


def _next_state(state: AgentState, update: dict, user_text: str) -> AgentState:
    payload = state.model_dump(mode="python")
    payload.update({key: value for key, value in update.items() if key != "messages"})
    payload["messages"] = list(state.messages) + list(update.get("messages") or []) + [
        HumanMessage(content=user_text)
    ]
    return AgentState(**payload)


def _instances_with_missed_session(monkeypatch):
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
    tracking_service = StudySessionTrackingService(
        repository=InMemoryStudySessionTrackingRepository(
            instances_repository=instances_repository
        )
    )
    tracking_service.mark_due_sessions_missed(
        student_id=7,
        as_of="2026-01-05T19:00:00-05:00",
        grace_minutes=30,
    )
    return instances_repository


def test_study_todo_sync_requires_confirmation_before_graph_calls(monkeypatch) -> None:
    instances_repository = _instances_with_missed_session(monkeypatch)
    state_repository = InMemoryMicrosoftGraphStateRepository()
    fake_client = _FakeMicrosoftTodoClient()
    sync_service = MicrosoftTodoSyncService(
        repository=InMemoryMicrosoftGraphSyncRepository(
            instances_repository=instances_repository
        ),
        state_repository=state_repository,
        auth_client=_oauth_client(state_repository),
        client=fake_client,
    )
    set_microsoft_todo_sync_service(sync_service)
    state = _state()

    try:
        assert _route_welcome(state) == "sync_study_todo"
        preview_update = sync_study_todo(state)
        assert fake_client.upserts == []

        confirmation_state = _next_state(state, preview_update, "si")
        final_update = sync_study_todo(confirmation_state)
    finally:
        set_microsoft_todo_sync_service(None)

    links = state_repository.list_todo_task_links(student_id=7, task_list_id="todo-list-1")
    assert preview_update["phase"] == "todo_sync"
    assert preview_update["awaiting_user_input"] is True
    assert preview_update["interaction"]["confirmation_pending"] is True
    assert preview_update["interaction"]["last_confirmation_payload"]["preview"]["create_count"] == 1
    assert "Confirmas que sincronice Microsoft To Do" in preview_update["messages"][0].content
    assert final_update["phase"] == "end"
    assert final_update["awaiting_user_input"] is False
    assert len(fake_client.upserts) == 1
    assert len(links) == 1
    assert final_update["study_plan"]["rules"]["todo_sync"]["status"] == "synced"
    assert final_update["study_plan"]["rules"]["external_sync_status_by_target"]["microsoft_todo"] == "synced"


def test_study_todo_sync_rejection_does_not_call_graph(monkeypatch) -> None:
    instances_repository = _instances_with_missed_session(monkeypatch)
    state_repository = InMemoryMicrosoftGraphStateRepository()
    fake_client = _FakeMicrosoftTodoClient()
    sync_service = MicrosoftTodoSyncService(
        repository=InMemoryMicrosoftGraphSyncRepository(
            instances_repository=instances_repository
        ),
        state_repository=state_repository,
        auth_client=_oauth_client(state_repository),
        client=fake_client,
    )
    set_microsoft_todo_sync_service(sync_service)
    state = _state()

    try:
        preview_update = sync_study_todo(state)
        rejection_state = _next_state(state, preview_update, "no")
        final_update = sync_study_todo(rejection_state)
    finally:
        set_microsoft_todo_sync_service(None)

    assert final_update["phase"] == "end"
    assert final_update["study_plan"]["rules"]["todo_sync"]["status"] == "rejected"
    assert fake_client.upserts == []
    assert state_repository.list_todo_task_links(student_id=7, task_list_id="todo-list-1") == []


def test_study_todo_sync_missing_oauth_is_non_destructive(monkeypatch) -> None:
    instances_repository = _instances_with_missed_session(monkeypatch)
    state_repository = InMemoryMicrosoftGraphStateRepository()
    fake_client = _FakeMicrosoftTodoClient()
    auth_client = MicrosoftOAuthClient(
        config=MicrosoftOAuthConfig(
            client_id="client-123",
            tenant_id="tenant-456",
            redirect_uri="https://example.com/oauth/callback",
        ),
        token_store=MicrosoftGraphStateTokenStore(state_repository),
    )
    sync_service = MicrosoftTodoSyncService(
        repository=InMemoryMicrosoftGraphSyncRepository(
            instances_repository=instances_repository
        ),
        state_repository=state_repository,
        auth_client=auth_client,
        client=fake_client,
    )
    set_microsoft_todo_sync_service(sync_service)

    try:
        update = sync_study_todo(_state())
    finally:
        set_microsoft_todo_sync_service(None)

    assert update["phase"] == "end"
    assert update["awaiting_user_input"] is False
    assert "conectes Microsoft 365" in update["messages"][0].content
    assert update["study_plan"]["rules"]["todo_sync"]["status"] == "blocked_oauth"
    assert fake_client.upserts == []
