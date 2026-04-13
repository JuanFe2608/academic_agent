"""Helpers compartidos para fechas límite de horarios fijos."""

from __future__ import annotations

import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

_ISO_DATE_PATTERN = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})\s*$")
_DAY_FIRST_DATE_PATTERN = re.compile(r"^\s*(\d{1,2})[/-](\d{1,2})[/-](\d{4})\s*$")


def parse_schedule_end_date(
    text: str | None,
    *,
    timezone_name: str,
    min_date: date | None = None,
) -> date | None:
    """Interpreta una fecha límite en formatos simples y seguros."""

    raw = str(text or "").strip()
    if not raw:
        return None

    parsed = _parse_known_date(raw)
    if parsed is None:
        return None

    effective_min_date = min_date or current_local_date(timezone_name)
    if parsed < effective_min_date:
        return None
    return parsed


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


def _parse_known_date(raw: str) -> date | None:
    iso_match = _ISO_DATE_PATTERN.match(raw)
    if iso_match is not None:
        year, month, day = (int(part) for part in iso_match.groups())
        return _safe_date(year, month, day)

    day_first_match = _DAY_FIRST_DATE_PATTERN.match(raw)
    if day_first_match is not None:
        day, month, year = (int(part) for part in day_first_match.groups())
        return _safe_date(year, month, day)

    return None


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


__all__ = [
    "current_local_date",
    "format_schedule_end_date",
    "is_schedule_expired",
    "parse_schedule_end_date",
]
