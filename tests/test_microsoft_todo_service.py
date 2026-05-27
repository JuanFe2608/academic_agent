"""Pruebas del sync durable hacia Microsoft To Do."""

from __future__ import annotations

from datetime import datetime as real_datetime, timezone

from integrations.microsoft_graph.auth_client import (
    MicrosoftGraphStateTokenStore,
    MicrosoftOAuthClient,
    MicrosoftOAuthConfig,
)
from integrations.microsoft_graph.models import (
    MicrosoftTodoTaskList,
    MicrosoftTodoTaskSnapshot,
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
from schemas.planning import AcademicActivity
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
        tasks: list[MicrosoftTodoTaskSnapshot] | None = None,
        expected_task_list_id: str = "todo-list-1",
    ) -> None:
        self.upserts: list[MicrosoftTodoTaskUpsert] = []
        self.deletes: list[str] = []
        self.listed_task_lists = 0
        self.listed_tasks = 0
        self.task_lists = list(task_lists or [])
        self.tasks = list(tasks or [])
        self.expected_task_list_id = expected_task_list_id

    def list_task_lists(
        self,
        *,
        access_token: str,
    ) -> list[MicrosoftTodoTaskList]:
        assert access_token.startswith("access-token")
        self.listed_task_lists += 1
        return list(self.task_lists)

    def list_tasks(
        self,
        *,
        access_token: str,
        task_list_id: str,
    ) -> list[MicrosoftTodoTaskSnapshot]:
        assert access_token.startswith("access-token")
        assert task_list_id == self.expected_task_list_id
        self.listed_tasks += 1
        return list(self.tasks)

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


def test_microsoft_todo_activity_sync_updates_completed_and_deletes_removed() -> None:
    state_repository = InMemoryMicrosoftGraphStateRepository()
    client = _FakeMicrosoftTodoClient()
    service = MicrosoftTodoSyncService(
        repository=InMemoryMicrosoftGraphSyncRepository(),
        state_repository=state_repository,
        auth_client=_oauth_client(state_repository),
        client=client,
    )
    activities = [
        AcademicActivity(
            activity_id="act-pending",
            activity_type="parcial",
            subject_name="Calculo",
            activity_title="Parcial 1",
            due_date="2026-05-01",
            priority_level="alta",
            status="pending",
        ),
        AcademicActivity(
            activity_id="act-completed",
            activity_type="tarea",
            subject_name="Fisica",
            activity_title="Tarea 1",
            due_date="2026-05-02",
            status="completed",
            todo_task_id="todo-existing-completed",
        ),
        AcademicActivity(
            activity_id="act-deleted",
            activity_type="quiz",
            subject_name="Programacion",
            activity_title="Quiz 1",
            due_date="2026-05-03",
            status="deleted",
            todo_task_id="todo-existing-deleted",
        ),
    ]

    result = service.sync_academic_activities_to_todo(
        student_id=7,
        task_list_id="todo-list-1",
        activities=activities,
    )

    assert result.synced is True
    assert result.upserted_count == 2
    assert result.deleted_count == 1
    assert len(client.upserts) == 2
    assert any(task.is_completed for task in client.upserts)
    assert any(task.existing_external_task_id == "todo-existing-completed" for task in client.upserts)
    assert client.deletes == ["todo-existing-deleted"]

    updated_by_id = {activity.activity_id: activity for activity in result.synced_activities}
    assert updated_by_id["act-pending"].todo_task_id == "todo:act-pending"
    assert updated_by_id["act-completed"].todo_task_id == "todo:act-completed"
    assert updated_by_id["act-deleted"].todo_task_id is None


def test_microsoft_todo_activity_sync_imports_completed_task_before_upsert() -> None:
    state_repository = InMemoryMicrosoftGraphStateRepository()
    activity = AcademicActivity(
        activity_id="act-fisica",
        activity_type="tarea",
        subject_name="Fisica",
        activity_title="Tarea 1",
        due_date="2026-05-02",
        status="pending",
        todo_task_id="todo-act-fisica",
    )
    client = _FakeMicrosoftTodoClient(
        tasks=[
            MicrosoftTodoTaskSnapshot(
                external_task_id="todo-act-fisica",
                title="[tarea] Fisica: Tarea 1",
                due_at=real_datetime(2026, 5, 2, 23, 59, tzinfo=timezone.utc),
                is_completed=True,
            )
        ]
    )
    service = MicrosoftTodoSyncService(
        repository=InMemoryMicrosoftGraphSyncRepository(),
        state_repository=state_repository,
        auth_client=_oauth_client(state_repository),
        client=client,
    )

    result = service.sync_academic_activities_to_todo(
        student_id=7,
        task_list_id="todo-list-1",
        activities=[activity],
    )

    assert result.synced is True
    assert result.imported_completed_count == 1
    assert result.synced_activities[0].status == "completed"
    assert client.listed_tasks == 1
    assert client.upserts[0].is_completed is True


def test_microsoft_todo_activity_sync_blocks_manual_title_or_due_change() -> None:
    state_repository = InMemoryMicrosoftGraphStateRepository()
    activity = AcademicActivity(
        activity_id="act-proyecto",
        activity_type="proyecto",
        subject_name="Bases",
        activity_title="Entrega final",
        due_date="2026-05-10",
        status="pending",
        todo_task_id="todo-act-proyecto",
    )
    client = _FakeMicrosoftTodoClient(
        tasks=[
            MicrosoftTodoTaskSnapshot(
                external_task_id="todo-act-proyecto",
                title="[proyecto] Bases: Entrega ajustada",
                due_at=real_datetime(2026, 5, 12, 23, 59, tzinfo=timezone.utc),
            )
        ]
    )
    service = MicrosoftTodoSyncService(
        repository=InMemoryMicrosoftGraphSyncRepository(),
        state_repository=state_repository,
        auth_client=_oauth_client(state_repository),
        client=client,
    )

    result = service.sync_academic_activities_to_todo(
        student_id=7,
        task_list_id="todo-list-1",
        activities=[activity],
    )

    assert result.synced is False
    assert result.requires_confirmation is True
    assert result.error_code == "microsoft_todo_manual_changes_detected"
    assert result.inbound_change_count == 1
    assert set(result.inbound_changes[0]["changed_fields"]) == {"title", "due_date"}
    assert result.synced_activities[0].activity_title == "Entrega final"
    assert result.synced_activities[0].due_date == "2026-05-10"
    assert client.upserts == []
    assert client.deletes == []


def test_microsoft_todo_activity_sync_imports_manual_changes_when_confirmed() -> None:
    state_repository = InMemoryMicrosoftGraphStateRepository()
    activity = AcademicActivity(
        activity_id="act-proyecto",
        activity_type="proyecto",
        subject_name="Bases",
        activity_title="Entrega final",
        due_date="2026-05-10",
        status="pending",
        todo_task_id="todo-act-proyecto",
    )
    client = _FakeMicrosoftTodoClient(
        tasks=[
            MicrosoftTodoTaskSnapshot(
                external_task_id="todo-act-proyecto",
                title="[proyecto] Bases: Entrega ajustada",
                due_at=real_datetime(2026, 5, 12, 23, 59, tzinfo=timezone.utc),
            )
        ]
    )
    service = MicrosoftTodoSyncService(
        repository=InMemoryMicrosoftGraphSyncRepository(),
        state_repository=state_repository,
        auth_client=_oauth_client(state_repository),
        client=client,
    )

    result = service.sync_academic_activities_to_todo(
        student_id=7,
        task_list_id="todo-list-1",
        activities=[activity],
        import_manual_todo_changes=True,
    )

    assert result.synced is True
    assert result.inbound_change_count == 1
    assert result.synced_activities[0].activity_title == "Entrega ajustada"
    assert result.synced_activities[0].due_date == "2026-05-12"
    assert client.upserts[0].title == "[proyecto] Bases: Entrega ajustada"


def test_microsoft_todo_activity_sync_restores_assistant_task_when_requested() -> None:
    state_repository = InMemoryMicrosoftGraphStateRepository()
    activity = AcademicActivity(
        activity_id="act-proyecto",
        activity_type="proyecto",
        subject_name="Bases",
        activity_title="Entrega final",
        due_date="2026-05-10",
        status="pending",
        todo_task_id="todo-act-proyecto",
    )
    client = _FakeMicrosoftTodoClient(
        tasks=[
            MicrosoftTodoTaskSnapshot(
                external_task_id="todo-act-proyecto",
                title="[proyecto] Bases: Entrega ajustada",
                due_at=real_datetime(2026, 5, 12, 23, 59, tzinfo=timezone.utc),
            )
        ]
    )
    service = MicrosoftTodoSyncService(
        repository=InMemoryMicrosoftGraphSyncRepository(),
        state_repository=state_repository,
        auth_client=_oauth_client(state_repository),
        client=client,
    )

    result = service.sync_academic_activities_to_todo(
        student_id=7,
        task_list_id="todo-list-1",
        activities=[activity],
        restore_manual_todo_changes=True,
    )

    assert result.synced is True
    assert result.inbound_change_count == 1
    assert result.synced_activities[0].activity_title == "Entrega final"
    assert result.synced_activities[0].due_date == "2026-05-10"
    assert client.upserts[0].title == "[proyecto] Bases: Entrega final"
