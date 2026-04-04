"""Utilidades ligeras de runtime para el flujo de personalizacion."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def current_timestamp(timezone_name: object) -> str:
    """Retorna un timestamp ISO con la zona del usuario cuando es valida."""

    zone_name = str(timezone_name or "").strip()
    if zone_name:
        try:
            return datetime.now(ZoneInfo(zone_name)).isoformat()
        except ZoneInfoNotFoundError:
            pass
    return datetime.now(timezone.utc).isoformat()


def coerce_int_answer_map(raw_answers: object) -> dict[str, int]:
    """Normaliza un diccionario de respuestas hacia enteros."""

    answers: dict[str, int] = {}
    if not isinstance(raw_answers, dict):
        return answers
    for question_id, value in raw_answers.items():
        try:
            answers[str(question_id)] = int(value)
        except (TypeError, ValueError):
            continue
    return answers
