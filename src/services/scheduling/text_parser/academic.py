"""Parser académico determinístico para horarios en texto."""

from __future__ import annotations

from schemas.scheduling import Event

from ._common import (
    ACADEMIC_DAYS_PATTERN,
    DATE_LINE,
    DAY_LINE_PATTERN,
    build_day_events,
    normalize_day_token,
    normalize_lines,
    normalize_parser_text,
    normalize_time_range_info,
    strip_accents,
)


def parse_academic_schedule_text(
    text: str,
    timezone: str = "America/Bogota",
) -> list[Event]:
    """Parsea texto del correo institucional de horario académico."""

    if text is None or not str(text).strip():
        return []

    lines = normalize_lines(normalize_parser_text(text))
    current_subject = ""
    events: list[Event] = []
    seen: set[tuple[str, str, str, str]] = set()

    for line in lines:
        day_match = DAY_LINE_PATTERN.search(line)
        if day_match:
            day_token = day_match.group("day")
            days = [normalize_day_token(day_token)]
            start_raw = day_match.group("start")
            end_raw = day_match.group("end")
            start, end, overnight = normalize_time_range_info(start_raw, end_raw, line)
            title = (day_match.group("title") or "").strip() or current_subject or "Clase"
            for day in days:
                for event in build_day_events(
                    day=day,
                    start=start,
                    end=end,
                    overnight=overnight,
                    title=title,
                    category="academico",
                    timezone=timezone,
                ):
                    key = (event.dia, event.inicio, event.fin, event.titulo)
                    if key in seen:
                        continue
                    seen.add(key)
                    events.append(event)
            continue

        if is_subject_line(line):
            current_subject = line.strip()
            continue

        for match in ACADEMIC_DAYS_PATTERN.finditer(line):
            days = split_days(match.group("days"))
            start, end, overnight = normalize_time_range_info(
                match.group("start"),
                match.group("end"),
                line,
            )
            title = current_subject or "Clase"
            for day in days:
                for event in build_day_events(
                    day=day,
                    start=start,
                    end=end,
                    overnight=overnight,
                    title=title,
                    category="academico",
                    timezone=timezone,
                ):
                    key = (event.dia, event.inicio, event.fin, event.titulo)
                    if key in seen:
                        continue
                    seen.add(key)
                    events.append(event)
    return events


def is_subject_line(line: str) -> bool:
    normalized = strip_accents(line.lower())
    if DAY_LINE_PATTERN.search(line):
        return False
    if DATE_LINE.search(normalized):
        return False
    if "codigo asignatura" in normalized:
        return False
    if "creditos" in normalized or "créditos" in normalized:
        return False
    if "grupo" in normalized:
        return False
    if (
        "bogota" in normalized
        or "bloque" in normalized
        or "salon" in normalized
        or "sala" in normalized
    ):
        return False
    if ACADEMIC_DAYS_PATTERN.search(line):
        return False
    if len(normalized) < 3:
        return False
    letters = sum(1 for ch in normalized if ch.isalpha())
    return letters >= 3


def split_days(days_raw: str) -> list[str]:
    tokens = [token.strip() for token in days_raw.split(",") if token.strip()]
    days: list[str] = []
    for token in tokens:
        normalized = strip_accents(token.lower())
        normalized = normalized[:3]
        if normalized == "lun":
            days.append("Lunes")
        elif normalized == "mar":
            days.append("Martes")
        elif normalized == "mie":
            days.append("Miercoles")
        elif normalized == "jue":
            days.append("Jueves")
        elif normalized == "vie":
            days.append("Viernes")
        elif normalized == "sab":
            days.append("Sabado")
        elif normalized == "dom":
            days.append("Domingo")
    return days

