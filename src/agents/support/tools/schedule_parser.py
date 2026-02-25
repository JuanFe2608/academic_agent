"""Herramientas minimas para analizar horarios laborales en texto.

Un parser es un componente que interpreta texto y lo transforma en una
estructura de datos util. Aqui convertimos entradas simples en eventos
estandar usando utilidades del state.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Iterable

from agents.support.state import DAY_ORDER, Event, new_event_id, normalize_day, normalize_time

_DAY_TOKEN_PATTERN = (
    r"(?:"
    r"lunes|lun|l|"
    r"martes|mar|ma|"
    r"miercoles|mier|mie|mi|x|"
    r"jueves|jue|ju|j|"
    r"viernes|vie|vi|v|"
    r"sabados|sabado|sab|sa|s|"
    r"domingo|dom|do|d"
    r")"
)

_RANGE_PATTERN = re.compile(
    rf"\b({_DAY_TOKEN_PATTERN})\b\s*(?:-|a|hasta)\s*\b({_DAY_TOKEN_PATTERN})\b"
)
_SINGLE_DAY_PATTERN = re.compile(rf"\b({_DAY_TOKEN_PATTERN})\b")
_TIME_RANGE_PATTERN = re.compile(
    r"(\d{1,2}(?::\d{2})?\s*(?:[ap]m?)?)\s*(?:-|a|hasta)\s*(\d{1,2}(?::\d{2})?\s*(?:[ap]m?)?)"
)


def parse_work_schedule_text(
    text: str, timezone: str = "America/Bogota"
) -> list[Event]:
    """Analiza texto de horario laboral y retorna eventos estandar.

    Soporta rangos de dias (L-V) y dias individuales con horas en formato
    "7am", "7:30 am" o "19:00".
    """

    if text is None or not str(text).strip():
        return []

    normalized = _strip_accents(str(text).lower())
    start_raw, end_raw = _extract_time_range(normalized)
    start = normalize_time(start_raw)
    end = normalize_time(end_raw)
    days = _extract_days(normalized)

    events: list[Event] = []
    for day in days:
        events.append(
            {
                "id": new_event_id(),
                "dia": day,
                "inicio": start,
                "fin": end,
                "titulo": "Trabajo",
                "tipo": "confirmado",
                "categoria": "laboral",
                "origen": "user_text",
                "timezone": timezone,
            }
        )
    return events


def _strip_accents(value: str) -> str:
    """Elimina acentos para facilitar la deteccion de dias."""
    return (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
    )


def _extract_time_range(text: str) -> tuple[str, str]:
    """Extrae el rango de horas desde el texto normalizado."""
    match = _TIME_RANGE_PATTERN.search(text)
    if not match:
        raise ValueError("no time range found")
    return match.group(1), match.group(2)


def _extract_days(text: str) -> list[str]:
    """Extrae dias desde un rango o un dia individual."""
    range_match = _RANGE_PATTERN.search(text)
    if range_match:
        start_token, end_token = range_match.group(1), range_match.group(2)
        start_day = _normalize_day_token(start_token)
        end_day = _normalize_day_token(end_token)
        return _expand_day_range(start_day, end_day)

    single_match = _SINGLE_DAY_PATTERN.search(text)
    if not single_match:
        raise ValueError("no day found")
    return [_normalize_day_token(single_match.group(1))]


def _normalize_day_token(token: str) -> str:
    """Normaliza un token de dia y permite plural simple."""
    try:
        return normalize_day(token)
    except ValueError:
        if token.endswith("s") and len(token) > 1:
            return normalize_day(token[:-1])
        raise


def _expand_day_range(start_day: str, end_day: str) -> list[str]:
    """Expande un rango de dias respetando el orden semanal."""
    order = list(DAY_ORDER)
    start_index = order.index(start_day)
    end_index = order.index(end_day)
    if start_index <= end_index:
        return order[start_index : end_index + 1]
    return order[start_index:] + order[: end_index + 1]
