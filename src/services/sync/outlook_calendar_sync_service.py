"""Sincronización durable de instancias hacia Outlook Calendar."""

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
from schemas.microsoft_graph import CalendarState

from integrations.microsoft_graph.calendar_client import GraphOutlookCalendarClient
from integrations.microsoft_graph.models import (
    MicrosoftGraphClientError,
    OutlookCalendarClient,
    OutlookCalendarEventUpsert,
)
from repositories.microsoft_graph.state_repository import (
    InMemoryMicrosoftGraphStateRepository,
    MicrosoftGraphConnectionRecord,
    MicrosoftGraphStateRepository,
    MicrosoftGraphStateRepositoryError,
    OutlookCalendarEventLinkRecord,
    build_microsoft_graph_state_repository,
)
from repositories.microsoft_graph.sync_repository import (
    InMemoryMicrosoftGraphSyncRepository,
    MicrosoftGraphSyncRepository,
    MicrosoftGraphSyncRepositoryError,
    MicrosoftSyncableStudyInstance,
    build_microsoft_graph_sync_repository,
)

_CALENDAR_UPSERT_STATUSES = {"scheduled", "in_progress", "completed", "missed", "skipped"}
_CALENDAR_DELETE_STATUSES = {"superseded", "canceled"}
_DEFAULT_CALENDAR_SCOPE_ID = "__default__"


@dataclass(frozen=True)
class OutlookCalendarSyncResult:
    """Resultado de una corrida de sync hacia Outlook Calendar."""

    synced: bool
    upserted_count: int = 0
    deleted_count: int = 0
    synced_event_map: dict[str, str] = field(default_factory=dict)
    error_code: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class OutlookCalendarSyncPreviewResult:
    """Previsualizacion local antes de tocar Outlook Calendar."""

    previewed: bool
    create_count: int = 0
    update_count: int = 0
    delete_count: int = 0
    active_instance_count: int = 0
    target_instance_count: int = 0
    synced_event_map: dict[str, str] = field(default_factory=dict)
    error_code: str | None = None
    detail: str | None = None


class OutlookCalendarSyncService:
    """Sincroniza instancias materializadas hacia Outlook Calendar."""

    def __init__(
        self,
        *,
        repository: MicrosoftGraphSyncRepository,
        state_repository: MicrosoftGraphStateRepository | None = None,
        auth_client: MicrosoftOAuthClient | None = None,
        client: OutlookCalendarClient | None = None,
    ) -> None:
        effective_state_repository = state_repository or InMemoryMicrosoftGraphStateRepository()
        self.repository = repository
        self.state_repository = effective_state_repository
        self.auth_client = auth_client or build_microsoft_oauth_client_from_env(
            token_store=MicrosoftGraphStateTokenStore(effective_state_repository)
        )
        self.client = client or GraphOutlookCalendarClient()

    def preview_student_calendar_sync(
        self,
        *,
        student_id: int | None,
        calendar_state: CalendarState | dict | None = None,
        calendar_id: str | None = None,
        study_plan_profile_id: int | None = None,
    ) -> OutlookCalendarSyncPreviewResult:
        """Calcula impacto local de sync sin llamar a Microsoft Graph."""

        if not student_id:
            return OutlookCalendarSyncPreviewResult(
                previewed=False,
                error_code="missing_student_id",
                detail="No encontré el estudiante persistido para sincronizar Outlook Calendar.",
            )

        normalized_calendar = _ensure_calendar_state(calendar_state)
        validation_error = _validate_calendar_state(normalized_calendar)
        if validation_error is not None:
            return OutlookCalendarSyncPreviewResult(
                previewed=False,
                synced_event_map=dict(normalized_calendar.synced_event_map),
                error_code=validation_error.error_code,
                detail=validation_error.detail,
            )

        try:
            connection = self.state_repository.get_connection(student_id=int(student_id))
        except (MicrosoftGraphStateRepositoryError, RepositoryConfigurationError) as exc:
            return OutlookCalendarSyncPreviewResult(
                previewed=False,
                error_code="microsoft_graph_state_error",
                detail=str(exc),
            )
        if connection is None:
            return OutlookCalendarSyncPreviewResult(
                previewed=False,
                error_code="microsoft_connection_not_found",
                detail=(
                    "No existe una conexión Microsoft persistida para este estudiante. "
                    "Completa OAuth antes de sincronizar el calendario."
                ),
            )

        try:
            instances = self.repository.list_instances(
                student_id=int(student_id),
                study_plan_profile_id=study_plan_profile_id,
            )
            storage_calendar_id = _storage_calendar_id(
                _connection_with_resolved_calendar(
                    connection=connection,
                    explicit_calendar_id=_resolve_calendar_id(
                        calendar_id,
                        normalized_calendar.calendar_id,
                    ),
                )
            )
            existing_links = self.state_repository.list_calendar_event_links(
                student_id=int(student_id),
                calendar_id=storage_calendar_id,
            )
        except (
            MicrosoftGraphSyncRepositoryError,
            MicrosoftGraphStateRepositoryError,
            RepositoryConfigurationError,
        ) as exc:
            return OutlookCalendarSyncPreviewResult(
                previewed=False,
                error_code="outlook_calendar_repository_error",
                detail=str(exc),
            )

        existing_link_map = {link.source_instance_key: link for link in existing_links}
        upsert_instances = [
            instance
            for instance in instances
            if instance.status in _CALENDAR_UPSERT_STATUSES
        ]
        delete_instances = [
            instance
            for instance in instances
            if instance.status in _CALENDAR_DELETE_STATUSES
            and instance.source_instance_key in existing_link_map
        ]
        update_count = sum(
            1 for instance in upsert_instances if instance.source_instance_key in existing_link_map
        )
        create_count = len(upsert_instances) - update_count
        return OutlookCalendarSyncPreviewResult(
            previewed=True,
            create_count=create_count,
            update_count=update_count,
            delete_count=len(delete_instances),
            active_instance_count=len(upsert_instances),
            target_instance_count=len(instances),
            synced_event_map={
                link.source_instance_key: link.external_event_id for link in existing_links
            },
        )

    def sync_student_calendar(
        self,
        *,
        student_id: int | None,
        calendar_state: CalendarState | dict | None = None,
        calendar_id: str | None = None,
        study_plan_profile_id: int | None = None,
    ) -> OutlookCalendarSyncResult:
        if not student_id:
            return OutlookCalendarSyncResult(
                synced=False,
                error_code="missing_student_id",
                detail="No encontré el estudiante persistido para sincronizar Outlook Calendar.",
            )

        normalized_calendar = _ensure_calendar_state(calendar_state)
        validation_error = _validate_calendar_state(normalized_calendar)
        if validation_error is not None:
            return validation_error

        try:
            connection = self.state_repository.get_connection(student_id=int(student_id))
        except (MicrosoftGraphStateRepositoryError, RepositoryConfigurationError) as exc:
            return OutlookCalendarSyncResult(
                synced=False,
                error_code="microsoft_graph_state_error",
                detail=str(exc),
            )
        if connection is None:
            return OutlookCalendarSyncResult(
                synced=False,
                error_code="microsoft_connection_not_found",
                detail=(
                    "No existe una conexión Microsoft persistida para este estudiante. "
                    "Completa OAuth antes de sincronizar el calendario."
                ),
            )

        token_result = self.auth_client.get_valid_access_token(student_id=int(student_id))
        if not token_result.ok or token_result.token is None:
            return OutlookCalendarSyncResult(
                synced=False,
                error_code=token_result.error_code or "microsoft_oauth_error",
                detail=token_result.detail,
            )

        try:
            connection = self.state_repository.get_connection(student_id=int(student_id))
            connection = _persist_calendar_default(
                state_repository=self.state_repository,
                connection=connection,
                explicit_calendar_id=_resolve_calendar_id(calendar_id, normalized_calendar.calendar_id),
            )
            instances = self.repository.list_instances(
                student_id=int(student_id),
                study_plan_profile_id=study_plan_profile_id,
            )
            storage_calendar_id = _storage_calendar_id(connection)
            existing_links = self.state_repository.list_calendar_event_links(
                student_id=int(student_id),
                calendar_id=storage_calendar_id,
            )
        except (
            MicrosoftGraphSyncRepositoryError,
            MicrosoftGraphStateRepositoryError,
            RepositoryConfigurationError,
        ) as exc:
            return OutlookCalendarSyncResult(
                synced=False,
                error_code="outlook_calendar_repository_error",
                detail=str(exc),
            )

        existing_link_map = {link.source_instance_key: link for link in existing_links}
        upserts = [
            _build_outlook_event(instance, existing_link=existing_link_map.get(instance.source_instance_key))
            for instance in instances
            if instance.status in _CALENDAR_UPSERT_STATUSES
        ]
        delete_links = [
            existing_link_map[instance.source_instance_key]
            for instance in instances
            if instance.status in _CALENDAR_DELETE_STATUSES
            and instance.source_instance_key in existing_link_map
        ]

        try:
            upserted = self.client.upsert_events(
                access_token=token_result.token.access_token,
                calendar_id=connection.calendar_id,
                events=upserts,
            ) if upserts else []
            deleted_ids = self.client.delete_events(
                access_token=token_result.token.access_token,
                calendar_id=connection.calendar_id,
                external_event_ids=[link.external_event_id for link in delete_links],
            ) if delete_links else []
            self.state_repository.upsert_calendar_event_links(
                links=[
                    OutlookCalendarEventLinkRecord(
                        id=existing_link_map.get(record.external_key).id
                        if record.external_key in existing_link_map
                        else None,
                        student_id=int(student_id),
                        study_plan_event_instance_id=_instance_id_for_key(
                            instances=instances,
                            source_instance_key=record.external_key,
                        ),
                        source_instance_key=record.external_key,
                        calendar_id=storage_calendar_id,
                        external_event_id=record.external_event_id,
                        external_change_key=record.external_change_key,
                        sync_status="active",
                    )
                    for record in upserted
                ]
            )
            if deleted_ids:
                deleted_lookup = set(deleted_ids)
                self.state_repository.mark_calendar_event_links_deleted(
                    student_id=int(student_id),
                    source_instance_keys=[
                        link.source_instance_key
                        for link in delete_links
                        if link.external_event_id in deleted_lookup
                    ],
                )
            active_links = self.state_repository.list_calendar_event_links(
                student_id=int(student_id),
                calendar_id=storage_calendar_id,
            )
        except (MicrosoftGraphClientError, MicrosoftGraphStateRepositoryError) as exc:
            error_code = getattr(exc, "error_code", "outlook_calendar_sync_error")
            detail = getattr(exc, "detail", str(exc))
            return OutlookCalendarSyncResult(
                synced=False,
                synced_event_map={
                    link.source_instance_key: link.external_event_id for link in existing_links
                },
                error_code=error_code,
                detail=detail,
            )

        return OutlookCalendarSyncResult(
            synced=True,
            upserted_count=len(upserted),
            deleted_count=len(deleted_ids),
            synced_event_map={
                link.source_instance_key: link.external_event_id for link in active_links
            },
        )


def build_outlook_calendar_sync_service(
    *,
    instances_repository: Any | None = None,
    state_repository: MicrosoftGraphStateRepository | None = None,
    auth_client: MicrosoftOAuthClient | None = None,
    client: OutlookCalendarClient | None = None,
) -> OutlookCalendarSyncService:
    """Construye el servicio de sincronización Outlook."""

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

    return OutlookCalendarSyncService(
        repository=repository,
        state_repository=state_repository,
        auth_client=auth_client,
        client=client,
    )


def _ensure_calendar_state(calendar_state: CalendarState | dict | None) -> CalendarState:
    if isinstance(calendar_state, CalendarState):
        return calendar_state.model_copy(deep=True)
    return CalendarState(**dict(calendar_state or {}))


def _validate_calendar_state(calendar_state: CalendarState) -> OutlookCalendarSyncResult | None:
    if calendar_state.provider and calendar_state.provider != "outlook":
        return OutlookCalendarSyncResult(
            synced=False,
            synced_event_map=dict(calendar_state.synced_event_map),
            error_code="calendar_provider_not_outlook",
            detail="Esta integración solo sincroniza con provider='outlook'.",
        )
    return None


def _build_outlook_event(
    instance: MicrosoftSyncableStudyInstance,
    *,
    existing_link: OutlookCalendarEventLinkRecord | None,
) -> OutlookCalendarEventUpsert:
    event_payload = dict(instance.payload.get("event") or {})
    difficulty = event_payload.get("dificultad")
    priority = event_payload.get("prioridad")
    body_preview = (
        f"Sesion de estudio sincronizada por Academic Agent.\n"
        f"Estado: {instance.status}\n"
        f"Instancia: {instance.source_instance_key}\n"
        f"Prioridad: {priority or 'n/a'}\n"
        f"Dificultad: {difficulty or 'n/a'}"
    )
    return OutlookCalendarEventUpsert(
        external_key=instance.source_instance_key,
        subject=instance.title,
        body_preview=body_preview,
        starts_at=instance.starts_at,
        ends_at=instance.ends_at,
        timezone=instance.timezone,
        categories=(
            "academic-agent",
            "study-plan",
            f"status:{instance.status}",
        ),
        metadata={
            "student_id": instance.student_id,
            "study_plan_profile_id": instance.study_plan_profile_id,
            "instance_id": instance.id,
        },
        existing_external_event_id=(
            existing_link.external_event_id if existing_link is not None else None
        ),
        existing_change_key=(
            existing_link.external_change_key if existing_link is not None else None
        ),
    )


def _resolve_calendar_id(
    explicit_calendar_id: str | None,
    state_calendar_id: str | None,
) -> str | None:
    for candidate in (explicit_calendar_id, state_calendar_id):
        normalized = str(candidate or "").strip()
        if normalized:
            return normalized
    return None


def _persist_calendar_default(
    *,
    state_repository: MicrosoftGraphStateRepository,
    connection: MicrosoftGraphConnectionRecord | None,
    explicit_calendar_id: str | None,
) -> MicrosoftGraphConnectionRecord:
    if connection is None:
        raise MicrosoftGraphStateRepositoryError("No existe conexión Microsoft para este estudiante.")
    if not explicit_calendar_id or connection.calendar_id == explicit_calendar_id:
        return connection
    return state_repository.upsert_connection(
        record=replace(connection, calendar_id=explicit_calendar_id)
    )


def _connection_with_resolved_calendar(
    *,
    connection: MicrosoftGraphConnectionRecord,
    explicit_calendar_id: str | None,
) -> MicrosoftGraphConnectionRecord:
    if not explicit_calendar_id or connection.calendar_id == explicit_calendar_id:
        return connection
    return replace(connection, calendar_id=explicit_calendar_id)


def _storage_calendar_id(connection: MicrosoftGraphConnectionRecord) -> str:
    normalized = str(connection.calendar_id or "").strip()
    return normalized or _DEFAULT_CALENDAR_SCOPE_ID


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
    "OutlookCalendarSyncResult",
    "OutlookCalendarSyncService",
    "build_outlook_calendar_sync_service",
]
