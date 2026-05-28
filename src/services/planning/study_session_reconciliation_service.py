"""Detección de sesiones de estudio modificadas o eliminadas en Outlook Calendar.

Servicio READ-ONLY: solo detecta divergencias. La mutación ocurre en
apply_outlook_reconciliation (tools.py) cuando el estudiante confirma el cambio.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

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
    MicrosoftGraphStateRepository,
    MicrosoftGraphStateRepositoryError,
    build_microsoft_graph_state_repository,
)
from repositories.microsoft_graph.sync_repository import (
    InMemoryMicrosoftGraphSyncRepository,
    MicrosoftGraphSyncRepository,
    MicrosoftSyncableStudyInstance,
    build_microsoft_graph_sync_repository,
)


@dataclass
class StudySessionDrift:
    """Divergencia detectada entre una instancia del plan y Outlook Calendar."""

    instance_id: str
    session_title: str
    kind: Literal["moved", "deleted"]
    original_start: datetime
    original_end: datetime
    new_start: datetime | None
    new_end: datetime | None
    outlook_event_id: str


class StudySessionReconciliationService:
    """Detecta sesiones de estudio movidas o eliminadas manualmente en Outlook."""

    def __init__(
        self,
        *,
        sync_repository: MicrosoftGraphSyncRepository,
        state_repository: MicrosoftGraphStateRepository | None = None,
        auth_client: MicrosoftOAuthClient | None = None,
        client: OutlookCalendarClient | None = None,
    ) -> None:
        effective_state_repository = state_repository or InMemoryMicrosoftGraphStateRepository()
        self.sync_repository = sync_repository
        self.state_repository = effective_state_repository
        self.auth_client = auth_client or build_microsoft_oauth_client_from_env(
            token_store=MicrosoftGraphStateTokenStore(effective_state_repository)
        )
        self.client = client or GraphOutlookCalendarClient()

    def reconcile_for_student(
        self,
        student_id: int,
        lookahead_days: int = 14,
    ) -> list[StudySessionDrift]:
        try:
            connection = self.state_repository.get_connection(student_id=int(student_id))
        except (MicrosoftGraphStateRepositoryError, RepositoryConfigurationError):
            return []
        if connection is None:
            return []

        token_result = self.auth_client.get_valid_access_token(student_id=int(student_id))
        if not token_result.ok or token_result.token is None:
            return []

        try:
            instances = self.sync_repository.list_instances(student_id=int(student_id))
        except Exception:
            return []

        calendar_id = str(connection.calendar_id or "").strip() or None
        storage_calendar_id = calendar_id or "__default__"

        try:
            links = self.state_repository.list_calendar_event_links(
                student_id=int(student_id),
                calendar_id=storage_calendar_id,
            )
        except (MicrosoftGraphStateRepositoryError, RepositoryConfigurationError):
            return []

        link_by_key = {link.source_instance_key: link for link in links}

        now_utc = datetime.now(timezone.utc)
        horizon = now_utc.timestamp() + lookahead_days * 86400
        drifts: list[StudySessionDrift] = []

        for instance in instances:
            if not _instance_in_window(instance, now_utc.timestamp(), horizon):
                continue
            link = link_by_key.get(instance.source_instance_key)
            if link is None:
                continue

            try:
                snapshot = self.client.get_event(
                    access_token=token_result.token.access_token,
                    calendar_id=calendar_id,
                    external_event_id=str(link.external_event_id),
                )
            except MicrosoftGraphClientError:
                continue
            except Exception:
                continue

            if snapshot is None or snapshot.is_cancelled:
                drifts.append(
                    StudySessionDrift(
                        instance_id=instance.source_instance_key,
                        session_title=instance.title,
                        kind="deleted",
                        original_start=instance.starts_at,
                        original_end=instance.ends_at,
                        new_start=None,
                        new_end=None,
                        outlook_event_id=str(link.external_event_id),
                    )
                )
                continue

            if _dates_changed(instance, snapshot):
                new_start = _parse_snapshot_dt(snapshot.start)
                new_end = _parse_snapshot_dt(snapshot.end)
                drifts.append(
                    StudySessionDrift(
                        instance_id=instance.source_instance_key,
                        session_title=instance.title,
                        kind="moved",
                        original_start=instance.starts_at,
                        original_end=instance.ends_at,
                        new_start=new_start,
                        new_end=new_end,
                        outlook_event_id=str(link.external_event_id),
                    )
                )

        return drifts


def build_study_session_reconciliation_service(
    *,
    instances_repository: Any | None = None,
    state_repository: MicrosoftGraphStateRepository | None = None,
    auth_client: MicrosoftOAuthClient | None = None,
    client: OutlookCalendarClient | None = None,
) -> StudySessionReconciliationService:
    """Construye el servicio de detección de drift en Outlook Calendar."""

    if instances_repository is not None:
        sync_repository: MicrosoftGraphSyncRepository = InMemoryMicrosoftGraphSyncRepository(
            instances_repository=instances_repository
        )
    else:
        sync_repository = build_microsoft_graph_sync_repository(database_url_from_env())

    if state_repository is None:
        if instances_repository is not None:
            state_repository = InMemoryMicrosoftGraphStateRepository()
        else:
            state_repository = build_microsoft_graph_state_repository(database_url_from_env())

    if auth_client is None:
        auth_client = build_microsoft_oauth_client_from_env(
            token_store=MicrosoftGraphStateTokenStore(state_repository)
        )

    return StudySessionReconciliationService(
        sync_repository=sync_repository,
        state_repository=state_repository,
        auth_client=auth_client,
        client=client,
    )


def _instance_in_window(
    instance: MicrosoftSyncableStudyInstance,
    from_ts: float,
    to_ts: float,
) -> bool:
    try:
        starts = instance.starts_at
        if starts.tzinfo is None:
            starts = starts.replace(tzinfo=timezone.utc)
        ts = starts.astimezone(timezone.utc).timestamp()
        return from_ts <= ts <= to_ts
    except Exception:
        return False


def _dates_changed(
    instance: MicrosoftSyncableStudyInstance,
    snapshot: Any,
) -> bool:
    def _norm_expected(dt: datetime) -> str:
        normalized = dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
        return normalized.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    def _norm_snapshot(payload: dict[str, str]) -> str:
        raw = str(payload.get("dateTime") or "").strip()
        # Graph returns e.g. "2026-05-30T09:00:00.0000000" — strip trailing zeros
        if "." in raw:
            raw = raw.rstrip("0").rstrip(".")
        if raw and not raw.endswith("Z") and "+" not in raw:
            raw += "Z"
        return raw

    try:
        start_changed = _norm_snapshot(snapshot.start) != _norm_expected(instance.starts_at)
        end_changed = _norm_snapshot(snapshot.end) != _norm_expected(instance.ends_at)
        return start_changed or end_changed
    except Exception:
        return False


def _parse_snapshot_dt(payload: dict[str, str]) -> datetime | None:
    raw = str(payload.get("dateTime") or "").strip()
    if not raw:
        return None
    try:
        tz_name = str(payload.get("timeZone") or "UTC").strip()
        if "." in raw:
            raw = raw.rstrip("0").rstrip(".")
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            if tz_name.upper() == "UTC":
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                from zoneinfo import ZoneInfo
                try:
                    dt = dt.replace(tzinfo=ZoneInfo(tz_name))
                except Exception:
                    dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


__all__ = [
    "StudySessionDrift",
    "StudySessionReconciliationService",
    "build_study_session_reconciliation_service",
]
