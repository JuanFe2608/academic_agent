"""Reparación del horario fijo sincronizado hacia Outlook Calendar."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from bootstrap.errors import RepositoryConfigurationError
from bootstrap.settings import database_url_from_env
from integrations.microsoft_graph.auth_client import (
    MicrosoftGraphStateTokenStore,
    MicrosoftOAuthClient,
    build_microsoft_oauth_client_from_env,
)
from integrations.microsoft_graph.calendar_client import GraphOutlookCalendarClient
from integrations.microsoft_graph.models import OutlookCalendarClient
from repositories.microsoft_graph.state_repository import (
    InMemoryMicrosoftGraphStateRepository,
    MicrosoftGraphStateRepository,
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
from services.sync.outlook_fixed_schedule_reconciliation_service import (
    OutlookFixedScheduleReconciliationResult,
    OutlookFixedScheduleReconciliationService,
)
from services.sync.outlook_fixed_schedule_sync_service import (
    OutlookFixedScheduleSyncResult,
    OutlookFixedScheduleSyncService,
)

_REPAIRABLE_STATUSES = ("drifted", "missing")


@dataclass(frozen=True)
class OutlookFixedScheduleRepairResult:
    """Resumen operativo de una reparación de horario fijo en Outlook."""

    repaired: bool
    schedule_profile_id: int | None = None
    repairable_count: int = 0
    restored_count: int = 0
    recreated_count: int = 0
    skipped_count: int = 0
    synced_event_map: dict[str, str] = field(default_factory=dict)
    reconciliation_result: OutlookFixedScheduleReconciliationResult | None = None
    sync_result: OutlookFixedScheduleSyncResult | None = None
    error_code: str | None = None
    detail: str | None = None


class OutlookFixedScheduleRepairService:
    """Restaura Outlook usando PostgreSQL como fuente de verdad."""

    def __init__(
        self,
        *,
        repository: ScheduleRepository,
        reconciliation_service: OutlookFixedScheduleReconciliationService,
        sync_service: OutlookFixedScheduleSyncService,
    ) -> None:
        self.repository = repository
        self.reconciliation_service = reconciliation_service
        self.sync_service = sync_service

    def repair_schedule_profile(
        self,
        *,
        student_id: int | None,
        schedule_profile_id: int | None = None,
        calendar_state: CalendarState | dict | None = None,
        calendar_id: str | None = None,
        reconcile_first: bool = True,
        repair_statuses: tuple[str, ...] = _REPAIRABLE_STATUSES,
    ) -> OutlookFixedScheduleRepairResult:
        """Repara en Outlook los bloques marcados como `drifted` o `missing`."""

        if not student_id:
            return OutlookFixedScheduleRepairResult(
                repaired=False,
                error_code="missing_student_id",
                detail="No encontré el estudiante persistido para reparar Outlook.",
            )

        reconciliation_result: OutlookFixedScheduleReconciliationResult | None = None
        if reconcile_first:
            reconciliation_result = self.reconciliation_service.reconcile_schedule_profile(
                student_id=int(student_id),
                schedule_profile_id=schedule_profile_id,
                calendar_id=calendar_id,
            )
            if not reconciliation_result.reconciled:
                return OutlookFixedScheduleRepairResult(
                    repaired=False,
                    schedule_profile_id=schedule_profile_id,
                    reconciliation_result=reconciliation_result,
                    error_code=reconciliation_result.error_code,
                    detail=reconciliation_result.detail,
                )
            schedule_profile_id = reconciliation_result.schedule_profile_id or schedule_profile_id

        if schedule_profile_id is None:
            schedule_profile_id = self._resolve_current_schedule_profile_id(student_id=int(student_id))
        if schedule_profile_id is None:
            return OutlookFixedScheduleRepairResult(
                repaired=False,
                error_code="current_schedule_profile_not_found",
                detail="No encontré un horario fijo actual para reparar.",
            )

        try:
            blocks = self.repository.list_student_schedule_blocks(
                student_id=int(student_id),
                schedule_profile_id=int(schedule_profile_id),
                only_current_profile=True,
            )
        except (ScheduleRepositoryError, RepositoryConfigurationError) as exc:
            return OutlookFixedScheduleRepairResult(
                repaired=False,
                schedule_profile_id=schedule_profile_id,
                error_code="outlook_fixed_schedule_repair_repository_error",
                detail=str(exc),
            )

        repairable_statuses = {str(status).strip() for status in repair_statuses}
        target_blocks = [
            block
            for block in blocks
            if str(block.external_sync_status or "").strip() in repairable_statuses
        ]
        if not target_blocks:
            return OutlookFixedScheduleRepairResult(
                repaired=True,
                schedule_profile_id=schedule_profile_id,
                skipped_count=len(blocks),
                reconciliation_result=reconciliation_result,
                detail="No hay bloques con drift o missing para reparar.",
            )

        missing_blocks = [
            block
            for block in target_blocks
            if str(block.external_sync_status or "").strip() == "missing"
        ]
        if missing_blocks:
            prepare_result = self._prepare_missing_blocks_for_recreation(missing_blocks)
            if prepare_result is not None:
                return OutlookFixedScheduleRepairResult(
                    repaired=False,
                    schedule_profile_id=schedule_profile_id,
                    repairable_count=len(target_blocks),
                    reconciliation_result=reconciliation_result,
                    error_code="outlook_fixed_schedule_repair_prepare_error",
                    detail=prepare_result,
                )

        sync_result = self.sync_service.sync_schedule_profile(
            student_id=int(student_id),
            schedule_profile_id=int(schedule_profile_id),
            calendar_state=calendar_state,
            calendar_id=calendar_id,
            target_block_ids={block.id for block in target_blocks},
            delete_stale_blocks=False,
        )
        if not sync_result.synced:
            if missing_blocks:
                self._rollback_missing_block_links(
                    missing_blocks,
                    reason=sync_result.detail or sync_result.error_code or "sync_failed",
                )
            return OutlookFixedScheduleRepairResult(
                repaired=False,
                schedule_profile_id=schedule_profile_id,
                repairable_count=len(target_blocks),
                reconciliation_result=reconciliation_result,
                sync_result=sync_result,
                error_code=sync_result.error_code,
                detail=sync_result.detail,
            )

        restored_count = sum(
            1
            for block in target_blocks
            if str(block.external_sync_status or "").strip() == "drifted"
        )
        return OutlookFixedScheduleRepairResult(
            repaired=True,
            schedule_profile_id=schedule_profile_id,
            repairable_count=len(target_blocks),
            restored_count=restored_count,
            recreated_count=len(missing_blocks),
            skipped_count=max(0, len(blocks) - len(target_blocks)),
            synced_event_map=dict(sync_result.synced_event_map),
            reconciliation_result=reconciliation_result,
            sync_result=sync_result,
        )

    def _resolve_current_schedule_profile_id(self, *, student_id: int) -> int | None:
        try:
            profile = self.repository.get_current_schedule_profile(student_id=student_id)
        except (ScheduleRepositoryError, RepositoryConfigurationError):
            return None
        if profile is None:
            return None
        return int(profile.id)

    def _prepare_missing_blocks_for_recreation(
        self,
        blocks: list[PersistedRecurringScheduleBlock],
    ) -> str | None:
        try:
            self.repository.update_block_sync_metadata(
                updates=[
                    RecurringScheduleBlockSyncUpdate(
                        block_id=block.id,
                        external_provider="outlook",
                        external_series_id=None,
                        external_event_id=None,
                        external_sync_status="deleted",
                        external_sync_metadata={
                            **dict(block.external_sync_metadata),
                            "repair_previous_external_series_id": block.external_series_id,
                            "repair_previous_external_event_id": block.external_event_id,
                            "repair_prepared_recreate_at": _utc_now_iso(),
                        },
                    )
                    for block in blocks
                ]
            )
        except (ScheduleRepositoryError, RepositoryConfigurationError) as exc:
            return str(exc)
        return None

    def _rollback_missing_block_links(
        self,
        blocks: list[PersistedRecurringScheduleBlock],
        *,
        reason: str,
    ) -> None:
        try:
            self.repository.update_block_sync_metadata(
                updates=[
                    RecurringScheduleBlockSyncUpdate(
                        block_id=block.id,
                        external_provider="outlook",
                        external_series_id=block.external_series_id,
                        external_event_id=block.external_event_id,
                        external_sync_status="missing",
                        external_sync_metadata={
                            **dict(block.external_sync_metadata),
                            "repair_rollback_at": _utc_now_iso(),
                            "repair_rollback_reason": reason,
                        },
                    )
                    for block in blocks
                ]
            )
        except (ScheduleRepositoryError, RepositoryConfigurationError):
            return


def build_outlook_fixed_schedule_repair_service(
    *,
    schedule_repository: ScheduleRepository | None = None,
    state_repository: MicrosoftGraphStateRepository | None = None,
    auth_client: MicrosoftOAuthClient | None = None,
    client: OutlookCalendarClient | None = None,
) -> OutlookFixedScheduleRepairService:
    """Construye el servicio de reparación del horario fijo."""

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

    effective_client = client or GraphOutlookCalendarClient()
    reconciliation_service = OutlookFixedScheduleReconciliationService(
        repository=effective_schedule_repository,
        state_repository=state_repository,
        auth_client=auth_client,
        client=effective_client,
    )
    sync_service = OutlookFixedScheduleSyncService(
        repository=effective_schedule_repository,
        state_repository=state_repository,
        auth_client=auth_client,
        client=effective_client,
    )
    return OutlookFixedScheduleRepairService(
        repository=effective_schedule_repository,
        reconciliation_service=reconciliation_service,
        sync_service=sync_service,
    )


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


__all__ = [
    "OutlookFixedScheduleRepairResult",
    "OutlookFixedScheduleRepairService",
    "build_outlook_fixed_schedule_repair_service",
]
