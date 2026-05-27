"""Reconciliación de sesiones de estudio sincronizadas contra Outlook."""

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

_DEFAULT_CALENDAR_SCOPE_ID = "__default__"


@dataclass(frozen=True)
class OutlookStudyCalendarReconciliationFinding:
    """Diferencia detectada entre una sesión materializada y Outlook."""

    source_instance_key: str
    external_event_id: str | None
    status: str
    title: str | None = None
    drift_fields: tuple[str, ...] = field(default_factory=tuple)
    detail: str | None = None
    external_change_key: str | None = None
    web_link: str | None = None


@dataclass(frozen=True)
class OutlookStudyCalendarReconciliationResult:
    """Resumen de reconciliación de sesiones de estudio en Outlook."""

    reconciled: bool
    study_plan_profile_id: int | None = None
    inspected_count: int = 0
    aligned_count: int = 0
    drifted_count: int = 0
    missing_count: int = 0
    unsynced_count: int = 0
    error_count: int = 0
    findings: tuple[OutlookStudyCalendarReconciliationFinding, ...] = ()
    error_code: str | None = None
    detail: str | None = None


class OutlookStudyCalendarReconciliationService:
    """Detecta cambios manuales en sesiones de estudio sincronizadas."""

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

    def reconcile_student_calendar(
        self,
        *,
        student_id: int | None,
        calendar_id: str | None = None,
        study_plan_profile_id: int | None = None,
    ) -> OutlookStudyCalendarReconciliationResult:
        if not student_id:
            return OutlookStudyCalendarReconciliationResult(
                reconciled=False,
                error_code="missing_student_id",
                detail="No encontré el estudiante persistido para reconciliar Outlook.",
            )

        try:
            connection = self.state_repository.get_connection(student_id=int(student_id))
        except (MicrosoftGraphStateRepositoryError, RepositoryConfigurationError) as exc:
            return OutlookStudyCalendarReconciliationResult(
                reconciled=False,
                error_code="microsoft_graph_state_error",
                detail=str(exc),
            )
        if connection is None:
            return OutlookStudyCalendarReconciliationResult(
                reconciled=False,
                error_code="microsoft_connection_not_found",
                detail="No existe una conexión Microsoft persistida para este estudiante.",
            )

        token_result = self.auth_client.get_valid_access_token(student_id=int(student_id))
        if not token_result.ok or token_result.token is None:
            return OutlookStudyCalendarReconciliationResult(
                reconciled=False,
                error_code=token_result.error_code or "microsoft_oauth_error",
                detail=token_result.detail,
            )

        try:
            instances = self.repository.list_instances(
                student_id=int(student_id),
                study_plan_profile_id=study_plan_profile_id,
            )
            resolved_calendar_id = _resolve_calendar_id(calendar_id, connection.calendar_id)
            storage_calendar_id = resolved_calendar_id or _DEFAULT_CALENDAR_SCOPE_ID
            links = self.state_repository.list_calendar_event_links(
                student_id=int(student_id),
                calendar_id=storage_calendar_id,
            )
        except (
            MicrosoftGraphSyncRepositoryError,
            MicrosoftGraphStateRepositoryError,
            RepositoryConfigurationError,
        ) as exc:
            return OutlookStudyCalendarReconciliationResult(
                reconciled=False,
                error_code="outlook_study_calendar_repository_error",
                detail=str(exc),
            )

        if not instances:
            return OutlookStudyCalendarReconciliationResult(
                reconciled=True,
                study_plan_profile_id=study_plan_profile_id,
            )

        instance_by_key = {instance.source_instance_key: instance for instance in instances}
        link_by_key = {link.source_instance_key: link for link in links}
        findings: list[OutlookStudyCalendarReconciliationFinding] = []
        link_updates: list[OutlookCalendarEventLinkRecord] = []
        aligned_count = 0
        drifted_count = 0
        missing_count = 0
        unsynced_count = 0
        error_count = 0

        for instance in instances:
            link = link_by_key.get(instance.source_instance_key)
            if link is None:
                unsynced_count += 1
                findings.append(
                    OutlookStudyCalendarReconciliationFinding(
                        source_instance_key=instance.source_instance_key,
                        external_event_id=None,
                        status="unsynced",
                        title=instance.title,
                        detail="La sesión todavía no tiene evento activo en Outlook.",
                    )
                )
                continue

            try:
                snapshot = self.client.get_event(
                    access_token=token_result.token.access_token,
                    calendar_id=resolved_calendar_id,
                    external_event_id=str(link.external_event_id),
                )
            except MicrosoftGraphClientError as exc:
                error_count += 1
                findings.append(
                    OutlookStudyCalendarReconciliationFinding(
                        source_instance_key=instance.source_instance_key,
                        external_event_id=link.external_event_id,
                        status="error",
                        title=instance.title,
                        detail=getattr(exc, "detail", str(exc)),
                    )
                )
                link_updates.append(_link_update(link, status="error", last_error=getattr(exc, "detail", str(exc))))
                continue

            if snapshot is None or snapshot.is_cancelled:
                missing_count += 1
                findings.append(
                    OutlookStudyCalendarReconciliationFinding(
                        source_instance_key=instance.source_instance_key,
                        external_event_id=link.external_event_id,
                        status="missing",
                        title=instance.title,
                        detail="No encontré la sesión en Outlook o fue cancelada manualmente.",
                    )
                )
                link_updates.append(_link_update(link, status="active", last_error="manual_missing"))
                continue

            drift_fields = _detect_study_session_drift(instance, link, snapshot)
            if drift_fields:
                drifted_count += 1
                findings.append(
                    OutlookStudyCalendarReconciliationFinding(
                        source_instance_key=instance.source_instance_key,
                        external_event_id=link.external_event_id,
                        status="drifted",
                        title=instance.title,
                        drift_fields=tuple(drift_fields),
                        detail="Se detectaron cambios manuales en Outlook.",
                        external_change_key=snapshot.external_change_key,
                        web_link=snapshot.web_link,
                    )
                )
                link_updates.append(
                    _link_update(
                        link,
                        status="active",
                        external_change_key=snapshot.external_change_key,
                        last_error=f"manual_drift:{','.join(drift_fields)}",
                    )
                )
                continue

            aligned_count += 1
            findings.append(
                OutlookStudyCalendarReconciliationFinding(
                    source_instance_key=instance.source_instance_key,
                    external_event_id=link.external_event_id,
                    status="active",
                    title=instance.title,
                    detail="La sesión sigue alineada con la fuente interna.",
                    external_change_key=snapshot.external_change_key,
                    web_link=snapshot.web_link,
                )
            )
            link_updates.append(
                _link_update(
                    link,
                    status="active",
                    external_change_key=snapshot.external_change_key,
                    last_error=None,
                )
            )

        orphan_links = [
            link for link in links if link.source_instance_key not in instance_by_key
        ]
        if orphan_links:
            try:
                self.state_repository.mark_calendar_event_links_deleted(
                    student_id=int(student_id),
                    source_instance_keys=[link.source_instance_key for link in orphan_links],
                )
            except MicrosoftGraphStateRepositoryError as exc:
                return OutlookStudyCalendarReconciliationResult(
                    reconciled=False,
                    study_plan_profile_id=study_plan_profile_id,
                    inspected_count=len(instances),
                    aligned_count=aligned_count,
                    drifted_count=drifted_count,
                    missing_count=missing_count,
                    unsynced_count=unsynced_count,
                    error_count=error_count,
                    findings=tuple(findings),
                    error_code="outlook_study_calendar_link_update_error",
                    detail=str(exc),
                )

        if link_updates:
            try:
                self.state_repository.upsert_calendar_event_links(links=link_updates)
            except MicrosoftGraphStateRepositoryError as exc:
                return OutlookStudyCalendarReconciliationResult(
                    reconciled=False,
                    study_plan_profile_id=study_plan_profile_id,
                    inspected_count=len(instances),
                    aligned_count=aligned_count,
                    drifted_count=drifted_count,
                    missing_count=missing_count,
                    unsynced_count=unsynced_count,
                    error_count=error_count,
                    findings=tuple(findings),
                    error_code="outlook_study_calendar_link_update_error",
                    detail=str(exc),
                )

        return OutlookStudyCalendarReconciliationResult(
            reconciled=True,
            study_plan_profile_id=study_plan_profile_id,
            inspected_count=len(instances),
            aligned_count=aligned_count,
            drifted_count=drifted_count,
            missing_count=missing_count,
            unsynced_count=unsynced_count,
            error_count=error_count,
            findings=tuple(findings),
        )

    def mark_missing_links_deleted(
        self,
        *,
        student_id: int | None,
        source_instance_keys: list[str],
    ) -> int:
        if not student_id or not source_instance_keys:
            return 0
        return self.state_repository.mark_calendar_event_links_deleted(
            student_id=int(student_id),
            source_instance_keys=source_instance_keys,
        )


def build_outlook_study_calendar_reconciliation_service(
    *,
    instances_repository: Any | None = None,
    state_repository: MicrosoftGraphStateRepository | None = None,
    auth_client: MicrosoftOAuthClient | None = None,
    client: OutlookCalendarClient | None = None,
) -> OutlookStudyCalendarReconciliationService:
    """Construye el servicio de reconciliación de sesiones de estudio."""

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

    return OutlookStudyCalendarReconciliationService(
        repository=repository,
        state_repository=state_repository,
        auth_client=auth_client,
        client=client,
    )


def _detect_study_session_drift(
    instance: MicrosoftSyncableStudyInstance,
    link: OutlookCalendarEventLinkRecord,
    snapshot: OutlookCalendarEventSnapshot,
) -> list[str]:
    drift_fields: list[str] = []
    if snapshot.subject != instance.title:
        drift_fields.append("subject")
    if _normalize_snapshot_datetime(snapshot.start) != _normalize_expected_datetime(instance.starts_at):
        drift_fields.append("start")
    if _normalize_snapshot_datetime(snapshot.end) != _normalize_expected_datetime(instance.ends_at):
        drift_fields.append("end")

    stored_change_key = str(link.external_change_key or "").strip()
    current_change_key = str(snapshot.external_change_key or "").strip()
    if stored_change_key and current_change_key and stored_change_key != current_change_key:
        drift_fields.append("external_change_key")
    return drift_fields


def _normalize_expected_datetime(value: datetime) -> tuple[str, str]:
    normalized = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    utc_value = normalized.astimezone(timezone.utc).replace(microsecond=0)
    return (utc_value.isoformat().replace("+00:00", "Z"), "UTC")


def _normalize_snapshot_datetime(payload: dict[str, str]) -> tuple[str, str]:
    return (
        str(payload.get("dateTime") or "").strip(),
        str(payload.get("timeZone") or "").strip() or "UTC",
    )


def _link_update(
    link: OutlookCalendarEventLinkRecord,
    *,
    status: str,
    external_change_key: str | None = None,
    last_error: str | None,
) -> OutlookCalendarEventLinkRecord:
    return OutlookCalendarEventLinkRecord(
        id=link.id,
        student_id=link.student_id,
        study_plan_event_instance_id=link.study_plan_event_instance_id,
        source_instance_key=link.source_instance_key,
        calendar_id=link.calendar_id,
        external_event_id=link.external_event_id,
        external_change_key=external_change_key if external_change_key is not None else link.external_change_key,
        sync_status=status,
        last_error=last_error,
        last_synced_at=link.last_synced_at,
    )


def _resolve_calendar_id(
    explicit_calendar_id: str | None,
    connection_calendar_id: str | None,
) -> str | None:
    for candidate in (explicit_calendar_id, connection_calendar_id):
        normalized = str(candidate or "").strip()
        if normalized:
            return normalized
    return None


__all__ = [
    "OutlookStudyCalendarReconciliationFinding",
    "OutlookStudyCalendarReconciliationResult",
    "OutlookStudyCalendarReconciliationService",
    "build_outlook_study_calendar_reconciliation_service",
]
