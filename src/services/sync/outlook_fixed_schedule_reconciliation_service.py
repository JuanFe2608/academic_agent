"""Reconciliación del horario fijo sincronizado contra Outlook Calendar."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

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
    OutlookCalendarEventSnapshot,
)
from repositories.microsoft_graph.state_repository import (
    InMemoryMicrosoftGraphStateRepository,
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
from services.sync.fixed_schedule_outlook_projection import (
    build_outlook_fixed_schedule_event,
)


@dataclass(frozen=True)
class OutlookFixedScheduleReconciliationFinding:
    """Diferencia detectada entre un bloque interno y Outlook."""

    block_id: int
    source_block_id: str
    external_event_id: str | None
    status: str
    drift_fields: tuple[str, ...] = field(default_factory=tuple)
    detail: str | None = None
    external_change_key: str | None = None
    web_link: str | None = None


@dataclass(frozen=True)
class OutlookFixedScheduleReconciliationResult:
    """Resumen operativo de una corrida de reconciliación."""

    reconciled: bool
    schedule_profile_id: int | None = None
    inspected_count: int = 0
    aligned_count: int = 0
    drifted_count: int = 0
    missing_count: int = 0
    unsynced_count: int = 0
    error_count: int = 0
    findings: tuple[OutlookFixedScheduleReconciliationFinding, ...] = ()
    error_code: str | None = None
    detail: str | None = None


class OutlookFixedScheduleReconciliationService:
    """Consulta Outlook y detecta drift manual sobre el horario fijo."""

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

    def reconcile_schedule_profile(
        self,
        *,
        student_id: int | None,
        schedule_profile_id: int | None = None,
        calendar_id: str | None = None,
    ) -> OutlookFixedScheduleReconciliationResult:
        if not student_id:
            return OutlookFixedScheduleReconciliationResult(
                reconciled=False,
                error_code="missing_student_id",
                detail="No encontré el estudiante persistido para reconciliar Outlook.",
            )

        try:
            connection = self.state_repository.get_connection(student_id=int(student_id))
        except (MicrosoftGraphStateRepositoryError, RepositoryConfigurationError) as exc:
            return OutlookFixedScheduleReconciliationResult(
                reconciled=False,
                error_code="microsoft_graph_state_error",
                detail=str(exc),
            )
        if connection is None:
            return OutlookFixedScheduleReconciliationResult(
                reconciled=False,
                error_code="microsoft_connection_not_found",
                detail=(
                    "No existe una conexión Microsoft persistida para este estudiante. "
                    "Completa OAuth antes de reconciliar Outlook."
                ),
            )

        token_result = self.auth_client.get_valid_access_token(student_id=int(student_id))
        if not token_result.ok or token_result.token is None:
            return OutlookFixedScheduleReconciliationResult(
                reconciled=False,
                error_code=token_result.error_code or "microsoft_oauth_error",
                detail=token_result.detail,
            )

        try:
            blocks = self.repository.list_student_schedule_blocks(
                student_id=int(student_id),
                schedule_profile_id=schedule_profile_id,
                only_current_profile=True if schedule_profile_id is None else None,
            )
        except (ScheduleRepositoryError, RepositoryConfigurationError) as exc:
            return OutlookFixedScheduleReconciliationResult(
                reconciled=False,
                error_code="outlook_fixed_schedule_repository_error",
                detail=str(exc),
            )

        candidate_blocks = [block for block in blocks if block.profile_is_current]
        if schedule_profile_id is None and candidate_blocks:
            schedule_profile_id = candidate_blocks[0].schedule_profile_id
        scoped_blocks = [
            block
            for block in candidate_blocks
            if schedule_profile_id is None or block.schedule_profile_id == int(schedule_profile_id)
        ]
        if not scoped_blocks:
            return OutlookFixedScheduleReconciliationResult(
                reconciled=False,
                schedule_profile_id=schedule_profile_id,
                error_code="empty_schedule_blocks",
                detail="No encontré bloques activos del horario fijo para reconciliar.",
            )

        findings: list[OutlookFixedScheduleReconciliationFinding] = []
        updates: list[RecurringScheduleBlockSyncUpdate] = []
        aligned_count = 0
        drifted_count = 0
        missing_count = 0
        unsynced_count = 0
        error_count = 0
        resolved_calendar_id = str(calendar_id or connection.calendar_id or "__default__").strip() or "__default__"

        for block in scoped_blocks:
            if block.external_provider != "outlook" or not str(block.external_event_id or "").strip():
                unsynced_count += 1
                findings.append(
                    OutlookFixedScheduleReconciliationFinding(
                        block_id=block.id,
                        source_block_id=block.source_block_id,
                        external_event_id=block.external_event_id,
                        status="unsynced",
                        detail="El bloque actual no tiene link activo hacia Outlook.",
                    )
                )
                updates.append(
                    _build_reconciliation_update(
                        block,
                        status="unsynced",
                        calendar_id=resolved_calendar_id,
                    )
                )
                continue

            try:
                snapshot = self.client.get_event(
                    access_token=token_result.token.access_token,
                    calendar_id=calendar_id or connection.calendar_id,
                    external_event_id=str(block.external_event_id),
                )
            except MicrosoftGraphClientError as exc:
                error_count += 1
                findings.append(
                    OutlookFixedScheduleReconciliationFinding(
                        block_id=block.id,
                        source_block_id=block.source_block_id,
                        external_event_id=block.external_event_id,
                        status="error",
                        detail=getattr(exc, "detail", str(exc)),
                    )
                )
                updates.append(
                    _build_reconciliation_update(
                        block,
                        status="error",
                        calendar_id=resolved_calendar_id,
                        detail=getattr(exc, "detail", str(exc)),
                    )
                )
                continue

            if snapshot is None or snapshot.is_cancelled:
                missing_count += 1
                findings.append(
                    OutlookFixedScheduleReconciliationFinding(
                        block_id=block.id,
                        source_block_id=block.source_block_id,
                        external_event_id=block.external_event_id,
                        status="missing",
                        detail="No encontré la serie en Outlook o fue cancelada manualmente.",
                    )
                )
                updates.append(
                    _build_reconciliation_update(
                        block,
                        status="missing",
                        calendar_id=resolved_calendar_id,
                        detail="Event missing or cancelled in Outlook.",
                    )
                )
                continue

            expected = build_outlook_fixed_schedule_event(block)
            drift_fields = _detect_drift_fields(block, expected, snapshot)
            status = "active" if not drift_fields else "drifted"
            if status == "active":
                aligned_count += 1
            else:
                drifted_count += 1

            findings.append(
                OutlookFixedScheduleReconciliationFinding(
                    block_id=block.id,
                    source_block_id=block.source_block_id,
                    external_event_id=block.external_event_id,
                    status=status,
                    drift_fields=tuple(drift_fields),
                    external_change_key=snapshot.external_change_key,
                    web_link=snapshot.web_link,
                    detail=(
                        "Se detectaron diferencias manuales en Outlook."
                        if drift_fields
                        else "El bloque sigue alineado con la fuente interna."
                    ),
                )
            )
            updates.append(
                _build_reconciliation_update(
                    block,
                    status=status,
                    calendar_id=resolved_calendar_id,
                    snapshot=snapshot,
                    drift_fields=drift_fields,
                )
            )

        try:
            self.repository.update_block_sync_metadata(updates=updates)
        except (ScheduleRepositoryError, RepositoryConfigurationError) as exc:
            return OutlookFixedScheduleReconciliationResult(
                reconciled=False,
                schedule_profile_id=schedule_profile_id,
                inspected_count=len(scoped_blocks),
                aligned_count=aligned_count,
                drifted_count=drifted_count,
                missing_count=missing_count,
                unsynced_count=unsynced_count,
                error_count=error_count,
                findings=tuple(findings),
                error_code="outlook_fixed_schedule_reconciliation_update_error",
                detail=str(exc),
            )

        return OutlookFixedScheduleReconciliationResult(
            reconciled=True,
            schedule_profile_id=schedule_profile_id,
            inspected_count=len(scoped_blocks),
            aligned_count=aligned_count,
            drifted_count=drifted_count,
            missing_count=missing_count,
            unsynced_count=unsynced_count,
            error_count=error_count,
            findings=tuple(findings),
        )


def build_outlook_fixed_schedule_reconciliation_service(
    *,
    schedule_repository: ScheduleRepository | None = None,
    state_repository: MicrosoftGraphStateRepository | None = None,
    auth_client: MicrosoftOAuthClient | None = None,
    client: OutlookCalendarClient | None = None,
) -> OutlookFixedScheduleReconciliationService:
    """Construye el servicio de reconciliación del horario fijo."""

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

    return OutlookFixedScheduleReconciliationService(
        repository=effective_schedule_repository,
        state_repository=state_repository,
        auth_client=auth_client,
        client=client,
    )


def _detect_drift_fields(
    block: PersistedRecurringScheduleBlock,
    expected,
    snapshot: OutlookCalendarEventSnapshot,
) -> list[str]:
    drift_fields: list[str] = []
    if snapshot.subject != expected.subject:
        drift_fields.append("subject")
    if _normalize_snapshot_datetime(snapshot.start) != _normalize_expected_datetime(expected.starts_at):
        drift_fields.append("start")
    if _normalize_snapshot_datetime(snapshot.end) != _normalize_expected_datetime(expected.ends_at):
        drift_fields.append("end")

    expected_recurrence = expected.recurrence
    recurrence = snapshot.recurrence or {}
    pattern = recurrence.get("pattern") if isinstance(recurrence.get("pattern"), dict) else {}
    range_payload = recurrence.get("range") if isinstance(recurrence.get("range"), dict) else {}
    if expected_recurrence is None:
        if recurrence:
            drift_fields.append("recurrence")
    else:
        if str(pattern.get("type") or "").strip() != expected_recurrence.pattern_type:
            drift_fields.append("recurrence.pattern_type")
        if int(pattern.get("interval") or 0) != expected_recurrence.interval:
            drift_fields.append("recurrence.interval")
        actual_days = sorted(str(day).strip().lower() for day in pattern.get("daysOfWeek") or [])
        expected_days = sorted(day.lower() for day in expected_recurrence.days_of_week)
        if actual_days != expected_days:
            drift_fields.append("recurrence.days_of_week")
        if str(range_payload.get("type") or "").strip() != expected_recurrence.range_type:
            drift_fields.append("recurrence.range_type")
        if str(range_payload.get("startDate") or "").strip() != expected_recurrence.start_date.isoformat():
            drift_fields.append("recurrence.start_date")
        actual_end_date = str(range_payload.get("endDate") or "").strip() or None
        expected_end_date = (
            expected_recurrence.end_date.isoformat()
            if expected_recurrence.end_date is not None
            else None
        )
        if actual_end_date != expected_end_date:
            drift_fields.append("recurrence.end_date")

    stored_change_key = str(block.external_sync_metadata.get("external_change_key") or "").strip()
    current_change_key = str(snapshot.external_change_key or "").strip()
    if stored_change_key and current_change_key and stored_change_key != current_change_key:
        drift_fields.append("external_change_key")
    return drift_fields


def _normalize_expected_datetime(value: datetime) -> tuple[str, str]:
    utc_value = value.astimezone(timezone.utc).replace(microsecond=0)
    return (utc_value.isoformat().replace("+00:00", "Z"), "UTC")


def _normalize_snapshot_datetime(payload: dict[str, str]) -> tuple[str, str]:
    return (
        str(payload.get("dateTime") or "").strip(),
        str(payload.get("timeZone") or "").strip() or "UTC",
    )


def _build_reconciliation_update(
    block: PersistedRecurringScheduleBlock,
    *,
    status: str,
    calendar_id: str,
    snapshot: OutlookCalendarEventSnapshot | None = None,
    drift_fields: list[str] | None = None,
    detail: str | None = None,
) -> RecurringScheduleBlockSyncUpdate:
    metadata = dict(block.external_sync_metadata)
    metadata.update(
        {
            "calendar_id": calendar_id,
            "reconciled_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "reconciliation_status": status,
            "reconciliation_detail": detail,
            "drift_fields": list(drift_fields or []),
        }
    )
    if snapshot is not None:
        metadata["external_change_key"] = snapshot.external_change_key
        metadata["outlook_web_link"] = snapshot.web_link
    return RecurringScheduleBlockSyncUpdate(
        block_id=block.id,
        external_provider="outlook",
        external_series_id=block.external_series_id,
        external_event_id=block.external_event_id,
        external_sync_status=status,
        external_sync_metadata=metadata,
    )


__all__ = [
    "OutlookFixedScheduleReconciliationFinding",
    "OutlookFixedScheduleReconciliationResult",
    "OutlookFixedScheduleReconciliationService",
    "build_outlook_fixed_schedule_reconciliation_service",
]
