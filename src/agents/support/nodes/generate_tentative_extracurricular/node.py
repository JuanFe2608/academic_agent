"""Nodo para generar eventos tentativos de extracurriculares variables."""

from __future__ import annotations

import re

from agents.support.nodes.utils import normalize_text
from agents.support.state import DAY_ORDER, AgentState, Event, ExtracurricularItem, validate_event
from agents.support.state import new_event_id, normalize_day, normalize_time

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
_COUNT_PATTERN = re.compile(r"(\d+)\s*veces")


def generate_tentative_extracurricular(state: AgentState) -> dict:
    """Genera eventos tentativos para actividades variables."""
    timezone = state.get("timezone", "America/Bogota")
    events: list[Event] = list(state.get("events", []))
    errors = list(state.get("errors", []))
    extracurricular_updated: list[ExtracurricularItem] = []

    for item in state.get("extracurricular", []):
        updated_item = _ensure_extracurricular_item(item)
        tentativos: list[Event] = []
        if item.get("es_variable"):
            tentativos = build_tentative_events(item, timezone)
            for event in tentativos:
                try:
                    validate_event(event)
                except ValueError as exc:
                    errors.append(f"Tentativo extracurricular invalido: {exc}")
                    continue
                events.append(event)
        updated_item.tentativo = tentativos
        extracurricular_updated.append(updated_item)

    return {
        "extracurricular": extracurricular_updated,
        "events": events,
        "errors": errors,
        "phase": "draft",
    }


def build_tentative_events(item: ExtracurricularItem, timezone: str) -> list[Event]:
    """Crea eventos tentativos con una heuristica simple."""
    detail = str(item.get("detalle", ""))
    day_candidates = _extract_days(detail)
    count = _extract_count(detail)
    start_time = _extract_start_time(detail)
    end_time = _add_minutes(start_time, 60)

    if not day_candidates:
        day_candidates = ["Lunes", "Miercoles", "Viernes"]
    if count <= 0:
        count = min(2, len(day_candidates))

    selected_days = _pick_days(day_candidates, count)
    events: list[Event] = []
    for day in selected_days:
        events.append(
            Event(
                id=new_event_id(),
                dia=day,
                inicio=start_time,
                fin=end_time,
                titulo=item.get("nombre", "Extracurricular"),
                tipo="tentativo",
                categoria="extracurricular",
                origen="agent",
                timezone=timezone,
            )
        )
    return events


def _ensure_extracurricular_item(item: ExtracurricularItem | dict) -> ExtracurricularItem:
    if isinstance(item, ExtracurricularItem):
        return item
    return ExtracurricularItem(**item)


def _extract_days(text: str) -> list[str]:
    normalized = normalize_text(text)
    range_match = _RANGE_PATTERN.search(normalized)
    if range_match:
        start_day = _normalize_day_token(range_match.group(1))
        end_day = _normalize_day_token(range_match.group(2))
        return _expand_day_range(start_day, end_day)

    single_match = _SINGLE_DAY_PATTERN.search(normalized)
    if single_match:
        return [_normalize_day_token(single_match.group(1))]
    return []


def _normalize_day_token(token: str) -> str:
    try:
        return normalize_day(token)
    except ValueError:
        if token.endswith("s") and len(token) > 1:
            return normalize_day(token[:-1])
        raise


def _expand_day_range(start_day: str, end_day: str) -> list[str]:
    order = list(DAY_ORDER)
    start_index = order.index(start_day)
    end_index = order.index(end_day)
    if start_index <= end_index:
        return order[start_index : end_index + 1]
    return order[start_index:] + order[: end_index + 1]


def _extract_count(text: str) -> int:
    match = _COUNT_PATTERN.search(text.lower())
    if not match:
        return 1
    return int(match.group(1))


def _extract_start_time(text: str) -> str:
    match = _TIME_RANGE_PATTERN.search(normalize_text(text))
    if match:
        return normalize_time(match.group(1))
    return "18:00"


def _add_minutes(time_str: str, minutes: int) -> str:
    base = normalize_time(time_str)
    hours = int(base[:2])
    mins = int(base[3:])
    total = hours * 60 + mins + minutes
    total = total % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


def _pick_days(days: list[str], count: int) -> list[str]:
    selected: list[str] = []
    if not days:
        return selected
    index = 0
    while len(selected) < count:
        selected.append(days[index % len(days)])
        index += 1
    return selected
