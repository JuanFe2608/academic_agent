"""Pruebas del sync durable hacia Microsoft To Do."""

from __future__ import annotations

from datetime import datetime as real_datetime

from integrations.microsoft_graph.auth_client import (
    MicrosoftGraphStateTokenStore,
    MicrosoftOAuthClient,
    MicrosoftOAuthConfig,
)
from integrations.microsoft_graph.models import (
    MicrosoftTodoTaskList,
    MicrosoftTodoTaskUpsert,
    UpsertedMicrosoftTodoTask,
)
import services.planning.materialization_service as materialization_module
from repositories.microsoft_graph.state_repository import (
    InMemoryMicrosoftGraphStateRepository,
)
from repositories.microsoft_graph.sync_repository import (
    InMemoryMicrosoftGraphSyncRepository,
)
from repositories.planning.instances_repository import InMemoryStudyPlanInstancesRepository
from repositories.planning.tracking_repository import InMemoryStudySessionTrackingRepository
from schemas.scheduling import Event
from services.planning import StudyPlanMaterializationService, StudySessionTrackingService
from services.sync.microsoft_todo_sync_service import MicrosoftTodoSyncService


class _FrozenDateTime(real_datetime):
    @classmethod
    def now(cls, tz=None):
        base = real_datetime(2026, 1, 5, 8, 0)
        if tz is not None:
            return base.replace(tzinfo=tz)
        return base


class _FakeMicrosoftTodoClient:
    def __init__(
        self,
        *,
        task_lists: list[MicrosoftTodoTaskList] | None = None,
        expected_task_list_id: str = "todo-list-1",
    ) -> None:
        self.upserts: list[MicrosoftTodoTaskUpsert] = []
        self.deletes: list[str] = []
        self.task_lists = list(task_lists or [])
        self.expected_task_list_id = expected_task_list_id

    def list_task_lists(
        self,
        *,
        access_token: str,
    ) -> list[MicrosoftTodoTaskList]:
        assert access_token.startswith("access-token")
        return list(self.task_lists)

    def upsert_tasks(
        self,
        *,
        access_token: str,
        task_list_id: str,
        tasks: list[MicrosoftTodoTaskUpsert],
    ) -> list[UpsertedMicrosoftTodoTask]:
        assert access_token.startswith("access-token")
        assert task_list_id == self.expected_task_list_id
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
        assert task_list_id == self.expected_task_list_id
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


def _oauth_client_without_task_list(
    state_repository: InMemoryMicrosoftGraphStateRepository,
) -> MicrosoftOAuthClient:
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
        email="student@example.edu",
    )
    return client


def test_microsoft_todo_sync_service_projects_missed_sessions(monkeypatch) -> None:
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

    state_repository = InMemoryMicrosoftGraphStateRepository()
    client = _FakeMicrosoftTodoClient()
    service = MicrosoftTodoSyncService(
        repository=InMemoryMicrosoftGraphSyncRepository(
            instances_repository=instances_repository
        ),
        state_repository=state_repository,
        auth_client=_oauth_client(state_repository),
        client=client,
    )
    result = service.sync_actionable_sessions(
        student_id=7,
        task_list_id="todo-list-1",
        study_plan_profile_id=31,
    )

    persisted_links = state_repository.list_todo_task_links(
        student_id=7,
        task_list_id="todo-list-1",
    )
    assert result.synced is True
    assert result.upserted_count == 1
    assert result.deleted_count == 0
    assert len(client.upserts) == 1
    assert client.upserts[0].title.startswith("Reprogramar:")
    assert result.synced_task_map
    assert len(persisted_links) == 1
    assert persisted_links[0].external_task_id.startswith("todo:")


def test_microsoft_todo_sync_preview_does_not_call_upsert(monkeypatch) -> None:
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

    state_repository = InMemoryMicrosoftGraphStateRepository()
    client = _FakeMicrosoftTodoClient()
    service = MicrosoftTodoSyncService(
        repository=InMemoryMicrosoftGraphSyncRepository(
            instances_repository=instances_repository
        ),
        state_repository=state_repository,
        auth_client=_oauth_client(state_repository),
        client=client,
    )

    preview = service.preview_actionable_sessions(
        student_id=7,
        task_list_id="todo-list-1",
        study_plan_profile_id=31,
    )

    assert preview.previewed is True
    assert preview.create_count == 1
    assert preview.update_count == 0
    assert preview.delete_count == 0
    assert preview.actionable_count == 1
    assert client.upserts == []
    assert client.deletes == []


def test_microsoft_todo_sync_service_deletes_tasks_when_session_is_resolved(
    monkeypatch,
) -> None:
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

    state_repository = InMemoryMicrosoftGraphStateRepository()
    client = _FakeMicrosoftTodoClient()
    service = MicrosoftTodoSyncService(
        repository=InMemoryMicrosoftGraphSyncRepository(
            instances_repository=instances_repository
        ),
        state_repository=state_repository,
        auth_client=_oauth_client(state_repository),
        client=client,
    )

    first_result = service.sync_actionable_sessions(
        student_id=7,
        task_list_id="todo-list-1",
        study_plan_profile_id=31,
    )
    for payload in instances_repository._instances_by_key.values():
        payload["status"] = "completed"

    second_result = service.sync_actionable_sessions(
        student_id=7,
        task_list_id="todo-list-1",
        study_plan_profile_id=31,
    )

    assert first_result.upserted_count == 1
    assert second_result.synced is True
    assert second_result.upserted_count == 0
    assert second_result.deleted_count == 1
    assert len(client.deletes) == 1
    assert state_repository.list_todo_task_links(
        student_id=7,
        task_list_id="todo-list-1",
    ) == []


def test_microsoft_todo_sync_service_persists_default_task_list_when_missing(
    monkeypatch,
) -> None:
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

    state_repository = InMemoryMicrosoftGraphStateRepository()
    client = _FakeMicrosoftTodoClient(
        task_lists=[
            MicrosoftTodoTaskList(
                id="default-list-id",
                display_name="Tasks",
                wellknown_list_name="defaultList",
            ),
            MicrosoftTodoTaskList(
                id="secondary-list-id",
                display_name="Academic Agent",
            ),
        ],
        expected_task_list_id="default-list-id",
    )
    service = MicrosoftTodoSyncService(
        repository=InMemoryMicrosoftGraphSyncRepository(
            instances_repository=instances_repository
        ),
        state_repository=state_repository,
        auth_client=_oauth_client_without_task_list(state_repository),
        client=client,
    )

    result = service.sync_actionable_sessions(
        student_id=7,
        task_list_id=None,
        study_plan_profile_id=31,
    )

    persisted_connection = state_repository.get_connection(student_id=7)
    persisted_links = state_repository.list_todo_task_links(
        student_id=7,
        task_list_id="default-list-id",
    )
    assert result.synced is True
    assert result.upserted_count == 1
    assert persisted_connection is not None
    assert persisted_connection.todo_task_list_id == "default-list-id"
    assert len(persisted_links) == 1
