"""Utilidades para resolver eventos semanales a fechas concretas."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from schemas.scheduling import Event
from services.scheduling.validation import DAY_ORDER, normalize_time

MONTH_NAMES = {
    1: "Enero",
    2: "Febrero",
    3: "Marzo",
    4: "Abril",
    5: "Mayo",
    6: "Junio",
    7: "Julio",
    8: "Agosto",
    9: "Septiembre",
    10: "Octubre",
    11: "Noviembre",
    12: "Diciembre",
}

MONTH_SHORT_NAMES = {
    1: "Ene",
    2: "Feb",
    3: "Mar",
    4: "Abr",
    5: "May",
    6: "Jun",
    7: "Jul",
    8: "Ago",
    9: "Sep",
    10: "Oct",
    11: "Nov",
    12: "Dic",
}


@dataclass(frozen=True)
class WeekDaySlot:
    """Representa un dia concreto de la semana visible."""

    day_name: str
    day_date: date


@dataclass(frozen=True)
class ScheduledOccurrence:
    """Evento con fecha concreta dentro de la semana visible."""

    event: Event
    week_date: date
    start_at: datetime
    end_at: datetime


def get_reference_now(timezone_name: str, reference: datetime | None = None) -> datetime:
    """Retorna la fecha/hora base de la zona horaria configurada."""
    zone = ZoneInfo(timezone_name)
    if reference is None:
        return datetime.now(zone)
    if reference.tzinfo is None:
        return reference.replace(tzinfo=zone)
    return reference.astimezone(zone)


def build_current_week_slots(
    timezone_name: str,
    reference: datetime | None = None,
) -> list[WeekDaySlot]:
    """Construye la semana actual de lunes a domingo usando la fecha local."""
    local_now = get_reference_now(timezone_name, reference)
    monday = local_now.date() - timedelta(days=local_now.weekday())
    return [
        WeekDaySlot(day_name=day_name, day_date=monday + timedelta(days=index))
        for index, day_name in enumerate(DAY_ORDER)
    ]


def resolve_weekly_events_to_current_week(
    events: list[Event],
    timezone_name: str,
    reference: datetime | None = None,
) -> tuple[list[WeekDaySlot], list[ScheduledOccurrence]]:
    """Mapea eventos semanales a ocurrencias concretas de la semana actual."""
    slots = build_current_week_slots(timezone_name, reference)
    date_by_day = {slot.day_name: slot.day_date for slot in slots}
    occurrences: list[ScheduledOccurrence] = []
    zone = ZoneInfo(timezone_name)

    for event in events:
        week_date = date_by_day.get(event.get("dia"))
        if week_date is None:
            continue
        start_at = datetime.combine(week_date, _to_time(event.get("inicio", "00:00")), zone)
        end_at = datetime.combine(week_date, _to_time(event.get("fin", "00:00")), zone)
        if end_at <= start_at:
            end_at = end_at + timedelta(days=1)
        occurrences.append(
            ScheduledOccurrence(
                event=event,
                week_date=week_date,
                start_at=start_at,
                end_at=end_at,
            )
        )
    return slots, occurrences


def format_week_title(slots: list[WeekDaySlot]) -> str:
    """Retorna un titulo legible para la semana visible."""
    if not slots:
        return ""
    start_date = slots[0].day_date
    end_date = slots[-1].day_date
    if start_date.month == end_date.month and start_date.year == end_date.year:
        month = MONTH_NAMES[start_date.month]
        return f"Semana del {start_date.day} al {end_date.day} de {month} de {start_date.year}"
    if start_date.year == end_date.year:
        start_month = MONTH_NAMES[start_date.month]
        end_month = MONTH_NAMES[end_date.month]
        return (
            f"Semana del {start_date.day} de {start_month} al "
            f"{end_date.day} de {end_month} de {start_date.year}"
        )
    start_month = MONTH_NAMES[start_date.month]
    end_month = MONTH_NAMES[end_date.month]
    return (
        f"Semana del {start_date.day} de {start_month} de {start_date.year} al "
        f"{end_date.day} de {end_month} de {end_date.year}"
    )


def format_day_header(slot: WeekDaySlot) -> tuple[str, str]:
    """Devuelve lineas cortas para mostrar un dia con fecha completa."""
    first_line = slot.day_name
    second_line = f"{slot.day_date.day:02d} {MONTH_SHORT_NAMES[slot.day_date.month]} {slot.day_date.year}"
    return first_line, second_line


def format_day_label(slot: WeekDaySlot) -> str:
    """Texto largo para la vista previa textual."""
    return f"{slot.day_name} {slot.day_date.day:02d}/{slot.day_date.month:02d}/{slot.day_date.year}"


def _to_time(value: str) -> time:
    normalized = normalize_time(value)
    return time.fromisoformat(normalized)
