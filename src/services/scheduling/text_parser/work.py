"""Parser laboral determinístico para horarios en texto."""

from __future__ import annotations

from schemas.scheduling import Event

from ._common import (
    WORK_DAY_LINE_PATTERN,
    build_day_events,
    extract_natural_schedule_components,
    normalize_day_token,
    normalize_lines,
    normalize_parser_text,
    normalize_time_range_info,
    strip_accents,
)


def parse_work_schedule_text(
    text: str,
    timezone: str = "America/Bogota",
) -> list[Event]:
    """Analiza texto de horario laboral y retorna eventos estándar."""

    if text is None or not str(text).strip():
        return []

    prepared_text = normalize_parser_text(str(text))
    line_events = parse_work_day_lines(prepared_text, timezone)
    if line_events:
        return line_events

    normalized = strip_accents(prepared_text.lower())
    schedule = extract_natural_schedule_components(normalized)
    start = str(schedule["start"])
    end = str(schedule["end"])
    days = list(schedule["days"])
    overnight = bool(schedule["overnight"])

    events: list[Event] = []
    for day in days:
        events.extend(
            build_day_events(
                day=day,
                start=start,
                end=end,
                overnight=overnight,
                title="Trabajo",
                category="laboral",
                timezone=timezone,
            )
        )
    return events


def parse_work_day_lines(text: str, timezone: str) -> list[Event]:
    lines = normalize_lines(text)
    events: list[Event] = []
    seen: set[tuple[str, str, str]] = set()

    for line in lines:
        match = WORK_DAY_LINE_PATTERN.search(line)
        if not match:
            continue
        day = normalize_day_token(match.group("day"))
        start, end, overnight = normalize_time_range_info(
            match.group("start"),
            match.group("end"),
            line,
        )
        for event in build_day_events(
            day=day,
            start=start,
            end=end,
            overnight=overnight,
            title="Trabajo",
            category="laboral",
            timezone=timezone,
        ):
            key = (event.dia, event.inicio, event.fin)
            if key in seen:
                continue
            seen.add(key)
            events.append(event)
    return events

