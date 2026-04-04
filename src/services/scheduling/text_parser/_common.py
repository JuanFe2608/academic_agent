"""Utilidades compartidas para parseo de horarios en texto."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from schemas.scheduling import Event
from services.scheduling.validation import (
    DAY_ORDER,
    new_event_id,
    normalize_day,
    normalize_time,
)

DAY_TOKEN_PATTERN = (
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
DAY_TOKEN_STRICT_PATTERN = (
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
TIME_TOKEN_PATTERN = r"\d{1,2}(?::\d{2})?(?::\d{2})?(?:\s*[ap]\.?\s*m\.?)?"

ALL_DAYS_PATTERN = re.compile(
    r"\b(?:todos\s+los\s+dias|todos\s+los\s+días|cada\s+dia|cada\s+día|diario|diariamente)\b"
)
ALL_DAYS_EXCEPT_PATTERN = re.compile(
    r"\b(?:todos\s+los\s+dias|todos\s+los\s+días|cada\s+dia|cada\s+día)\b\s+menos\s+(?P<excluded>.+)"
)
RANGE_PATTERN = re.compile(
    rf"\b({DAY_TOKEN_PATTERN})\b\s*(?:-|a|hasta)\s*\b({DAY_TOKEN_PATTERN})\b"
)
SINGLE_DAY_PATTERN = re.compile(rf"\b({DAY_TOKEN_PATTERN})\b")
STRICT_DAY_PATTERN = re.compile(rf"\b({DAY_TOKEN_STRICT_PATTERN})\b")
TIME_RANGE_PATTERN = re.compile(
    rf"(?:de|desde)?\s*(?:las\s+)?({TIME_TOKEN_PATTERN})\s*(?:-|a|hasta)\s*(?:las\s+)?({TIME_TOKEN_PATTERN})"
)

WORK_DAY_LINE_PATTERN = re.compile(
    r"^\s*(?P<day>lunes|martes|miercoles|miércoles|jueves|viernes|sabado|sábado|domingo)"
    rf"\s+(?:de\s+)?(?P<start>{TIME_TOKEN_PATTERN})\s*(?:-|a|hasta)\s*(?P<end>{TIME_TOKEN_PATTERN})",
    re.IGNORECASE,
)
ACADEMIC_DAYS_PATTERN = re.compile(
    r"(?P<days>(?:LUN|MAR|MIE|JUE|VIE|SAB|DOM)(?:\s*,\s*(?:LUN|MAR|MIE|JUE|VIE|SAB|DOM))*)"
    rf"\s+(?P<start>{TIME_TOKEN_PATTERN})\s*-\s*(?P<end>{TIME_TOKEN_PATTERN})",
    re.IGNORECASE,
)
DATE_LINE = re.compile(r"\b\d{2}-\d{2}-\d{4}\b")
DAY_LINE_PATTERN = re.compile(
    r"^\s*(?P<day>lunes|martes|miercoles|miércoles|jueves|viernes|sabado|sábado|domingo)"
    rf"\s+(?:de\s+)?(?P<start>{TIME_TOKEN_PATTERN})\s*(?:-|a|hasta)\s*(?P<end>{TIME_TOKEN_PATTERN})"
    r"(?:\s+(?P<title>.+))?",
    re.IGNORECASE,
)


def extract_natural_schedule_components(text: str) -> dict[str, object]:
    """Extrae días y horas desde lenguaje natural sin inventar AM/PM."""

    if text is None or not str(text).strip():
        raise ValueError("schedule text is required")

    normalized = strip_accents(normalize_parser_text(str(text)).lower())
    start_raw, end_raw = extract_time_range(normalized)
    start, end, overnight = normalize_time_range_info(start_raw, end_raw, normalized)
    days, is_all_days = extract_days_with_meta(normalized)
    return {
        "days": days,
        "start": start,
        "end": end,
        "is_all_days": is_all_days,
        "overnight": overnight,
    }


def is_ambiguous_time_range(text: str) -> bool:
    """Indica si el rango horario requiere aclaración adicional."""

    if text is None or not str(text).strip():
        return False
    try:
        normalized = strip_accents(normalize_parser_text(str(text)).lower())
        start_raw, end_raw = extract_time_range(normalized)
    except ValueError:
        return False

    try:
        normalize_time_range_info(start_raw, end_raw, normalized)
    except ValueError:
        return False
    return False


def normalize_time_range(start_raw: str, end_raw: str, context: str = "") -> tuple[str, str]:
    start, end, _overnight = normalize_time_range_info(start_raw, end_raw, context)
    return start, end


def normalize_time_range_info(
    start_raw: str,
    end_raw: str,
    context: str = "",
) -> tuple[str, str, bool]:
    del context
    start_options = parse_time_token(start_raw)
    end_options = parse_time_token(end_raw)

    best_pair: tuple[str, str, bool] | None = None
    best_score: tuple[int, int, int, int] | None = None
    for start_option in start_options:
        for end_option in end_options:
            start_minutes = minutes(start_option.value)
            end_minutes = minutes(end_option.value)
            overnight = end_minutes <= start_minutes
            duration = (
                (end_minutes + 1440 - start_minutes)
                if overnight
                else (end_minutes - start_minutes)
            )
            if duration <= 0:
                continue

            score = score_time_pair(
                start_option,
                end_option,
                duration=duration,
                overnight=overnight,
            )
            if best_score is None or score > best_score:
                best_score = score
                best_pair = (start_option.value, end_option.value, overnight)

    if best_pair is None:
        raise ValueError("invalid time range")
    return best_pair


def strip_accents(value: str) -> str:
    """Elimina acentos para facilitar la detección de días."""

    return (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
    )


def normalize_lines(text: str) -> list[str]:
    lines = [line.strip() for line in str(text).splitlines()]
    return [line for line in lines if line]


def extract_time_range(text: str) -> tuple[str, str]:
    """Extrae el rango de horas desde el texto normalizado."""

    cleaned_text = normalize_common_time_typos(text)
    match = TIME_RANGE_PATTERN.search(cleaned_text)
    if not match:
        raise ValueError("no time range found")
    return match.group(1), match.group(2)


def has_meridiem(value: str) -> bool:
    return bool(extract_meridiem(value))


def looks_24h(value: str) -> bool:
    raw = normalize_meridiem_token(value)
    match = re.match(r"^(\d{1,2})", raw)
    hour = int(match.group(1)) if match else 0
    return hour >= 13 or ":" in raw


def strip_seconds(value: str) -> str:
    raw = str(value).strip()
    match = re.match(r"^(\d{1,2}:\d{2})(?::\d{2})?$", raw)
    return match.group(1) if match else raw


def extract_days(text: str) -> list[str]:
    days, _ = extract_days_with_meta(text)
    return days


def extract_days_with_meta(text: str) -> tuple[list[str], bool]:
    """Extrae días desde un rango o un día individual."""

    except_match = ALL_DAYS_EXCEPT_PATTERN.search(text)
    if except_match:
        excluded: list[str] = []
        for token in STRICT_DAY_PATTERN.findall(except_match.group("excluded")):
            day = normalize_day_token(token)
            if day not in excluded:
                excluded.append(day)
        return [day for day in DAY_ORDER if day not in excluded], False

    range_match = RANGE_PATTERN.search(text)
    if range_match:
        start_token, end_token = range_match.group(1), range_match.group(2)
        start_day = normalize_day_token(start_token)
        end_day = normalize_day_token(end_token)
        return expand_day_range(start_day, end_day), False

    if ALL_DAYS_PATTERN.search(text):
        return list(DAY_ORDER), True

    matches = STRICT_DAY_PATTERN.findall(text)
    if matches:
        days: list[str] = []
        for token in matches:
            day = normalize_day_token(token)
            if day not in days:
                days.append(day)
        return days, False

    single_match = SINGLE_DAY_PATTERN.search(text)
    if not single_match:
        raise ValueError("no day found")
    return [normalize_day_token(single_match.group(1))], False


def normalize_day_token(token: str) -> str:
    """Normaliza un token de día y permite plural simple."""

    try:
        return normalize_day(token)
    except ValueError:
        if token.endswith("s") and len(token) > 1:
            return normalize_day(token[:-1])
        raise


def expand_day_range(start_day: str, end_day: str) -> list[str]:
    """Expande un rango de días respetando el orden semanal."""

    order = list(DAY_ORDER)
    start_index = order.index(start_day)
    end_index = order.index(end_day)
    if start_index <= end_index:
        return order[start_index : end_index + 1]
    return order[start_index:] + order[: end_index + 1]


def next_day(day: str) -> str:
    order = list(DAY_ORDER)
    return order[(order.index(day) + 1) % len(order)]


def build_day_events(
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
                dia=next_day(day),
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


@dataclass(frozen=True)
class TimeOption:
    value: str
    source: str
    has_meridiem: bool


def parse_time_token(value: str) -> list[TimeOption]:
    raw = normalize_meridiem_token(strip_seconds(value))
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
            return [TimeOption(normalized, "literal", False)]
        normalized = normalize_time(f"{hour}:{minute:02d}{meridiem}")
        return [TimeOption(normalized, "explicit", True)]

    normalized = normalize_time(f"{hour}:{minute:02d}")
    options = [TimeOption(normalized, "literal", False)]
    if not has_colon and 1 <= hour <= 11:
        pm_value = normalize_time(f"{hour}:{minute:02d}pm")
        if pm_value != normalized:
            options.append(TimeOption(pm_value, "pm_inferred", False))
    return options


def extract_meridiem(value: str) -> str:
    raw = normalize_meridiem_token(value)
    match = re.search(r"([ap]m)$", raw)
    return match.group(1) if match else ""


def normalize_meridiem_token(value: str) -> str:
    raw = str(value).strip().lower()
    raw = raw.replace(".", "")
    raw = re.sub(r"\s+", "", raw)
    raw = raw.replace("a m", "am").replace("p m", "pm")
    return raw


def normalize_common_time_typos(text: str) -> str:
    """Corrige variantes comunes de AM/PM copiadas desde WhatsApp."""

    normalized = re.sub(
        r"(\b\d{1,2}(?::\d{2})?(?::\d{2})?)\s+a\s+([ap])\s*\.?\s*m\.?\b",
        r"\1 \2m",
        str(text),
        flags=re.IGNORECASE,
    )
    return re.sub(
        r"(\b\d{1,2}(?::\d{2})?(?::\d{2})?)\s*([ap])(?:[\.\s]*m\.?)\b",
        r"\1 \2m",
        normalized,
        flags=re.IGNORECASE,
    )


def normalize_parser_text(text: str) -> str:
    """Limpia separadores y espacios unicode antes de aplicar regex."""

    normalized = str(text)
    normalized = (
        normalized.replace("\u00a0", " ")
        .replace("\u202f", " ")
        .replace("\u2009", " ")
        .replace("：", ":")
        .replace("．", ".")
    )
    normalized = re.sub(r"[–—−]", "-", normalized)
    normalized = re.sub(r"\s*:\s*", ":", normalized)
    return normalize_common_time_typos(normalized)


def score_time_pair(
    start: TimeOption,
    end: TimeOption,
    *,
    duration: int,
    overnight: bool,
) -> tuple[int, int, int, int]:
    overnight_penalty = 0 if not overnight else -200
    duration_score = -abs(duration - 120)
    literal_score = (
        (25 if start.source == "literal" else 0)
        + (25 if end.source == "literal" else 0)
    )
    inferred_pm_score = (
        (15 if start.source == "pm_inferred" else 0)
        + (15 if end.source == "pm_inferred" else 0)
    )
    return (
        overnight_penalty,
        -duration,
        inferred_pm_score + literal_score,
        duration_score,
    )


def minutes(value: str) -> int:
    normalized = normalize_time(value)
    return (int(normalized[:2]) * 60) + int(normalized[3:])

