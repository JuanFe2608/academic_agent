"""Helpers heurísticos reutilizables para parsing de scheduling."""

from __future__ import annotations

import re

from services.scheduling.constants import DAY_ORDER, SPANISH_TO_ENGLISH
from services.scheduling.text_parser import extract_natural_schedule_components
from services.scheduling.validation import normalize_day, normalize_time

_DAY_TOKEN_PATTERN = (
    r"(?:"
    r"lunes|lun|l|"
    r"martes|mar|ma|"
    r"miercoles|miércoles|mier|mie|mi|x|"
    r"jueves|jue|ju|j|"
    r"viernes|vie|vi|v|"
    r"sabados|sábado|sabado|sab|sa|s|"
    r"domingos|domingo|dom|do|d"
    r")"
)
_DAY_RANGE_PATTERN = re.compile(
    rf"\b({_DAY_TOKEN_PATTERN})\b\s*(?:-|a|hasta)\s*\b({_DAY_TOKEN_PATTERN})\b",
    re.IGNORECASE,
)
_DAY_LIST_PATTERN = re.compile(rf"\b({_DAY_TOKEN_PATTERN})\b", re.IGNORECASE)
_ALL_DAYS_PATTERN = re.compile(
    r"\b(?:todos\s+los\s+dias|todos\s+los\s+días|cada\s+dia|cada\s+día|diario|diariamente)\b",
    re.IGNORECASE,
)
_ALL_DAYS_EXCEPT_PATTERN = re.compile(
    r"\b(?:todos\s+los\s+dias|todos\s+los\s+días|cada\s+dia|cada\s+día)\b\s+menos\s+(?P<excluded>.+)",
    re.IGNORECASE,
)
_TIME_RANGE_PATTERN = re.compile(
    r"(?:de|desde)?\s*(?:las\s+)?\d{1,2}(?::\d{2})?(?::\d{2})?(?:\s*[ap]\.?\s*m\.?)?\s*"
    r"(?:-|a|hasta)\s*(?:las\s+)?\d{1,2}(?::\d{2})?(?::\d{2})?(?:\s*[ap]\.?\s*m\.?)?",
    re.IGNORECASE,
)
_SEPARATOR_PATTERN = re.compile(r"(?:[\n;]+|,\s*(?=[A-Za-zÁÉÍÓÚáéíóúÑñ]))")


def split_segments(text: str) -> list[str]:
    parts = [part.strip() for part in _SEPARATOR_PATTERN.split(text) if part.strip()]
    return parts or [str(text).strip()]


def extract_days_from_text(text: str) -> list[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    except_match = _ALL_DAYS_EXCEPT_PATTERN.search(raw)
    if except_match:
        excluded = {
            _normalize_day_token(match.group(1))
            for match in _DAY_LIST_PATTERN.finditer(except_match.group("excluded"))
        }
        return [day for day in DAY_ORDER if day not in excluded]
    range_match = _DAY_RANGE_PATTERN.search(raw)
    if range_match:
        start_day = _normalize_day_token(range_match.group(1))
        end_day = _normalize_day_token(range_match.group(2))
        return _expand_day_range(start_day, end_day)
    if _ALL_DAYS_PATTERN.search(raw):
        return list(DAY_ORDER)
    days: list[str] = []
    for match in _DAY_LIST_PATTERN.finditer(raw):
        day = _normalize_day_token(match.group(1))
        if day not in days:
            days.append(day)
    return days


def extract_time_range(text: str) -> tuple[str, str]:
    seed = text if extract_days_from_text(text) else f"Lunes {text}"
    parsed = extract_natural_schedule_components(seed)
    return normalize_time(str(parsed["start"])), normalize_time(str(parsed["end"]))


def infer_title(text: str, default_title: str) -> str:
    cleaned = str(text or "")
    cleaned = _DAY_RANGE_PATTERN.sub(" ", cleaned)
    cleaned = _ALL_DAYS_EXCEPT_PATTERN.sub(" ", cleaned)
    cleaned = _ALL_DAYS_PATTERN.sub(" ", cleaned)
    cleaned = _DAY_LIST_PATTERN.sub(" ", cleaned)
    cleaned = _TIME_RANGE_PATTERN.sub(" ", cleaned)
    cleaned = re.sub(
        r"\b(de|desde|hasta|las|los|el|la|en|por|para|todos|dias|días|actualmente|voy|tengo|hago|y|e)\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.-")
    if not cleaned:
        return default_title
    compact = " ".join(cleaned.split()[:6]).strip()
    return compact.title()


def to_day_key(spanish_day: str) -> str:
    normalized = normalize_day(spanish_day)
    day_key = SPANISH_TO_ENGLISH.get(normalized)
    if not day_key:
        raise ValueError(f"Dia no soportado: {spanish_day!r}")
    return day_key


def _normalize_day_token(token: str) -> str:
    normalized = normalize_day(token)
    return to_day_key(normalized)


def _expand_day_range(start_day: str, end_day: str) -> list[str]:
    start_index = DAY_ORDER.index(start_day)
    end_index = DAY_ORDER.index(end_day)
    if start_index <= end_index:
        return DAY_ORDER[start_index : end_index + 1]
    return DAY_ORDER[start_index:] + DAY_ORDER[: end_index + 1]


__all__ = [
    "extract_days_from_text",
    "extract_time_range",
    "infer_title",
    "split_segments",
    "to_day_key",
]
