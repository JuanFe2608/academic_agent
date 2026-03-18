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
    r"domingos|domingo|dom|do|d"
    r")"
)
_DAY_TOKEN_STRICT_PATTERN = (
    r"(?:"
    r"lunes|lun|"
    r"martes|mar|"
    r"miercoles|mier|mie|x|"
    r"jueves|jue|"
    r"viernes|vie|"
    r"sabados|sabado|sab|"
    r"domingos|domingo|dom"
    r")"
)
_TIME_TOKEN_PATTERN = r"\d{1,2}(?::\d{2})?(?::\d{2})?(?:\s*[ap]\.?\s*m\.?)?"
_ALL_DAYS_PATTERN = re.compile(
    r"\b(?:todos\s+los\s+dias|todos\s+los\s+días|cada\s+dia|cada\s+día|diario|diariamente)\b"
)
_ALL_DAYS_EXCEPT_PATTERN = re.compile(
    r"\b(?:todos\s+los\s+dias|todos\s+los\s+días|cada\s+dia|cada\s+día)\b\s+menos\s+(?P<excluded>.+)"
)

_RANGE_PATTERN = re.compile(
    rf"\b({_DAY_TOKEN_PATTERN})\b\s*(?:-|a|hasta)\s*\b({_DAY_TOKEN_PATTERN})\b"
)
_SINGLE_DAY_PATTERN = re.compile(rf"\b({_DAY_TOKEN_PATTERN})\b")
_STRICT_DAY_PATTERN = re.compile(rf"\b({_DAY_TOKEN_STRICT_PATTERN})\b")
_TIME_RANGE_PATTERN = re.compile(
    rf"(?:de|desde)?\s*(?:las\s+)?({_TIME_TOKEN_PATTERN})\s*(?:-|a|hasta)\s*(?:las\s+)?({_TIME_TOKEN_PATTERN})"
)

_WORK_DAY_LINE_PATTERN = re.compile(
    r"^\s*(?P<day>lunes|martes|miercoles|miércoles|jueves|viernes|sabado|sábado|domingo)"
    rf"\s+(?:de\s+)?(?P<start>{_TIME_TOKEN_PATTERN})\s*(?:-|a|hasta)\s*(?P<end>{_TIME_TOKEN_PATTERN})",
    re.IGNORECASE,
)

_ACADEMIC_DAYS_PATTERN = re.compile(
    r"(?P<days>(?:LUN|MAR|MIE|JUE|VIE|SAB|DOM)(?:\s*,\s*(?:LUN|MAR|MIE|JUE|VIE|SAB|DOM))*)"
    rf"\s+(?P<start>{_TIME_TOKEN_PATTERN})\s*-\s*(?P<end>{_TIME_TOKEN_PATTERN})",
    re.IGNORECASE,
)

_DATE_LINE = re.compile(r"\b\d{2}-\d{2}-\d{4}\b")

_DAY_LINE_PATTERN = re.compile(
    r"^\s*(?P<day>lunes|martes|miercoles|miércoles|jueves|viernes|sabado|sábado|domingo)"
    rf"\s+(?:de\s+)?(?P<start>{_TIME_TOKEN_PATTERN})\s*(?:-|a|hasta)\s*(?P<end>{_TIME_TOKEN_PATTERN})"
    r"(?:\s+(?P<title>.+))?",
    re.IGNORECASE,
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

    line_events = _parse_work_day_lines(str(text), timezone)
    if line_events:
        return line_events

    normalized = _strip_accents(str(text).lower())
    schedule = extract_natural_schedule_components(normalized)
    start = str(schedule["start"])
    end = str(schedule["end"])
    days = list(schedule["days"])
    overnight = bool(schedule["overnight"])

    events: list[Event] = []
    for day in days:
        events.extend(
            _build_day_events(
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


def extract_natural_schedule_components(text: str) -> dict[str, object]:
    """Extrae dias y horas desde lenguaje natural sin inventar AM/PM."""
    if text is None or not str(text).strip():
        raise ValueError("schedule text is required")

    normalized = _strip_accents(str(text).lower())
    start_raw, end_raw = _extract_time_range(normalized)
    start, end, overnight = _normalize_time_range_info(start_raw, end_raw, normalized)
    days, is_all_days = _extract_days_with_meta(normalized)
    return {
        "days": days,
        "start": start,
        "end": end,
        "is_all_days": is_all_days,
        "overnight": overnight,
    }


def is_ambiguous_time_range(text: str) -> bool:
    """Indica si el rango horario requiere aclaracion adicional."""
    if text is None or not str(text).strip():
        return False
    normalized = _strip_accents(str(text).lower())
    if any(marker in normalized for marker in ("manana", "mañana", "tarde", "noche")):
        return False

    try:
        start_raw, end_raw = _extract_time_range(normalized)
    except ValueError:
        return False

    try:
        _normalize_time_range_info(start_raw, end_raw, normalized)
    except ValueError as exc:
        return "ambiguous time range" in str(exc).lower()
    return False


def _parse_work_day_lines(text: str, timezone: str) -> list[Event]:
    lines = _normalize_lines(text)
    events: list[Event] = []
    seen: set[tuple[str, str, str]] = set()

    for line in lines:
        match = _WORK_DAY_LINE_PATTERN.search(line)
        if not match:
            continue
        day = _normalize_day_token(match.group("day"))
        start, end, overnight = _normalize_time_range_info(
            match.group("start"),
            match.group("end"),
            line,
        )
        for event in _build_day_events(
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


def _normalize_time_range(start_raw: str, end_raw: str, context: str = "") -> tuple[str, str]:
    start, end, _overnight = _normalize_time_range_info(start_raw, end_raw, context)
    return start, end


def _normalize_time_range_info(
    start_raw: str,
    end_raw: str,
    context: str = "",
) -> tuple[str, str, bool]:
    start, start_ambiguous, start_has_meridiem = _parse_time_token(start_raw)
    end, end_ambiguous, end_has_meridiem = _parse_time_token(end_raw)
    propagated_meridiem = False

    if start_ambiguous and end_ambiguous:
        raise ValueError(
            "ambiguous time range; specify AM o PM o usa formato de 24 horas"
        )

    if start_ambiguous and end_has_meridiem:
        start = _apply_meridiem(start_raw, _extract_meridiem(end_raw))
        start_ambiguous = False
        propagated_meridiem = True
    elif end_ambiguous and start_has_meridiem:
        end = _apply_meridiem(end_raw, _extract_meridiem(start_raw))
        end_ambiguous = False
        propagated_meridiem = True

    if start_ambiguous or end_ambiguous:
        raise ValueError(
            "ambiguous time range; specify AM o PM o usa formato de 24 horas"
        )

    start_minutes = int(start[:2]) * 60 + int(start[3:])
    end_minutes = int(end[:2]) * 60 + int(end[3:])
    if end_minutes <= start_minutes:
        if propagated_meridiem:
            raise ValueError(
                "ambiguous time range; specify AM o PM o usa formato de 24 horas"
            )
        if (
            start_has_meridiem
            or end_has_meridiem
            or _looks_24h(start_raw)
            or _looks_24h(end_raw)
        ):
            return start, end, True
        raise ValueError(
            "ambiguous time range; specify AM o PM o usa formato de 24 horas"
        )
    return start, end, False


def parse_academic_schedule_text(
    text: str, timezone: str = "America/Bogota"
) -> list[Event]:
    """Parsea texto del correo institucional de horario academico."""
    if text is None or not str(text).strip():
        return []

    lines = _normalize_lines(text)
    current_subject = ""
    events: list[Event] = []
    seen: set[tuple[str, str, str, str]] = set()

    for line in lines:
        day_match = _DAY_LINE_PATTERN.search(line)
        if day_match:
            day_token = day_match.group("day")
            days = [_normalize_day_token(day_token)]
            start_raw = day_match.group("start")
            end_raw = day_match.group("end")
            start, end, overnight = _normalize_time_range_info(start_raw, end_raw, line)
            title = (day_match.group("title") or "").strip() or current_subject or "Clase"
            for day in days:
                for event in _build_day_events(
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

        if _is_subject_line(line):
            current_subject = line.strip()
            continue

        for match in _ACADEMIC_DAYS_PATTERN.finditer(line):
            days = _split_days(match.group("days"))
            start, end, overnight = _normalize_time_range_info(
                match.group("start"),
                match.group("end"),
                line,
            )
            title = current_subject or "Clase"
            for day in days:
                for event in _build_day_events(
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


def _strip_accents(value: str) -> str:
    """Elimina acentos para facilitar la deteccion de dias."""
    return (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
    )


def _normalize_lines(text: str) -> list[str]:
    lines = [line.strip() for line in str(text).splitlines()]
    return [line for line in lines if line]


def _is_subject_line(line: str) -> bool:
    normalized = _strip_accents(line.lower())
    if _DAY_LINE_PATTERN.search(line):
        return False
    if _DATE_LINE.search(normalized):
        return False
    if "codigo asignatura" in normalized:
        return False
    if "creditos" in normalized or "créditos" in normalized:
        return False
    if "grupo" in normalized:
        return False
    if "bogota" in normalized or "bloque" in normalized or "salon" in normalized or "sala" in normalized:
        return False
    if _ACADEMIC_DAYS_PATTERN.search(line):
        return False
    if len(normalized) < 3:
        return False
    letters = sum(1 for ch in normalized if ch.isalpha())
    return letters >= 3


def _split_days(days_raw: str) -> list[str]:
    tokens = [token.strip() for token in days_raw.split(",") if token.strip()]
    days: list[str] = []
    for token in tokens:
        normalized = _strip_accents(token.lower())
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


def _extract_time_range(text: str) -> tuple[str, str]:
    """Extrae el rango de horas desde el texto normalizado."""
    match = _TIME_RANGE_PATTERN.search(text)
    if not match:
        raise ValueError("no time range found")
    return match.group(1), match.group(2)


def _has_meridiem(value: str) -> bool:
    return bool(_extract_meridiem(value))


def _looks_24h(value: str) -> bool:
    raw = _normalize_meridiem_token(value)
    match = re.match(r"^(\d{1,2})", raw)
    hour = int(match.group(1)) if match else 0
    return hour >= 13 or ":" in raw


def _strip_seconds(value: str) -> str:
    raw = str(value).strip()
    match = re.match(r"^(\d{1,2}:\d{2})(?::\d{2})?$", raw)
    return match.group(1) if match else raw


def _extract_days(text: str) -> list[str]:
    days, _ = _extract_days_with_meta(text)
    return days


def _extract_days_with_meta(text: str) -> tuple[list[str], bool]:
    """Extrae dias desde un rango o un dia individual."""
    except_match = _ALL_DAYS_EXCEPT_PATTERN.search(text)
    if except_match:
        excluded: list[str] = []
        for token in _STRICT_DAY_PATTERN.findall(except_match.group("excluded")):
            day = _normalize_day_token(token)
            if day not in excluded:
                excluded.append(day)
        return [day for day in DAY_ORDER if day not in excluded], False

    if _ALL_DAYS_PATTERN.search(text):
        return list(DAY_ORDER), True

    range_match = _RANGE_PATTERN.search(text)
    if range_match:
        start_token, end_token = range_match.group(1), range_match.group(2)
        start_day = _normalize_day_token(start_token)
        end_day = _normalize_day_token(end_token)
        return _expand_day_range(start_day, end_day), False

    matches = _STRICT_DAY_PATTERN.findall(text)
    if matches:
        days: list[str] = []
        for token in matches:
            day = _normalize_day_token(token)
            if day not in days:
                days.append(day)
        return days, False

    single_match = _SINGLE_DAY_PATTERN.search(text)
    if not single_match:
        raise ValueError("no day found")
    return [_normalize_day_token(single_match.group(1))], False


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


def _next_day(day: str) -> str:
    order = list(DAY_ORDER)
    return order[(order.index(day) + 1) % len(order)]


def _build_day_events(
    day: str,
    start: str,
    end: str,
    overnight: bool,
    title: str,
    category: str,
    timezone: str,
) -> list[Event]:
    if not overnight:
        return [
            Event(
                id=new_event_id(),
                dia=day,
                inicio=start,
                fin=end,
                titulo=title,
                tipo="confirmado",
                categoria=category,
                origen="user_text",
                timezone=timezone,
            )
        ]

    events = [
        Event(
            id=new_event_id(),
            dia=day,
            inicio=start,
            fin="23:59",
            titulo=title,
            tipo="confirmado",
            categoria=category,
            origen="user_text",
            timezone=timezone,
        )
    ]
    if end != "00:00":
        events.append(
            Event(
                id=new_event_id(),
                dia=_next_day(day),
                inicio="00:00",
                fin=end,
                titulo=title,
                tipo="confirmado",
                categoria=category,
                origen="user_text",
                timezone=timezone,
            )
        )
    return events


def _parse_time_token(value: str) -> tuple[str, bool, bool]:
    raw = _normalize_meridiem_token(_strip_seconds(value))
    match = re.match(r"^(\d{1,2})(?::(\d{2}))?([ap]m)?$", raw)
    if not match:
        raise ValueError(f"invalid time format: {value!r}")

    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = match.group(3)
    has_colon = ":" in raw

    if meridiem:
        if hour > 12:
            normalized = normalize_time(f"{hour}:{minute:02d}")
            return normalized, False, False
        normalized = normalize_time(f"{hour}:{minute:02d}{meridiem}")
        return normalized, False, True

    normalized = normalize_time(f"{hour}:{minute:02d}")
    is_ambiguous = not has_colon and hour <= 12
    return normalized, is_ambiguous, False


def _extract_meridiem(value: str) -> str:
    raw = _normalize_meridiem_token(value)
    match = re.search(r"([ap]m)$", raw)
    return match.group(1) if match else ""


def _apply_meridiem(value: str, meridiem: str) -> str:
    if not meridiem:
        raise ValueError("ambiguous time range; specify AM o PM o usa formato de 24 horas")
    raw = _normalize_meridiem_token(_strip_seconds(value))
    if _extract_meridiem(raw):
        return normalize_time(raw)
    return normalize_time(f"{raw}{meridiem}")


def _normalize_meridiem_token(value: str) -> str:
    raw = str(value).strip().lower()
    raw = raw.replace(".", "")
    raw = re.sub(r"\s+", "", raw)
    raw = raw.replace("a m", "am").replace("p m", "pm")
    return raw
