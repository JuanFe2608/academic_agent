"""Generación de eventos para actividades extracurriculares."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping

from integrations.ai.structured_extraction import llm_normalize_schedule
from schemas.scheduling import Event, ExtracurricularItem
from services.scheduling.text_parser import parse_academic_schedule_text
from services.scheduling.validation import (
    DAY_ORDER,
    new_event_id,
    normalize_day,
    normalize_time,
    validate_event,
)

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
_DAY_TOKEN_STRICT_PATTERN = (
    r"(?:"
    r"lunes|lun|"
    r"martes|mar|"
    r"miercoles|mier|mie|x|"
    r"jueves|jue|"
    r"viernes|vie|"
    r"sabado|sab|"
    r"domingo|dom"
    r")"
)
_ALL_DAY_PATTERN = re.compile(rf"\b({_DAY_TOKEN_STRICT_PATTERN})\b")
_SINGLE_DAY_PATTERN = re.compile(rf"\b({_DAY_TOKEN_PATTERN})\b")
_TIME_RANGE_PATTERN = re.compile(
    r"(\d{1,2}(?::\d{2})?\s*(?:[ap]m?)?)\s*(?:-|a|hasta)\s*(\d{1,2}(?::\d{2})?\s*(?:[ap]m?)?)"
)
_COUNT_PATTERN = re.compile(r"(\d+)\s*veces")
_ALL_DAYS_PATTERN = re.compile(
    r"\b(?:todos\s+los\s+dias|todos\s+los\s+días|cada\s+dia|cada\s+día|diario|diariamente)\b"
)


def generate_tentative_extracurricular(state: Mapping[str, object]) -> dict:
    """Genera eventos para actividades variables y fijas."""

    timezone = str(state.get("timezone", "America/Bogota"))
    events: list[Event] = list(state.get("events", []))
    errors = list(state.get("errors", []))
    extracurricular_updated: list[ExtracurricularItem] = []

    for item in state.get("extracurricular", []):
        updated_item = ensure_extracurricular_item(item)
        tentativos: list[Event] = []
        generated_events = (
            build_tentative_events(updated_item, timezone)
            if updated_item.get("es_variable")
            else build_fixed_events(updated_item, timezone)
        )
        for event in generated_events:
            try:
                validate_event(event)
            except ValueError as exc:
                errors.append(f"Evento extracurricular invalido: {exc}")
                continue
            events.append(event)
            if event.get("tipo") == "tentativo":
                tentativos.append(event)
        updated_item.tentativo = tentativos
        extracurricular_updated.append(updated_item)

    return {
        "extracurricular": extracurricular_updated,
        "events": events,
        "errors": errors,
        "phase": "draft",
    }


def build_tentative_events(item: ExtracurricularItem, timezone: str) -> list[Event]:
    """Crea eventos tentativos con una heurística simple."""

    detail = str(item.get("detalle", ""))
    day_candidates = extract_days(detail)
    count = extract_count(detail)
    start_time = extract_start_time(detail)
    end_time = add_minutes(start_time, 60)

    if not day_candidates:
        day_candidates = ["Lunes", "Miercoles", "Viernes"]
    if count <= 0:
        count = min(2, len(day_candidates))

    selected_days = pick_days(day_candidates, count)
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


def build_fixed_events(item: ExtracurricularItem, timezone: str) -> list[Event]:
    """Crea eventos confirmados a partir del horario fijo de la actividad."""

    detail = str(item.get("detalle", "")).strip()
    if not detail:
        return []

    heuristic_events = build_fixed_events_heuristic(item, timezone)
    parsed = parse_fixed_schedule_with_ai(detail, timezone)
    if parsed and len(parsed) >= len(heuristic_events):
        return [
            Event(
                id=new_event_id(),
                dia=event.get("dia"),
                inicio=event.get("inicio"),
                fin=event.get("fin"),
                titulo=item.get("nombre", "Extracurricular"),
                tipo="confirmado",
                categoria="extracurricular",
                origen="user_text",
                timezone=timezone,
            )
            for event in parsed
        ]

    return heuristic_events


def build_fixed_events_heuristic(item: ExtracurricularItem, timezone: str) -> list[Event]:
    detail = str(item.get("detalle", "")).strip()
    day_candidates = extract_days(detail)
    if not day_candidates:
        return []
    start_time, end_time = extract_start_end_time(detail)
    if not start_time or not end_time:
        return []
    return [
        Event(
            id=new_event_id(),
            dia=day,
            inicio=start_time,
            fin=end_time,
            titulo=item.get("nombre", "Extracurricular"),
            tipo="confirmado",
            categoria="extracurricular",
            origen="user_text",
            timezone=timezone,
        )
        for day in day_candidates
    ]


def ensure_extracurricular_item(item: ExtracurricularItem | dict) -> ExtracurricularItem:
    if isinstance(item, ExtracurricularItem):
        return item
    return ExtracurricularItem(**item)


def extract_days(text: str) -> list[str]:
    normalized = normalize_text(text)
    if _ALL_DAYS_PATTERN.search(normalized):
        return list(DAY_ORDER)

    range_match = _RANGE_PATTERN.search(normalized)
    if range_match:
        start_day = normalize_day_token(range_match.group(1))
        end_day = normalize_day_token(range_match.group(2))
        return expand_day_range(start_day, end_day)

    matches = _ALL_DAY_PATTERN.findall(normalized)
    if not matches:
        single_match = _SINGLE_DAY_PATTERN.search(normalized)
        if single_match:
            matches = [single_match.group(1)]

    days: list[str] = []
    for token in matches:
        try:
            day = normalize_day_token(token)
        except ValueError:
            continue
        if day not in days:
            days.append(day)
    return days


def normalize_day_token(token: str) -> str:
    try:
        return normalize_day(token)
    except ValueError:
        if token.endswith("s") and len(token) > 1:
            return normalize_day(token[:-1])
        raise


def expand_day_range(start_day: str, end_day: str) -> list[str]:
    order = list(DAY_ORDER)
    start_index = order.index(start_day)
    end_index = order.index(end_day)
    if start_index <= end_index:
        return order[start_index : end_index + 1]
    return order[start_index:] + order[: end_index + 1]


def extract_count(text: str) -> int:
    match = _COUNT_PATTERN.search(text.lower())
    if not match:
        return 1
    return int(match.group(1))


def extract_start_time(text: str) -> str:
    match = _TIME_RANGE_PATTERN.search(normalize_text(text))
    if match:
        return normalize_time(match.group(1))
    return "18:00"


def extract_start_end_time(text: str) -> tuple[str | None, str | None]:
    match = _TIME_RANGE_PATTERN.search(normalize_text(text))
    if not match:
        return None, None
    start = normalize_time(match.group(1))
    end = normalize_time(match.group(2))
    return start, end


def add_minutes(time_str: str, minutes: int) -> str:
    base = normalize_time(time_str)
    hours = int(base[:2])
    mins = int(base[3:])
    total = hours * 60 + mins + minutes
    total = total % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


def pick_days(days: list[str], count: int) -> list[str]:
    selected: list[str] = []
    if not days:
        return selected
    index = 0
    while len(selected) < count:
        selected.append(days[index % len(days)])
        index += 1
    return selected


def parse_fixed_schedule_with_ai(detail: str, timezone: str) -> list[Event]:
    normalized = llm_normalize_schedule(detail, "academico")
    candidates = [candidate for candidate in [normalized, detail] if candidate]
    seen: set[str] = set()
    for candidate in candidates:
        text = str(candidate).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        try:
            parsed = parse_academic_schedule_text(text, timezone)
        except ValueError:
            parsed = []
        if parsed:
            return parsed
    return []


def normalize_text(value: str) -> str:
    """Normaliza texto para comparaciones simples sin depender del agente."""

    return (
        unicodedata.normalize("NFKD", str(value or ""))
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
        .strip()
    )

