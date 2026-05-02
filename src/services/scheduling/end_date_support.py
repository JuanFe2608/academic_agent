"""Helpers compartidos para fechas límite de horarios fijos."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

_ISO_DATE_PATTERN = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})\s*$")
_DAY_FIRST_DATE_PATTERN = re.compile(r"^\s*(\d{1,2})[\/\-\s]+(\d{1,2})[\/\-\s]+(\d{2}|\d{4})\s*$")

SCHEDULE_END_DATE_MAX_MONTHS: int = 7


def parse_schedule_end_date(
    text: str | None,
    *,
    timezone_name: str,
    min_date: date | None = None,
    max_months: int = SCHEDULE_END_DATE_MAX_MONTHS,
) -> date | None:
    """Interpreta y valida una fecha límite del horario fijo.

    Reglas:
    - Debe ser estrictamente futura (mínimo mañana).
    - No puede exceder max_months meses desde hoy (defecto: 7 meses).
    Retorna None si el texto no es parseable o viola cualquiera de las reglas.
    """

    raw = str(text or "").strip()
    if not raw:
        return None

    parsed = _parse_known_date(raw)
    if parsed is None:
        return None

    today = current_local_date(timezone_name)
    effective_min = min_date if min_date is not None else today + timedelta(days=1)
    if parsed < effective_min:
        return None

    max_date = _add_months(today, max_months)
    if parsed > max_date:
        return None

    return parsed


def schedule_end_date_max_date(
    timezone_name: str,
    max_months: int = SCHEDULE_END_DATE_MAX_MONTHS,
) -> date:
    """Retorna la fecha límite máxima permitida (hoy + max_months meses)."""
    return _add_months(current_local_date(timezone_name), max_months)


def current_local_date(timezone_name: str) -> date:
    """Retorna la fecha local actual según la zona horaria indicada."""

    return datetime.now(ZoneInfo(timezone_name or "America/Bogota")).date()


def is_schedule_expired(
    schedule_end_date: date | None,
    *,
    timezone_name: str,
) -> bool:
    """Indica si la fecha límite del horario ya expiró en la zona local."""

    if schedule_end_date is None:
        return False
    return current_local_date(timezone_name) > schedule_end_date


def format_schedule_end_date(value: date | None) -> str:
    """Formatea una fecha límite para mensajes de usuario."""

    if value is None:
        return "sin fecha límite"
    return value.strftime("%d/%m/%Y")


def _add_months(d: date, months: int) -> date:
    """Suma N meses a una fecha, ajustando al último día del mes si es necesario."""
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    import calendar
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day))


def _parse_known_date(raw: str) -> date | None:
    iso_match = _ISO_DATE_PATTERN.match(raw)
    if iso_match is not None:
        year, month, day = (int(part) for part in iso_match.groups())
        return _safe_date(year, month, day)

    day_first_match = _DAY_FIRST_DATE_PATTERN.match(raw)
    if day_first_match is not None:
        day, month = (int(part) for part in day_first_match.groups()[:2])
        year = _normalize_year(int(day_first_match.group(3)))
        return _safe_date(year, month, day)

    return None


def _normalize_year(year: int) -> int:
    if 0 <= year <= 99:
        return 2000 + year
    return year


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


__all__ = [
    "SCHEDULE_END_DATE_MAX_MONTHS",
    "current_local_date",
    "format_schedule_end_date",
    "is_schedule_expired",
    "parse_schedule_end_date",
    "schedule_end_date_max_date",
]
