"""Creación de eventos únicos (no recurrentes) en Outlook Calendar.

Separado del horario fijo recurrente: estos eventos se agendan solo para
una fecha específica y no modifican la tabla recurring_schedule_blocks.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
    OutlookCalendarEventUpsert,
)
from repositories.microsoft_graph.state_repository import (
    InMemoryMicrosoftGraphStateRepository,
    MicrosoftGraphStateRepository,
    MicrosoftGraphStateRepositoryError,
    build_microsoft_graph_state_repository,
)
from schemas.microsoft_graph import CalendarState

_EVENT_TYPE_CATEGORIES = {
    "extracurricular": "Evento Extracurricular",
    "academic": "Evento Académico",
    "work": "Evento Laboral",
}


@dataclass(frozen=True)
class OneTimeEventResult:
    """Resultado de intentar crear un evento único en Outlook Calendar."""

    created: bool
    external_event_id: str | None = None
    error_code: str | None = None
    detail: str | None = None


class OutlookOneTimeEventService:
    """Crea eventos únicos (no recurrentes) directamente en Outlook Calendar."""

    def __init__(
        self,
        *,
        state_repository: MicrosoftGraphStateRepository | None = None,
        auth_client: MicrosoftOAuthClient | None = None,
        client: OutlookCalendarClient | None = None,
    ) -> None:
        effective_repo = state_repository or InMemoryMicrosoftGraphStateRepository()
        self.state_repository = effective_repo
        self.auth_client = auth_client or build_microsoft_oauth_client_from_env(
            token_store=MicrosoftGraphStateTokenStore(effective_repo)
        )
        self.client = client or GraphOutlookCalendarClient()

    def create_event(
        self,
        *,
        student_id: int | None,
        calendar_state: CalendarState | dict | None = None,
        title: str,
        event_date: date,
        start_time: time,
        end_time: time,
        timezone: str = "America/Bogota",
        event_type: str = "extracurricular",
        calendar_id: str | None = None,
    ) -> OneTimeEventResult:
        """Crea un evento único en Outlook para la fecha indicada.

        No toca recurring_schedule_blocks — es un evento puntual en el calendario.
        """
        if not student_id:
            return OneTimeEventResult(
                created=False,
                error_code="missing_student_id",
                detail="No encontré el estudiante para sincronizar con Outlook.",
            )

        normalized_calendar = _ensure_calendar_state(calendar_state)
        resolved_calendar_id = calendar_id or normalized_calendar.calendar_id

        try:
            connection = self.state_repository.get_connection(student_id=int(student_id))
        except (MicrosoftGraphStateRepositoryError, RepositoryConfigurationError) as exc:
            return OneTimeEventResult(
                created=False,
                error_code="microsoft_graph_state_error",
                detail=str(exc),
            )
        if connection is None:
            return OneTimeEventResult(
                created=False,
                error_code="microsoft_connection_not_found",
                detail=(
                    "No existe una conexión Microsoft para este estudiante. "
                    "Completa el proceso de vinculación con Microsoft antes de sincronizar."
                ),
            )

        token_result = self.auth_client.get_valid_access_token(student_id=int(student_id))
        if not token_result.ok or token_result.token is None:
            return OneTimeEventResult(
                created=False,
                error_code=token_result.error_code or "microsoft_oauth_error",
                detail=token_result.detail,
            )

        try:
            zone = ZoneInfo(timezone)
        except ZoneInfoNotFoundError:
            zone = ZoneInfo("America/Bogota")

        starts_at = datetime.combine(event_date, start_time, zone)
        ends_at = datetime.combine(event_date, end_time, zone)
        type_label = _EVENT_TYPE_CATEGORIES.get(event_type, "Evento")

        body_preview = (
            f"Evento único creado por Academic Agent.\n"
            f"Tipo: {type_label}\n"
            f"Fecha: {event_date.isoformat()}\n"
            f"Horario: {start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}"
        )

        event_upsert = OutlookCalendarEventUpsert(
            external_key=str(uuid.uuid4()),
            subject=title,
            body_preview=body_preview,
            starts_at=starts_at,
            ends_at=ends_at,
            timezone=str(zone),
            categories=("AcademicAgentAI", "Evento Único", type_label),
            metadata={"student_id": student_id, "event_type": event_type},
            recurrence=None,
            use_local_timezone=True,
        )

        try:
            effective_calendar_id = resolved_calendar_id or connection.calendar_id
            results = self.client.upsert_events(
                access_token=token_result.token.access_token,
                calendar_id=effective_calendar_id,
                events=[event_upsert],
            )
            if results:
                return OneTimeEventResult(
                    created=True,
                    external_event_id=results[0].external_event_id,
                )
            return OneTimeEventResult(
                created=False,
                error_code="outlook_no_result",
                detail="Outlook no devolvió confirmación del evento creado.",
            )
        except MicrosoftGraphClientError as exc:
            return OneTimeEventResult(
                created=False,
                error_code=exc.error_code,
                detail=exc.detail,
            )
        except Exception as exc:
            return OneTimeEventResult(
                created=False,
                error_code="outlook_one_time_event_error",
                detail=str(exc),
            )


def build_outlook_one_time_event_service(
    *,
    state_repository: MicrosoftGraphStateRepository | None = None,
    auth_client: MicrosoftOAuthClient | None = None,
    client: OutlookCalendarClient | None = None,
) -> OutlookOneTimeEventService:
    if state_repository is None:
        state_repository = build_microsoft_graph_state_repository(database_url_from_env())
    if auth_client is None:
        auth_client = build_microsoft_oauth_client_from_env(
            token_store=MicrosoftGraphStateTokenStore(state_repository)
        )
    return OutlookOneTimeEventService(
        state_repository=state_repository,
        auth_client=auth_client,
        client=client,
    )


def _ensure_calendar_state(calendar_state: CalendarState | dict | None) -> CalendarState:
    if isinstance(calendar_state, CalendarState):
        return calendar_state.model_copy(deep=True)
    return CalendarState(**dict(calendar_state or {}))


__all__ = [
    "OneTimeEventResult",
    "OutlookOneTimeEventService",
    "build_outlook_one_time_event_service",
]
