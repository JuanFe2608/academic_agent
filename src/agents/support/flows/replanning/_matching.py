"""Matching y utilidades de seleccion para replanificacion."""

from __future__ import annotations

import re

from agents.support.nodes.utils import normalize_text
from schemas.scheduling import Event
from services.scheduling.activity_matching import resolve_best_title_key
from services.scheduling.validation import normalize_time


def event_from_id(events: list[Event], event_id: str) -> Event | None:
    for event in events:
        if str(event.get("id")) == str(event_id):
            return event
    return None


def events_from_ids(events: list[Event], candidate_ids: list[str]) -> list[Event]:
    id_set = set(candidate_ids)
    return [event for event in events if str(event.get("id")) in id_set]


def find_delete_matches(events: list[Event], details: str) -> list[Event]:
    normalized = normalize_text(details)
    hinted_day = extract_day_hint(normalized)
    hinted_time = extract_time_hint(details)
    title_key = extract_best_title_key(events, normalized)
    if not title_key and not hinted_day and not hinted_time and normalized:
        return []

    matches: list[Event] = []
    for event in events:
        event_title = str(event.get("titulo") or "").strip()
        if not event_title:
            continue
        event_normalized = normalize_text(event_title)
        if title_key and event_normalized != title_key:
            continue
        if hinted_day and normalize_text(str(event.get("dia") or "")) != hinted_day:
            continue
        if hinted_time and hinted_time != f"{event.get('inicio')}-{event.get('fin')}":
            continue
        matches.append(event)
    return matches


def extract_best_title_key(events: list[Event], normalized_details: str) -> str:
    return resolve_best_title_key(events, normalized_details)


def extract_day_hint(normalized: str) -> str:
    aliases = {
        "lunes": "lunes",
        "lun": "lunes",
        "martes": "martes",
        "mar": "martes",
        "miercoles": "miercoles",
        "mie": "miercoles",
        "jueves": "jueves",
        "jue": "jueves",
        "viernes": "viernes",
        "vie": "viernes",
        "sabado": "sabado",
        "sab": "sabado",
        "domingo": "domingo",
        "dom": "domingo",
    }
    for token, canonical in aliases.items():
        if re.search(rf"\b{re.escape(token)}\b", normalized):
            return canonical
    return ""


def extract_time_hint(details: str) -> str:
    match = re.search(
        r"(\d{1,2}(?::\d{2})?\s*(?:[ap]\.?\s*m\.?)?)\s*(?:-|a|hasta)\s*"
        r"(\d{1,2}(?::\d{2})?\s*(?:[ap]\.?\s*m\.?)?)",
        details,
        re.IGNORECASE,
    )
    if not match:
        return ""
    start_raw = normalize_meridiem_text(match.group(1))
    end_raw = normalize_meridiem_text(match.group(2))
    start_has_meridiem = bool(re.search(r"[ap]m$", start_raw))
    end_has_meridiem = bool(re.search(r"[ap]m$", end_raw))
    if start_has_meridiem and not end_has_meridiem:
        end_raw = f"{end_raw}{start_raw[-2:]}"
    elif end_has_meridiem and not start_has_meridiem:
        start_raw = f"{start_raw}{end_raw[-2:]}"
    try:
        if not start_has_meridiem and not end_has_meridiem and ":" not in start_raw and ":" not in end_raw:
            return ""
        return f"{normalize_time(start_raw)}-{normalize_time(end_raw)}"
    except ValueError:
        return ""


def normalize_meridiem_text(value: str) -> str:
    normalized = normalize_text(value)
    normalized = normalized.replace(".", "")
    normalized = normalized.replace(" ", "")
    normalized = normalized.replace("a m", "am").replace("p m", "pm")
    return normalized


def has_day_or_time_hint(details: str) -> bool:
    normalized = normalize_text(details)
    return bool(extract_day_hint(normalized) or extract_time_hint(details))


def build_match_table(matches: list[Event]) -> str:
    rows = [
        (str(event.get("dia") or ""), str(event.get("titulo") or ""), f"{event.get('inicio')}-{event.get('fin')}")
        for event in matches
    ]
    day_width = max(len("Dia"), *(len(row[0]) for row in rows))
    title_width = max(len("Actividad"), *(len(row[1]) for row in rows))
    hour_width = max(len("Hora"), *(len(row[2]) for row in rows))
    separator = "+" + "-" * (day_width + 2) + "+" + "-" * (title_width + 2) + "+" + "-" * (hour_width + 2) + "+"
    lines = [
        separator,
        f"| {'Dia'.ljust(day_width)} | {'Actividad'.ljust(title_width)} | {'Hora'.ljust(hour_width)} |",
        separator,
    ]
    for row in rows:
        lines.append(
            f"| {row[0].ljust(day_width)} | {row[1].ljust(title_width)} | {row[2].ljust(hour_width)} |"
        )
        lines.append(separator)
    return "\n".join(lines)


def build_delete_confirmation_prompt(matches: list[Event]) -> str:
    if len(matches) == 1:
        event = matches[0]
        return (
            "Estas seguro de que deseas eliminar la actividad:\n"
            f"{event.get('titulo')}\n"
            f"{event.get('dia')} {event.get('inicio')}-{event.get('fin')} ?"
        )
    activity_name = str(matches[0].get("titulo") or "actividad")
    schedules = "\n".join(
        f"- {event.get('dia')} {event.get('inicio')}-{event.get('fin')}" for event in matches
    )
    return (
        "Estas seguro de que deseas eliminar la actividad:\n"
        f"{activity_name}\n"
        f"{schedules}"
    )


def parse_delete_scope(text: str) -> str | None:
    normalized = normalize_text(text)
    if normalized in {"1", "1.", "1)", "todas", "toda", "eliminar todas"} or "todas" in normalized:
        return "all"
    if normalized in {"2", "2.", "2)", "especificar", "una", "solo una", "especifica"}:
        return "specific"
    return None


def filter_events_by_hint(events: list[Event], details: str) -> list[Event]:
    hinted_day = extract_day_hint(normalize_text(details))
    hinted_time = extract_time_hint(details)
    filtered: list[Event] = []
    for event in events:
        if hinted_day and normalize_text(str(event.get("dia") or "")) != hinted_day:
            continue
        if hinted_time and hinted_time != f"{event.get('inicio')}-{event.get('fin')}":
            continue
        filtered.append(event)
    return filtered


__all__ = [
    "build_delete_confirmation_prompt",
    "build_match_table",
    "event_from_id",
    "events_from_ids",
    "extract_day_hint",
    "extract_time_hint",
    "filter_events_by_hint",
    "find_delete_matches",
    "has_day_or_time_hint",
    "parse_delete_scope",
]
