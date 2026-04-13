"""Helpers compartidos para proyectar horario fijo hacia Outlook."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from integrations.microsoft_graph.models import (
    OutlookCalendarEventUpsert,
    OutlookEventRecurrence,
)
from repositories.scheduling.repository import PersistedRecurringScheduleBlock

_DAY_TO_WEEKDAY_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}
_BLOCK_TYPE_CATEGORIES = {
    "academic": "Horario Academico",
    "work": "Horario Laboral",
    "extracurricular": "Horario Extracurricular",
}


def build_outlook_fixed_schedule_event(
    block: PersistedRecurringScheduleBlock,
) -> OutlookCalendarEventUpsert:
    """Convierte un bloque recurrente persistido en su proyección Outlook."""

    timezone_name = str(block.timezone or "America/Bogota")
    series_start_date = resolve_series_start_date(block, timezone_name=timezone_name)
    start_time = time.fromisoformat(block.start_time)
    end_time = time.fromisoformat(block.end_time)
    zone = ZoneInfo(timezone_name)
    starts_at = datetime.combine(series_start_date, start_time, zone)
    ends_at = datetime.combine(series_start_date, end_time, zone)

    return OutlookCalendarEventUpsert(
        external_key=block.source_block_id,
        subject=block.title,
        body_preview=build_outlook_fixed_schedule_body_preview(block),
        starts_at=starts_at,
        ends_at=ends_at,
        timezone=timezone_name,
        categories=(
            "AcademicAgentAI",
            "Horario Fijo",
            _BLOCK_TYPE_CATEGORIES.get(block.block_type, "Horario"),
        ),
        metadata={
            "schedule_profile_id": block.schedule_profile_id,
            "block_id": block.id,
            "series_start_date": series_start_date.isoformat(),
        },
        recurrence=OutlookEventRecurrence(
            pattern_type="weekly",
            interval=1,
            days_of_week=(block.day_of_week,),
            start_date=series_start_date,
            range_type="endDate" if block.schedule_end_date is not None else "noEnd",
            end_date=block.schedule_end_date,
        ),
        use_local_timezone=True,
        existing_external_event_id=(
            block.external_event_id
            if block.external_provider == "outlook"
            and block.external_sync_status != "deleted"
            else None
        ),
    )


def resolve_series_start_date(
    block: PersistedRecurringScheduleBlock,
    *,
    timezone_name: str,
) -> date:
    """Calcula la fecha inicial de la serie semanal en Outlook."""

    raw_start_date = block.external_sync_metadata.get("series_start_date")
    if isinstance(raw_start_date, str):
        try:
            return date.fromisoformat(raw_start_date)
        except ValueError:
            pass

    zone = ZoneInfo(timezone_name)
    local_now = datetime.now(zone)
    target_weekday = _DAY_TO_WEEKDAY_INDEX[str(block.day_of_week)]
    days_ahead = (target_weekday - local_now.weekday()) % 7
    candidate_date = local_now.date() + timedelta(days=days_ahead)
    start_at = datetime.combine(candidate_date, time.fromisoformat(block.start_time), zone)
    if start_at <= local_now:
        candidate_date = candidate_date + timedelta(days=7)
    if block.schedule_end_date is not None and candidate_date > block.schedule_end_date:
        days_back = (block.schedule_end_date.weekday() - target_weekday) % 7
        return block.schedule_end_date - timedelta(days=days_back)
    return candidate_date


def build_outlook_fixed_schedule_body_preview(
    block: PersistedRecurringScheduleBlock,
) -> str:
    """Arma el cuerpo textual del evento sincronizado."""

    type_label = _BLOCK_TYPE_CATEGORIES.get(block.block_type, "Horario")
    return (
        "Horario fijo confirmado por el estudiante.\n"
        f"Categoria: {type_label}\n"
        f"Bloque: {block.day_of_week} {block.start_time}-{block.end_time}\n"
        f"Perfil horario: {block.schedule_profile_id}\n"
        f"Bloque interno: {block.source_block_id}"
    )


__all__ = [
    "build_outlook_fixed_schedule_body_preview",
    "build_outlook_fixed_schedule_event",
    "resolve_series_start_date",
]
