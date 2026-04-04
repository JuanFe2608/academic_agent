"""Parser determinista para respuestas cerradas del cuestionario."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

from .models import ParsedChoiceAnswer, ParsedLikertAnswer
from .questionnaire import LIKERT_ALIASES, LIKERT_OPTIONS

_LEADING_NUMERIC_PATTERN = re.compile(r"^\s*([0-3])(?:\s*[-.)=:]\s*|\s+.*|$)")
_LEADING_CHOICE_PATTERN = re.compile(r"^\s*([1-9])(?:\s*[-.)=:]\s*|\s+.*|$)")


def parse_likert_answer(raw: str) -> ParsedLikertAnswer:
    """Valida y normaliza una respuesta Likert entre 0 y 3.

    Acepta como formato principal el valor numerico y, como apoyo, algunas
    equivalencias textuales comunes de la escala.
    """

    if raw is None or not str(raw).strip():
        return ParsedLikertAnswer(error="empty_answer")

    raw_text = str(raw).strip()
    numeric_match = _LEADING_NUMERIC_PATTERN.match(raw_text)
    if numeric_match:
        value = int(numeric_match.group(1))
        if value in LIKERT_OPTIONS:
            return ParsedLikertAnswer(value=value)

    normalized = _normalize(raw_text)
    for value, aliases in LIKERT_ALIASES.items():
        if normalized in aliases:
            return ParsedLikertAnswer(value=value)

    return ParsedLikertAnswer(error="invalid_answer")


def likert_label(value: int) -> str:
    """Retorna la etiqueta humana de un valor Likert."""

    if value not in LIKERT_OPTIONS:
        raise ValueError(f"Valor Likert invalido: {value}")
    return LIKERT_OPTIONS[value]


def parse_choice_answer(raw: str, *, valid_values: Iterable[int]) -> ParsedChoiceAnswer:
    """Valida una respuesta numerica de opcion unica."""

    valid_set = {int(value) for value in valid_values}
    if raw is None or not str(raw).strip():
        return ParsedChoiceAnswer(error="empty_answer")

    raw_text = str(raw).strip()
    numeric_match = _LEADING_CHOICE_PATTERN.match(raw_text)
    if not numeric_match:
        return ParsedChoiceAnswer(error="invalid_answer")

    value = int(numeric_match.group(1))
    if value not in valid_set:
        return ParsedChoiceAnswer(error="invalid_answer")
    return ParsedChoiceAnswer(value=value)


def _normalize(value: str) -> str:
    folded = (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    normalized = re.sub(r"\s+", " ", folded.lower()).strip()
    return normalized
