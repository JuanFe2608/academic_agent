"""Parser determinista para respuestas cerradas del cuestionario."""

from __future__ import annotations

import re

from agents.support.personalization.models import ParsedLikertAnswer
from agents.support.personalization.questionnaire import LIKERT_OPTIONS

_ANSWER_PATTERN = re.compile(r"^\s*([0-3])(?:\s*[-.)]\s*.*)?\s*$")


def parse_likert_answer(raw: str) -> ParsedLikertAnswer:
    """Valida y normaliza una respuesta Likert entre 0 y 3."""

    if raw is None or not str(raw).strip():
        return ParsedLikertAnswer(error="empty_answer")

    match = _ANSWER_PATTERN.fullmatch(str(raw))
    if not match:
        return ParsedLikertAnswer(error="invalid_answer")

    value = int(match.group(1))
    if value not in LIKERT_OPTIONS:
        return ParsedLikertAnswer(error="out_of_range")
    return ParsedLikertAnswer(value=value)


def likert_label(value: int) -> str:
    """Retorna la etiqueta humana de un valor Likert."""

    if value not in LIKERT_OPTIONS:
        raise ValueError(f"Valor Likert invalido: {value}")
    return LIKERT_OPTIONS[value]

