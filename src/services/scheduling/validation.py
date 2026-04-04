"""Normalizacion y validacion reutilizable para eventos de scheduling."""

from __future__ import annotations

import re
import unicodedata
import uuid
from typing import Any

from schemas.common import Prioridad
from schemas.scheduling import Event

DAY_ORDER = [
    "Lunes",
    "Martes",
    "Miercoles",
    "Jueves",
    "Viernes",
    "Sabado",
    "Domingo",
]

DAY_ALIASES = {
    "l": "Lunes",
    "lu": "Lunes",
    "lun": "Lunes",
    "lunes": "Lunes",
    "ma": "Martes",
    "mar": "Martes",
    "martes": "Martes",
    "mi": "Miercoles",
    "mie": "Miercoles",
    "mier": "Miercoles",
    "miercoles": "Miercoles",
    "x": "Miercoles",
    "j": "Jueves",
    "ju": "Jueves",
    "jue": "Jueves",
    "jueves": "Jueves",
    "v": "Viernes",
    "vi": "Viernes",
    "vie": "Viernes",
    "viernes": "Viernes",
    "s": "Sabado",
    "sa": "Sabado",
    "sab": "Sabado",
    "sabado": "Sabado",
    "sabados": "Sabado",
    "d": "Domingo",
    "do": "Domingo",
    "dom": "Domingo",
    "domingo": "Domingo",
    "domingos": "Domingo",
}

EVENT_TYPES = {"confirmado", "tentativo"}
EVENT_CATEGORIES = {"academico", "laboral", "extracurricular", "estudio"}
PRIORIDADES: set[Prioridad] = {"alta", "media", "baja"}


def new_event_id() -> str:
    """Retorna un identificador unico para un Event."""

    return str(uuid.uuid4())


def normalize_time(value: str) -> str:
    """Normaliza tiempo a formato HH:MM en 24h."""

    if value is None:
        raise ValueError("time value is required")
    raw = str(value).strip().lower()
    if not raw:
        raise ValueError("time value is required")

    match = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*([ap]m)?$", raw)
    if not match:
        raise ValueError(f"invalid time format: {value!r}")

    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = match.group(3)

    if minute < 0 or minute > 59:
        raise ValueError(f"invalid minutes: {value!r}")

    if meridiem:
        if hour < 1 or hour > 12:
            raise ValueError(f"invalid hour: {value!r}")
        if meridiem == "am":
            hour = 0 if hour == 12 else hour
        else:
            hour = 12 if hour == 12 else hour + 12
    else:
        if hour < 0 or hour > 23:
            raise ValueError(f"invalid hour: {value!r}")

    return f"{hour:02d}:{minute:02d}"


def normalize_day(value: str) -> str:
    """Normaliza el dia a nombres canonicos en espanol."""

    if value is None:
        raise ValueError("day value is required")
    raw = str(value).strip().lower()
    if not raw:
        raise ValueError("day value is required")

    folded = unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")
    key = re.sub(r"[^a-z]", "", folded)
    if not key:
        raise ValueError(f"invalid day: {value!r}")

    normalized = DAY_ALIASES.get(key)
    if not normalized:
        raise ValueError(f"invalid day: {value!r}")
    return normalized


def validate_event(event: Event | dict[str, Any]) -> None:
    """Valida un Event por campos requeridos y formatos."""

    required = [
        "id",
        "dia",
        "inicio",
        "fin",
        "titulo",
        "tipo",
        "categoria",
        "origen",
        "timezone",
    ]
    for key in required:
        value = _event_value(event, key)
        if value in (None, ""):
            raise ValueError(f"missing required field: {key}")

    dia = _event_value(event, "dia")
    normalized_day = normalize_day(dia)
    if normalized_day != dia:
        raise ValueError("dia must be normalized to Lunes..Domingo")

    start = normalize_time(_event_value(event, "inicio"))
    end = normalize_time(_event_value(event, "fin"))
    if start != _event_value(event, "inicio") or end != _event_value(event, "fin"):
        raise ValueError("inicio/fin must be in HH:MM format")

    start_minutes = int(start[:2]) * 60 + int(start[3:])
    end_minutes = int(end[:2]) * 60 + int(end[3:])
    if start_minutes >= end_minutes:
        raise ValueError("inicio must be before fin")

    if _event_value(event, "tipo") not in EVENT_TYPES:
        raise ValueError("invalid event tipo")
    if _event_value(event, "categoria") not in EVENT_CATEGORIES:
        raise ValueError("invalid event categoria")

    prioridad = _event_value(event, "prioridad")
    if prioridad and prioridad not in PRIORIDADES:
        raise ValueError("invalid prioridad")
    dificultad = _event_value(event, "dificultad")
    if dificultad is not None:
        if not isinstance(dificultad, int) or not (1 <= dificultad <= 5):
            raise ValueError("dificultad must be int between 1 and 5")


def sort_events(events: list[Event]) -> list[Event]:
    """Retorna eventos ordenados por dia y hora de inicio."""

    order = {day: idx for idx, day in enumerate(DAY_ORDER)}

    def sort_key(item: Event) -> tuple[int, int]:
        raw_day = _event_value(item, "dia", "")
        try:
            normalized_day = normalize_day(raw_day)
        except ValueError:
            normalized_day = raw_day
        day_index = order.get(normalized_day, len(DAY_ORDER))
        time = normalize_time(_event_value(item, "inicio", "00:00"))
        minutes = int(time[:2]) * 60 + int(time[3:])
        return day_index, minutes

    return sorted(events, key=sort_key)


def _event_value(event: Event | dict[str, Any], key: str, default: Any = None) -> Any:
    if isinstance(event, dict):
        return event.get(key, default)
    return getattr(event, key, default)
