"""Helpers de normalización para comandos de tracking."""

from __future__ import annotations

from datetime import datetime
from typing import Any

_ALLOWED_ACTOR_TYPES = {"student", "agent", "system"}


def normalize_actor_type(actor_type: object, *, default: str = "student") -> str:
    """Normaliza el actor de tracking al conjunto permitido."""

    candidate = str(actor_type or default).strip().lower()
    if candidate not in _ALLOWED_ACTOR_TYPES:
        raise ValueError(f"actor_type invalido: {candidate!r}")
    return candidate


def normalize_completion_pct(
    value: object,
    *,
    default: int | None = None,
) -> int | None:
    """Coacciona el porcentaje de avance a un entero entre 0 y 100."""

    if value is None:
        return default
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"completion_pct invalido: {value!r}") from exc
    if normalized < 0 or normalized > 100:
        raise ValueError(f"completion_pct fuera de rango: {normalized!r}")
    return normalized


def normalize_optional_score(name: str, value: object) -> int | None:
    """Valida scores opcionales de comprensión y energía."""

    if value is None:
        return None
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} invalido: {value!r}") from exc
    if normalized < 1 or normalized > 5:
        raise ValueError(f"{name} fuera de rango: {normalized!r}")
    return normalized


def normalize_notes(notes: object) -> str | None:
    """Limpia notas libres y preserva `None` si quedan vacías."""

    if notes is None:
        return None
    cleaned = str(notes).strip()
    if not cleaned:
        return None
    if len(cleaned) > 1000:
        raise ValueError("notes excede el máximo de 1000 caracteres")
    return cleaned


def normalize_payload(payload: object) -> dict[str, object]:
    """Normaliza payloads libres a un objeto JSON simple."""

    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError("checkin_payload debe ser un objeto/dict")
    return dict(payload)


def normalize_timestamp(
    value: object,
    *,
    default: datetime | None = None,
) -> datetime | None:
    """Acepta `datetime`, ISO string o `None`."""

    if value is None:
        return default
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return default
        try:
            return datetime.fromisoformat(cleaned)
        except ValueError as exc:
            raise ValueError(f"timestamp invalido: {value!r}") from exc
    raise ValueError(f"timestamp invalido: {value!r}")


def ensure_feedback_content(
    *,
    notes: str | None,
    completion_pct: int | None,
    comprehension_score: int | None,
    energy_score: int | None,
    payload: dict[str, Any],
) -> None:
    """Evita insertar feedback completamente vacío."""

    if (
        notes is None
        and completion_pct is None
        and comprehension_score is None
        and energy_score is None
        and not payload
    ):
        raise ValueError("feedback vacio: debes enviar notas, scores o payload")
