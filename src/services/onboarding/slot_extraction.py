"""Extraccion deterministica de slots para onboarding."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from .config import OnboardingConfig

ONBOARDING_SLOT_FIELDS = (
    "full_name",
    "student_code",
    "age",
    "institutional_email",
    "semester",
    "average_grade",
)

_EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+\b"
)
_CODE_WITH_LABEL_PATTERN = re.compile(
    r"\b(?:c[oó]digo(?:\s+estudiantil)?|cod)\D{0,12}(\d{4,20})\b",
    re.IGNORECASE,
)
_AGE_PATTERNS = (
    re.compile(r"\b(?:tengo|edad(?:\s+es)?)\D{0,8}(\d{1,2})\b", re.IGNORECASE),
    re.compile(r"\b(\d{1,2})\s*(?:anos|anios|años)\b", re.IGNORECASE),
)
_SEMESTER_PATTERNS = (
    re.compile(
        r"\b(?:semestre|voy\s+en|estoy\s+en|curso)\D{0,12}"
        r"(\d{1,2}|primer(?:o)?|segundo|tercero|cuarto|quinto|sexto|septimo|octavo|noveno|decimo|undecimo|duodecimo)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(\d{1,2}|primer(?:o)?|segundo|tercero|cuarto|quinto|sexto|septimo|octavo|noveno|decimo|undecimo|duodecimo)"
        r"\s+semestre\b",
        re.IGNORECASE,
    ),
)
_AVERAGE_PATTERN = re.compile(
    r"\bpromedio(?:\s+(?:academico|acumulado))?(?:\s+(?:es|de))?\D{0,10}"
    r"(\d{1,3}(?:[.,]\d+)?)\b",
    re.IGNORECASE,
)
_NAME_MARKER_PATTERN = re.compile(
    r"\b(?:soy|me\s+llamo|mi\s+nombre\s+es|nombre\s+es)\s+(.+)",
    re.IGNORECASE,
)
_NAME_BOUNDARY_PATTERN = re.compile(
    r"\s+(?:y\s+)?(?:tengo|edad|c[oó]digo|cod|correo|email|e-mail|voy|estoy|curso|semestre|promedio)\b",
    re.IGNORECASE,
)
_ORDINAL_SEMESTERS = {
    "primer": "1",
    "primero": "1",
    "segundo": "2",
    "tercero": "3",
    "cuarto": "4",
    "quinto": "5",
    "sexto": "6",
    "septimo": "7",
    "octavo": "8",
    "noveno": "9",
    "decimo": "10",
    "undecimo": "11",
    "duodecimo": "12",
}


@dataclass(frozen=True)
class OnboardingSlotExtraction:
    """Slots crudos detectados en un mensaje de onboarding."""

    raw_slots: dict[str, str] = field(default_factory=dict)

    def has_slots(self) -> bool:
        return bool(self.raw_slots)


def extract_onboarding_slots(
    text: str | None,
    *,
    config: OnboardingConfig,
    candidate_fields: Iterable[str] | None = None,
) -> OnboardingSlotExtraction:
    """Extrae slots crudos sin validar ni modificar estado."""

    raw_text = str(text or "").strip()
    if not raw_text:
        return OnboardingSlotExtraction()

    fields = set(candidate_fields or ONBOARDING_SLOT_FIELDS)
    slots: dict[str, str] = {}

    if "full_name" in fields:
        name = _extract_full_name(raw_text)
        if name:
            slots["full_name"] = name

    if "student_code" in fields:
        code = _extract_student_code(raw_text, config=config)
        if code:
            slots["student_code"] = code

    if "age" in fields:
        age = _first_pattern_value(raw_text, _AGE_PATTERNS)
        if age:
            slots["age"] = age

    if "institutional_email" in fields:
        email = _extract_email(raw_text)
        if email:
            slots["institutional_email"] = email

    if "semester" in fields:
        semester = _extract_semester(raw_text)
        if semester:
            slots["semester"] = semester

    if "average_grade" in fields:
        average = _extract_average(raw_text)
        if average:
            slots["average_grade"] = average

    return OnboardingSlotExtraction(raw_slots=slots)


def _extract_full_name(raw_text: str) -> str | None:
    match = _NAME_MARKER_PATTERN.search(raw_text)
    if match is None:
        return None
    candidate = match.group(1)
    candidate = re.split(
        r"[,;\n.]|\s+(?=c[oó]digo\b)",
        candidate,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    boundary = _NAME_BOUNDARY_PATTERN.search(candidate)
    if boundary is not None:
        candidate = candidate[: boundary.start()]
    candidate = re.sub(r"\s+", " ", candidate).strip(" .:-")
    return candidate or None


def _extract_student_code(raw_text: str, *, config: OnboardingConfig) -> str | None:
    labeled = _CODE_WITH_LABEL_PATTERN.search(raw_text)
    if labeled is not None:
        return labeled.group(1)
    exact_length = re.search(rf"\b\d{{{int(config.student_code_length)}}}\b", raw_text)
    if exact_length is not None:
        return exact_length.group(0)
    return None


def _extract_email(raw_text: str) -> str | None:
    match = _EMAIL_PATTERN.search(raw_text)
    return match.group(0) if match else None


def _first_pattern_value(raw_text: str, patterns: Iterable[re.Pattern[str]]) -> str | None:
    for pattern in patterns:
        match = pattern.search(raw_text)
        if match is not None:
            return match.group(1)
    return None


def _extract_semester(raw_text: str) -> str | None:
    raw_value = _first_pattern_value(raw_text, _SEMESTER_PATTERNS)
    if not raw_value:
        return None
    normalized = _strip_accents(raw_value.lower().strip())
    return _ORDINAL_SEMESTERS.get(normalized, normalized)


def _extract_average(raw_text: str) -> str | None:
    match = _AVERAGE_PATTERN.search(raw_text)
    return match.group(1).replace(",", ".") if match else None


def _strip_accents(value: str) -> str:
    return (
        value.replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
    )


__all__ = [
    "ONBOARDING_SLOT_FIELDS",
    "OnboardingSlotExtraction",
    "extract_onboarding_slots",
]
