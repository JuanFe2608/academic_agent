"""Sincronización del horario fijo recurrente hacia Outlook Calendar."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

from bootstrap.errors import RepositoryConfigurationError
from bootstrap.settings import database_url_from_env
from integrations.microsoft_graph.auth_client import (
    MicrosoftGraphStateTokenStore,
    MicrosoftOAuthClient,
    build_microsoft_oauth_client_from_env,
)
from integrations.microsoft_graph.calendar_client import GraphOutlookCalendarClient
from integrations.microsoft_graph.models import (
    MicrosoftGraphClientError,
    OutlookCalendarClient,
)
from repositories.microsoft_graph.state_repository import (
    InMemoryMicrosoftGraphStateRepository,
    MicrosoftGraphConnectionRecord,
    MicrosoftGraphStateRepository,
    MicrosoftGraphStateRepositoryError,
    build_microsoft_graph_state_repository,
)
from repositories.scheduling.repository import (
    InMemoryScheduleRepository,
    PersistedRecurringScheduleBlock,
    RecurringScheduleBlockSyncUpdate,
    ScheduleRepository,
    ScheduleRepositoryError,
    build_schedule_repository,
)
from schemas.microsoft_graph import CalendarState
from services.sync.fixed_schedule_outlook_projection import (
    build_outlook_fixed_schedule_event,
    resolve_series_start_date,
)
_DEFAULT_CALENDAR_SCOPE_ID = "__default__"


@dataclass(frozen=True)
class OutlookFixedScheduleSyncResult:
    """Resultado de sincronizar el horario fijo hacia Outlook."""

    synced: bool
    upserted_count: int = 0
    deleted_count: int = 0
    synced_event_map: dict[str, str] = field(default_factory=dict)
    error_code: str | None = None
    detail: str | None = None


class OutlookFixedScheduleSyncService:
    """Sincroniza bloques recurrentes confirmados como series semanales de Outlook."""

    def __init__(
        self,
        *,
        repository: ScheduleRepository,
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

    def sync_schedule_profile(
        self,
        *,
        student_id: int | None,
        schedule_profile_id: int | None,
        calendar_state: CalendarState | dict | None = None,
        calendar_id: str | None = None,
        target_block_ids: set[int] | list[int] | tuple[int, ...] | None = None,
        delete_stale_blocks: bool = True,
    ) -> OutlookFixedScheduleSyncResult:
        if not student_id:
            return OutlookFixedScheduleSyncResult(
                synced=False,
                error_code="missing_student_id",
                detail="No encontré el estudiante persistido para sincronizar Outlook.",
            )
        if not schedule_profile_id:
            return OutlookFixedScheduleSyncResult(
                synced=False,
                error_code="missing_schedule_profile_id",
                detail="No encontré el schedule_profile_id del horario confirmado.",
            )

        normalized_calendar = _ensure_calendar_state(calendar_state)
        validation_error = _validate_calendar_state(normalized_calendar)
        if validation_error is not None:
            return validation_error

        try:
            connection = self.state_repository.get_connection(student_id=int(student_id))
        except (MicrosoftGraphStateRepositoryError, RepositoryConfigurationError) as exc:
            return OutlookFixedScheduleSyncResult(
                synced=False,
                error_code="microsoft_graph_state_error",
                detail=str(exc),
            )
        if connection is None:
            return OutlookFixedScheduleSyncResult(
                synced=False,
                error_code="microsoft_connection_not_found",
                detail=(
                    "No existe una conexión Microsoft persistida para este estudiante. "
                    "Completa OAuth antes de sincronizar Outlook."
                ),
            )

        token_result = self.auth_client.get_valid_access_token(student_id=int(student_id))
        if not token_result.ok or token_result.token is None:
            return OutlookFixedScheduleSyncResult(
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
            blocks = self.repository.list_student_schedule_blocks(student_id=int(student_id))
        except (
            ScheduleRepositoryError,
            MicrosoftGraphStateRepositoryError,
            RepositoryConfigurationError,
        ) as exc:
            return OutlookFixedScheduleSyncResult(
                synced=False,
                error_code="outlook_fixed_schedule_repository_error",
                detail=str(exc),
            )

        target_ids = (
            {int(block_id) for block_id in target_block_ids}
            if target_block_ids is not None
            else None
        )
        current_blocks = [
            block
            for block in blocks
            if block.schedule_profile_id == int(schedule_profile_id) and block.profile_is_current
        ]
        if target_ids is not None:
            current_blocks = [block for block in current_blocks if block.id in target_ids]
        if not current_blocks:
            return OutlookFixedScheduleSyncResult(
                synced=False,
                error_code="empty_schedule_blocks",
                detail="No encontré bloques recurrentes activos para el horario confirmado.",
            )

        stale_blocks = [
            block
            for block in blocks
            if block.schedule_profile_id != int(schedule_profile_id)
            and block.external_provider == "outlook"
            and block.external_event_id
            and block.external_sync_status != "deleted"
        ] if delete_stale_blocks else []

        upserts = [build_outlook_fixed_schedule_event(block) for block in current_blocks]
        delete_blocks = [
            block
            for block in stale_blocks
            if str(block.external_event_id or "").strip()
            and block.external_sync_status != "missing"
        ]
        already_missing_stale_blocks = [
            block
            for block in stale_blocks
            if str(block.external_event_id or "").strip()
            and block.external_sync_status == "missing"
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
                external_event_ids=[str(block.external_event_id) for block in delete_blocks],
            ) if delete_blocks else []

            update_map = {block.source_block_id: block for block in current_blocks}
            self.repository.update_block_sync_metadata(
                updates=[
                    RecurringScheduleBlockSyncUpdate(
                        block_id=update_map[record.external_key].id,
                        external_provider="outlook",
                        external_series_id=record.external_event_id,
                        external_event_id=record.external_event_id,
                        external_sync_status="active",
                        external_sync_metadata=_active_sync_metadata(
                            block=update_map[record.external_key],
                            storage_calendar_id=_storage_calendar_id(connection),
                            external_change_key=record.external_change_key,
                        ),
                    )
                    for record in upserted
                ]
            )
            if deleted_ids or already_missing_stale_blocks:
                deleted_lookup = set(deleted_ids)
                self.repository.update_block_sync_metadata(
                    updates=[
                        RecurringScheduleBlockSyncUpdate(
                            block_id=block.id,
                            external_provider="outlook",
                            external_series_id=block.external_series_id,
                            external_event_id=block.external_event_id,
                            external_sync_status="deleted",
                            external_sync_metadata={
                                **dict(block.external_sync_metadata),
                                "deleted_at": _utc_now_iso(),
                            },
                        )
                        for block in delete_blocks
                        if block.external_event_id in deleted_lookup
                    ] + [
                        RecurringScheduleBlockSyncUpdate(
                            block_id=block.id,
                            external_provider="outlook",
                            external_series_id=block.external_series_id,
                            external_event_id=block.external_event_id,
                            external_sync_status="deleted",
                            external_sync_metadata={
                                **dict(block.external_sync_metadata),
                                "deleted_at": _utc_now_iso(),
                                "delete_reason": "stale_missing_event",
                            },
                        )
                        for block in already_missing_stale_blocks
                    ]
                )
            active_blocks = self.repository.list_student_schedule_blocks(
                student_id=int(student_id),
                schedule_profile_id=int(schedule_profile_id),
                only_current_profile=True,
                external_provider="outlook",
            )
        except (
            MicrosoftGraphClientError,
            ScheduleRepositoryError,
            MicrosoftGraphStateRepositoryError,
        ) as exc:
            error_code = getattr(exc, "error_code", "outlook_fixed_schedule_sync_error")
            detail = getattr(exc, "detail", str(exc))
            return OutlookFixedScheduleSyncResult(
                synced=False,
                synced_event_map={
                    block.source_block_id: str(block.external_event_id)
                    for block in current_blocks
                    if block.external_event_id
                },
                error_code=error_code,
                detail=detail,
            )

        return OutlookFixedScheduleSyncResult(
            synced=True,
            upserted_count=len(upserted),
            deleted_count=len(deleted_ids),
            synced_event_map={
                block.source_block_id: str(block.external_event_id)
                for block in active_blocks
                if block.external_event_id and block.external_sync_status == "active"
            },
        )


def build_outlook_fixed_schedule_sync_service(
    *,
    schedule_repository: ScheduleRepository | None = None,
    state_repository: MicrosoftGraphStateRepository | None = None,
    auth_client: MicrosoftOAuthClient | None = None,
    client: OutlookCalendarClient | None = None,
) -> OutlookFixedScheduleSyncService:
    """Construye el servicio de sync del horario fijo hacia Outlook."""

    effective_schedule_repository = schedule_repository
    if effective_schedule_repository is None:
        effective_schedule_repository = build_schedule_repository(database_url_from_env())

    if state_repository is None:
        if isinstance(effective_schedule_repository, InMemoryScheduleRepository):
            state_repository = InMemoryMicrosoftGraphStateRepository()
        else:
            state_repository = build_microsoft_graph_state_repository(database_url_from_env())

    if auth_client is None:
        auth_client = build_microsoft_oauth_client_from_env(
            token_store=MicrosoftGraphStateTokenStore(state_repository)
        )

    return OutlookFixedScheduleSyncService(
        repository=effective_schedule_repository,
        state_repository=state_repository,
        auth_client=auth_client,
        client=client,
    )


def _ensure_calendar_state(calendar_state: CalendarState | dict | None) -> CalendarState:
    if isinstance(calendar_state, CalendarState):
        return calendar_state.model_copy(deep=True)
    return CalendarState(**dict(calendar_state or {}))


def _validate_calendar_state(
    calendar_state: CalendarState,
) -> OutlookFixedScheduleSyncResult | None:
    if calendar_state.provider and calendar_state.provider != "outlook":
        return OutlookFixedScheduleSyncResult(
            synced=False,
            synced_event_map=dict(calendar_state.synced_event_map),
            error_code="calendar_provider_not_outlook",
            detail="El proveedor configurado del calendario no es Outlook.",
        )
    return None


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
        raise MicrosoftGraphStateRepositoryError(
            "No existe conexión Microsoft persistida para guardar el calendar_id."
        )
    if not explicit_calendar_id or connection.calendar_id == explicit_calendar_id:
        return connection
    return state_repository.upsert_connection(
        record=replace(connection, calendar_id=explicit_calendar_id)
    )


def _storage_calendar_id(connection: MicrosoftGraphConnectionRecord) -> str:
    normalized = str(connection.calendar_id or "").strip()
    return normalized or _DEFAULT_CALENDAR_SCOPE_ID


def _active_sync_metadata(
    *,
    block: PersistedRecurringScheduleBlock,
    storage_calendar_id: str,
    external_change_key: str | None,
) -> dict[str, object]:
    series_start_date = resolve_series_start_date(block, timezone_name=block.timezone)
    metadata = dict(block.external_sync_metadata)
    metadata.update(
        {
            "calendar_id": storage_calendar_id,
            "series_start_date": series_start_date.isoformat(),
            "schedule_end_date": (
                block.schedule_end_date.isoformat()
                if block.schedule_end_date is not None
                else None
            ),
            "sync_scope": "fixed_schedule",
            "synced_at": _utc_now_iso(),
        }
    )
    if external_change_key:
        metadata["external_change_key"] = external_change_key
    return metadata


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


__all__ = [
    "OutlookFixedScheduleSyncResult",
    "OutlookFixedScheduleSyncService",
    "build_outlook_fixed_schedule_sync_service",
]
