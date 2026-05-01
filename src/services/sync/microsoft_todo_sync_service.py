"""Proyección durable de sesiones accionables hacia Microsoft To Do."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from integrations.microsoft_graph.auth_client import (
    MicrosoftGraphStateTokenStore,
    MicrosoftOAuthClient,
    build_microsoft_oauth_client_from_env,
)
from bootstrap.errors import RepositoryConfigurationError
from bootstrap.settings import database_url_from_env

from integrations.microsoft_graph.models import (
    MicrosoftGraphClientError,
    MicrosoftTodoClient,
    MicrosoftTodoTaskList,
    MicrosoftTodoTaskUpsert,
)
from integrations.microsoft_graph.todo_client import GraphMicrosoftTodoClient
from repositories.microsoft_graph.state_repository import (
    InMemoryMicrosoftGraphStateRepository,
    MicrosoftGraphConnectionRecord,
    MicrosoftGraphStateRepository,
    MicrosoftGraphStateRepositoryError,
    MicrosoftTodoTaskLinkRecord,
    build_microsoft_graph_state_repository,
)
from repositories.microsoft_graph.sync_repository import (
    InMemoryMicrosoftGraphSyncRepository,
    MicrosoftGraphSyncRepository,
    MicrosoftGraphSyncRepositoryError,
    MicrosoftSyncableStudyInstance,
    build_microsoft_graph_sync_repository,
)

_TODO_ACTIONABLE_STATUSES = {"missed", "skipped"}
_PRIORITY_TO_IMPORTANCE = {"alta": "high", "media": "normal", "baja": "normal"}


@dataclass(frozen=True)
class MicrosoftTodoSyncPreviewResult:
    """Vista previa no destructiva de la proyección hacia Microsoft To Do."""

    previewed: bool
    create_count: int = 0
    update_count: int = 0
    delete_count: int = 0
    actionable_count: int = 0
    active_task_count: int = 0
    target_task_count: int = 0
    task_list_id: str | None = None
    synced_task_map: dict[str, str] = field(default_factory=dict)
    error_code: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class MicrosoftTodoSyncResult:
    """Resultado de una corrida de sync hacia Microsoft To Do."""

    synced: bool
    upserted_count: int = 0
    deleted_count: int = 0
    synced_task_map: dict[str, str] = field(default_factory=dict)
    error_code: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class MicrosoftTodoActivitySyncResult:
    """Resultado de sync de actividades académicas hacia Microsoft To Do."""

    synced: bool
    upserted_count: int = 0
    deleted_count: int = 0
    synced_activities: list = field(default_factory=list)
    error_code: str | None = None
    detail: str | None = None


class MicrosoftTodoSyncService:
    """Convierte sesiones no resueltas en tareas sincronizables."""

    def __init__(
        self,
        *,
        repository: MicrosoftGraphSyncRepository,
        state_repository: MicrosoftGraphStateRepository | None = None,
        auth_client: MicrosoftOAuthClient | None = None,
        client: MicrosoftTodoClient | None = None,
    ) -> None:
        effective_state_repository = state_repository or InMemoryMicrosoftGraphStateRepository()
        self.repository = repository
        self.state_repository = effective_state_repository
        self.auth_client = auth_client or build_microsoft_oauth_client_from_env(
            token_store=MicrosoftGraphStateTokenStore(effective_state_repository)
        )
        self.client = client or GraphMicrosoftTodoClient()

    def preview_actionable_sessions(
        self,
        *,
        student_id: int | None,
        task_list_id: str | None,
        study_plan_profile_id: int | None = None,
    ) -> MicrosoftTodoSyncPreviewResult:
        """Calcula cambios To Do sin crear, actualizar ni borrar tareas."""

        if not student_id:
            return MicrosoftTodoSyncPreviewResult(
                previewed=False,
                error_code="missing_student_id",
                detail="No encontré el estudiante persistido para sincronizar Microsoft To Do.",
            )

        try:
            connection = self.state_repository.get_connection(student_id=int(student_id))
        except (MicrosoftGraphStateRepositoryError, RepositoryConfigurationError) as exc:
            return MicrosoftTodoSyncPreviewResult(
                previewed=False,
                error_code="microsoft_graph_state_error",
                detail=str(exc),
            )
        if connection is None:
            return MicrosoftTodoSyncPreviewResult(
                previewed=False,
                error_code="microsoft_connection_not_found",
                detail=(
                    "No existe una conexión Microsoft persistida para este estudiante. "
                    "Completa OAuth antes de sincronizar Microsoft To Do."
                ),
            )

        token_result = self.auth_client.get_valid_access_token(student_id=int(student_id))
        if not token_result.ok or token_result.token is None:
            return MicrosoftTodoSyncPreviewResult(
                previewed=False,
                error_code=token_result.error_code or "microsoft_oauth_error",
                detail=token_result.detail,
            )

        try:
            connection = self.state_repository.get_connection(student_id=int(student_id))
            effective_task_list_id = _preview_task_list_id(
                connection=connection,
                explicit_task_list_id=task_list_id,
                client=self.client,
                access_token=token_result.token.access_token,
            )
            if not effective_task_list_id:
                return MicrosoftTodoSyncPreviewResult(
                    previewed=False,
                    error_code="missing_task_list_id",
                    detail=(
                        "No pude resolver una lista de Microsoft To Do para proyectar "
                        "tus tareas accionables."
                    ),
                )
            instances = self.repository.list_instances(
                student_id=int(student_id),
                study_plan_profile_id=study_plan_profile_id,
            )
            existing_links = self.state_repository.list_todo_task_links(
                student_id=int(student_id),
                task_list_id=effective_task_list_id,
            )
        except (
            MicrosoftGraphSyncRepositoryError,
            MicrosoftGraphStateRepositoryError,
            RepositoryConfigurationError,
        ) as exc:
            return MicrosoftTodoSyncPreviewResult(
                previewed=False,
                error_code="microsoft_todo_repository_error",
                detail=str(exc),
            )
        except MicrosoftGraphClientError as exc:
            return MicrosoftTodoSyncPreviewResult(
                previewed=False,
                error_code=getattr(exc, "error_code", "microsoft_todo_sync_error"),
                detail=getattr(exc, "detail", str(exc)),
            )

        existing_link_map = {link.source_instance_key: link for link in existing_links}
        actionable = [
            instance for instance in instances if instance.status in _TODO_ACTIONABLE_STATUSES
        ]
        active_keys = {instance.source_instance_key for instance in actionable}
        create_count = sum(
            1 for instance in actionable if instance.source_instance_key not in existing_link_map
        )
        update_count = len(actionable) - create_count
        delete_count = sum(
            1 for link in existing_links if link.source_instance_key not in active_keys
        )

        return MicrosoftTodoSyncPreviewResult(
            previewed=True,
            create_count=create_count,
            update_count=update_count,
            delete_count=delete_count,
            actionable_count=len(actionable),
            active_task_count=len(existing_links),
            target_task_count=len(actionable),
            task_list_id=effective_task_list_id,
            synced_task_map={
                link.source_instance_key: link.external_task_id for link in existing_links
            },
        )

    def sync_actionable_sessions(
        self,
        *,
        student_id: int | None,
        task_list_id: str | None,
        synced_task_map: dict[str, str] | None = None,
        study_plan_profile_id: int | None = None,
    ) -> MicrosoftTodoSyncResult:
        del synced_task_map  # La verdad durable vive en microsoft_todo_task_links.
        if not student_id:
            return MicrosoftTodoSyncResult(
                synced=False,
                error_code="missing_student_id",
                detail="No encontré el estudiante persistido para sincronizar Microsoft To Do.",
            )

        try:
            connection = self.state_repository.get_connection(student_id=int(student_id))
        except (MicrosoftGraphStateRepositoryError, RepositoryConfigurationError) as exc:
            return MicrosoftTodoSyncResult(
                synced=False,
                error_code="microsoft_graph_state_error",
                detail=str(exc),
            )
        if connection is None:
            return MicrosoftTodoSyncResult(
                synced=False,
                error_code="microsoft_connection_not_found",
                detail=(
                    "No existe una conexión Microsoft persistida para este estudiante. "
                    "Completa OAuth antes de sincronizar Microsoft To Do."
                ),
            )

        token_result = self.auth_client.get_valid_access_token(student_id=int(student_id))
        if not token_result.ok or token_result.token is None:
            return MicrosoftTodoSyncResult(
                synced=False,
                error_code=token_result.error_code or "microsoft_oauth_error",
                detail=token_result.detail,
            )

        try:
            connection = self.state_repository.get_connection(student_id=int(student_id))
            connection = _resolve_task_list_connection(
                state_repository=self.state_repository,
                connection=connection,
                explicit_task_list_id=task_list_id,
                client=self.client,
                access_token=token_result.token.access_token,
            )
            effective_task_list_id = str(connection.todo_task_list_id or "").strip()
            if not effective_task_list_id:
                return MicrosoftTodoSyncResult(
                    synced=False,
                    error_code="missing_task_list_id",
                    detail=(
                        "Debes configurar un task_list_id en la conexión Microsoft "
                        "o pasarlo explícitamente al sync."
                    ),
                )
            instances = self.repository.list_instances(
                student_id=int(student_id),
                study_plan_profile_id=study_plan_profile_id,
            )
            existing_links = self.state_repository.list_todo_task_links(
                student_id=int(student_id),
                task_list_id=effective_task_list_id,
            )
        except (
            MicrosoftGraphSyncRepositoryError,
            MicrosoftGraphStateRepositoryError,
            RepositoryConfigurationError,
        ) as exc:
            return MicrosoftTodoSyncResult(
                synced=False,
                error_code="microsoft_todo_repository_error",
                detail=str(exc),
            )
        except MicrosoftGraphClientError as exc:
            return MicrosoftTodoSyncResult(
                synced=False,
                error_code=getattr(exc, "error_code", "microsoft_todo_sync_error"),
                detail=getattr(exc, "detail", str(exc)),
            )

        existing_link_map = {link.source_instance_key: link for link in existing_links}
        actionable = [
            instance for instance in instances if instance.status in _TODO_ACTIONABLE_STATUSES
        ]
        active_keys = {instance.source_instance_key for instance in actionable}
        delete_links = [
            link for link in existing_links if link.source_instance_key not in active_keys
        ]

        try:
            upserted = self.client.upsert_tasks(
                access_token=token_result.token.access_token,
                task_list_id=effective_task_list_id,
                tasks=[
                    _build_todo_task(instance, existing_link=existing_link_map.get(instance.source_instance_key))
                    for instance in actionable
                ],
            ) if actionable else []
            deleted = self.client.delete_tasks(
                access_token=token_result.token.access_token,
                task_list_id=effective_task_list_id,
                external_task_ids=[link.external_task_id for link in delete_links],
            ) if delete_links else []
            self.state_repository.upsert_todo_task_links(
                links=[
                    MicrosoftTodoTaskLinkRecord(
                        id=existing_link_map.get(record.external_key).id
                        if record.external_key in existing_link_map
                        else None,
                        student_id=int(student_id),
                        study_plan_event_instance_id=_instance_id_for_key(
                            instances=instances,
                            source_instance_key=record.external_key,
                        ),
                        source_instance_key=record.external_key,
                        task_list_id=effective_task_list_id,
                        external_task_id=record.external_task_id,
                        sync_status="active",
                    )
                    for record in upserted
                ]
            )
            if deleted:
                deleted_lookup = set(deleted)
                self.state_repository.mark_todo_task_links_deleted(
                    student_id=int(student_id),
                    source_instance_keys=[
                        link.source_instance_key
                        for link in delete_links
                        if link.external_task_id in deleted_lookup
                    ],
                )
            active_links = self.state_repository.list_todo_task_links(
                student_id=int(student_id),
                task_list_id=effective_task_list_id,
            )
        except (MicrosoftGraphClientError, MicrosoftGraphStateRepositoryError) as exc:
            error_code = getattr(exc, "error_code", "microsoft_todo_sync_error")
            detail = getattr(exc, "detail", str(exc))
            return MicrosoftTodoSyncResult(
                synced=False,
                synced_task_map={
                    link.source_instance_key: link.external_task_id for link in existing_links
                },
                error_code=error_code,
                detail=detail,
            )

        return MicrosoftTodoSyncResult(
            synced=True,
            upserted_count=len(upserted),
            deleted_count=len(deleted),
            synced_task_map={
                link.source_instance_key: link.external_task_id for link in active_links
            },
        )


    def sync_academic_activities_to_todo(
        self,
        *,
        student_id: int | None,
        task_list_id: str | None,
        activities: list,
    ) -> MicrosoftTodoActivitySyncResult:
        """Sincroniza actividades académicas con Microsoft To Do.

        Cada actividad pending/completed se upsertea; deleted se elimina si
        conserva todo_task_id. priority_level='alta' se marca con importance='high' (⭐).
        Usa activity.todo_task_id como id externo para evitar duplicados.
        Retorna las actividades con todo_task_id actualizado.
        """
        from schemas.planning import AcademicActivity

        if not student_id:
            return MicrosoftTodoActivitySyncResult(
                synced=False,
                error_code="missing_student_id",
                detail="No encontré el estudiante persistido para sincronizar Microsoft To Do.",
            )

        try:
            connection = self.state_repository.get_connection(student_id=int(student_id))
        except (MicrosoftGraphStateRepositoryError, RepositoryConfigurationError) as exc:
            return MicrosoftTodoActivitySyncResult(
                synced=False,
                error_code="microsoft_graph_state_error",
                detail=str(exc),
            )
        if connection is None:
            return MicrosoftTodoActivitySyncResult(
                synced=False,
                error_code="microsoft_connection_not_found",
                detail=(
                    "No existe una conexión Microsoft persistida para este estudiante. "
                    "Completa OAuth antes de sincronizar Microsoft To Do."
                ),
            )

        token_result = self.auth_client.get_valid_access_token(student_id=int(student_id))
        if not token_result.ok or token_result.token is None:
            return MicrosoftTodoActivitySyncResult(
                synced=False,
                error_code=token_result.error_code or "microsoft_oauth_error",
                detail=token_result.detail,
            )

        try:
            connection = _resolve_task_list_connection(
                state_repository=self.state_repository,
                connection=connection,
                explicit_task_list_id=task_list_id,
                client=self.client,
                access_token=token_result.token.access_token,
            )
        except (MicrosoftGraphStateRepositoryError, RepositoryConfigurationError) as exc:
            return MicrosoftTodoActivitySyncResult(
                synced=False,
                error_code="microsoft_todo_repository_error",
                detail=str(exc),
            )

        effective_task_list_id = str(connection.todo_task_list_id or "").strip()
        if not effective_task_list_id:
            return MicrosoftTodoActivitySyncResult(
                synced=False,
                error_code="missing_task_list_id",
                detail="Debes configurar un task_list_id para sincronizar actividades con Microsoft To Do.",
            )

        # Coerce activities to AcademicActivity objects
        coerced: list[AcademicActivity] = []
        for act in activities:
            if isinstance(act, AcademicActivity):
                coerced.append(act)
            elif isinstance(act, dict):
                try:
                    coerced.append(AcademicActivity.model_validate(act))
                except Exception:
                    pass

        if not coerced:
            return MicrosoftTodoActivitySyncResult(synced=True, upserted_count=0, synced_activities=[])

        upsertable = [act for act in coerced if act.status in {"pending", "completed"}]
        deleteable = [
            act
            for act in coerced
            if act.status == "deleted" and str(act.todo_task_id or "").strip()
        ]
        tasks = [_build_activity_todo_task(act) for act in upsertable]
        external_task_ids_to_delete = [str(act.todo_task_id) for act in deleteable]

        try:
            upserted = self.client.upsert_tasks(
                access_token=token_result.token.access_token,
                task_list_id=effective_task_list_id,
                tasks=tasks,
            ) if tasks else []
            deleted = self.client.delete_tasks(
                access_token=token_result.token.access_token,
                task_list_id=effective_task_list_id,
                external_task_ids=external_task_ids_to_delete,
            ) if external_task_ids_to_delete else []
        except MicrosoftGraphClientError as exc:
            return MicrosoftTodoActivitySyncResult(
                synced=False,
                error_code=getattr(exc, "error_code", "microsoft_todo_sync_error"),
                detail=getattr(exc, "detail", str(exc)),
            )

        # Build a map activity_id → task_id and update activities
        task_id_map = {record.external_key: record.external_task_id for record in upserted}
        deleted_lookup = set(deleted)
        updated_activities = [
            act.model_copy(update={"todo_task_id": task_id_map.get(act.activity_id, act.todo_task_id)})
            if act.status in {"pending", "completed"}
            else act.model_copy(update={"todo_task_id": None})
            if act.status == "deleted" and str(act.todo_task_id or "") in deleted_lookup
            else act
            for act in coerced
        ]

        return MicrosoftTodoActivitySyncResult(
            synced=True,
            upserted_count=len(upserted),
            deleted_count=len(deleted),
            synced_activities=updated_activities,
        )


def build_microsoft_todo_sync_service(
    *,
    instances_repository: Any | None = None,
    state_repository: MicrosoftGraphStateRepository | None = None,
    auth_client: MicrosoftOAuthClient | None = None,
    client: MicrosoftTodoClient | None = None,
) -> MicrosoftTodoSyncService:
    """Construye el servicio de proyección hacia Microsoft To Do."""

    if instances_repository is not None:
        repository = InMemoryMicrosoftGraphSyncRepository(
            instances_repository=instances_repository
        )
    else:
        repository = build_microsoft_graph_sync_repository(database_url_from_env())

    if state_repository is None:
        if instances_repository is not None:
            state_repository = InMemoryMicrosoftGraphStateRepository()
        else:
            state_repository = build_microsoft_graph_state_repository(database_url_from_env())

    if auth_client is None:
        auth_client = build_microsoft_oauth_client_from_env(
            token_store=MicrosoftGraphStateTokenStore(state_repository)
        )

    return MicrosoftTodoSyncService(
        repository=repository,
        state_repository=state_repository,
        auth_client=auth_client,
        client=client,
    )


def _build_activity_todo_task(activity: object) -> "MicrosoftTodoTaskUpsert":
    """Mapea una AcademicActivity a MicrosoftTodoTaskUpsert.

    priority_level='alta' → importance='high' (⭐ en To Do).
    Usa activity.todo_task_id como existing_external_task_id para deduplicar.
    """
    from datetime import datetime, timezone as _tz

    activity_id = str(getattr(activity, "activity_id", "") or "")
    subject_name = str(getattr(activity, "subject_name", "") or "")
    activity_type = str(getattr(activity, "activity_type", "") or "")
    title = str(getattr(activity, "activity_title", "") or activity_type)
    due_date_str = getattr(activity, "due_date", None)
    priority_level = str(getattr(activity, "priority_level", None) or "")
    status = str(getattr(activity, "status", "pending") or "pending")
    existing_task_id = getattr(activity, "todo_task_id", None) or None

    importance = _PRIORITY_TO_IMPORTANCE.get(priority_level)

    due_at: datetime | None = None
    if due_date_str:
        try:
            from datetime import date as _date
            d = _date.fromisoformat(str(due_date_str))
            due_at = datetime(d.year, d.month, d.day, 23, 59, 0, tzinfo=_tz.utc)
        except (ValueError, TypeError):
            pass

    star_prefix = "⭐ " if importance == "high" else ""
    task_title = f"{star_prefix}[{activity_type}] {subject_name}: {title}" if subject_name else title

    return MicrosoftTodoTaskUpsert(
        external_key=activity_id,
        title=task_title,
        body_preview=f"Tipo: {activity_type} | Materia: {subject_name} | Vence: {due_date_str or 'sin fecha'}",
        due_at=due_at,
        importance=importance,
        is_completed=(status == "completed"),
        existing_external_task_id=existing_task_id,
    )


def _build_todo_task(
    instance: MicrosoftSyncableStudyInstance,
    *,
    existing_link: MicrosoftTodoTaskLinkRecord | None,
) -> MicrosoftTodoTaskUpsert:
    status_label = "Reprogramar" if instance.status == "missed" else "Revisar"
    return MicrosoftTodoTaskUpsert(
        external_key=instance.source_instance_key,
        title=f"{status_label}: {instance.title}",
        body_preview=(
            f"Sesion con status={instance.status}. "
            f"Instancia={instance.source_instance_key}. "
            f"Fecha original={instance.starts_at.isoformat()}."
        ),
        due_at=instance.ends_at,
        metadata={
            "student_id": instance.student_id,
            "study_plan_profile_id": instance.study_plan_profile_id,
            "instance_id": instance.id,
            "status": instance.status,
        },
        existing_external_task_id=(
            existing_link.external_task_id if existing_link is not None else None
        ),
    )


def _resolve_task_list_connection(
    *,
    state_repository: MicrosoftGraphStateRepository,
    connection: MicrosoftGraphConnectionRecord | None,
    explicit_task_list_id: str | None,
    client: MicrosoftTodoClient,
    access_token: str,
) -> MicrosoftGraphConnectionRecord:
    if connection is None:
        raise MicrosoftGraphStateRepositoryError("No existe conexión Microsoft para este estudiante.")
    normalized = str(explicit_task_list_id or "").strip()
    if normalized:
        if connection.todo_task_list_id == normalized:
            return connection
        return state_repository.upsert_connection(
            record=replace(connection, todo_task_list_id=normalized)
        )

    persisted_task_list_id = str(connection.todo_task_list_id or "").strip()
    if persisted_task_list_id:
        return connection

    selected_task_list = _select_default_task_list(
        client.list_task_lists(access_token=access_token)
    )
    if selected_task_list is None:
        return connection

    return state_repository.upsert_connection(
        record=replace(connection, todo_task_list_id=selected_task_list.id)
    )


def _select_default_task_list(
    task_lists: list[MicrosoftTodoTaskList],
) -> MicrosoftTodoTaskList | None:
    for task_list in task_lists:
        if task_list.wellknown_list_name == "defaultList":
            return task_list
    return task_lists[0] if task_lists else None


def _preview_task_list_id(
    *,
    connection: MicrosoftGraphConnectionRecord | None,
    explicit_task_list_id: str | None,
    client: MicrosoftTodoClient,
    access_token: str,
) -> str | None:
    normalized = str(explicit_task_list_id or "").strip()
    if normalized:
        return normalized
    if connection is None:
        return None
    persisted_task_list_id = str(connection.todo_task_list_id or "").strip()
    if persisted_task_list_id:
        return persisted_task_list_id
    selected_task_list = _select_default_task_list(
        client.list_task_lists(access_token=access_token)
    )
    if selected_task_list is None:
        return None
    return selected_task_list.id


def _instance_id_for_key(
    *,
    instances: list[MicrosoftSyncableStudyInstance],
    source_instance_key: str,
) -> int | None:
    for instance in instances:
        if instance.source_instance_key == source_instance_key:
            return instance.id
    return None


__all__ = [
    "MicrosoftTodoActivitySyncResult",
    "MicrosoftTodoSyncPreviewResult",
    "MicrosoftTodoSyncResult",
    "MicrosoftTodoSyncService",
    "build_microsoft_todo_sync_service",
]
