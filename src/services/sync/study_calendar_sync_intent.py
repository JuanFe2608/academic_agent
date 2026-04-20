"""Deteccion de solicitudes para sincronizar sesiones de estudio con Outlook."""

from __future__ import annotations

import re
import unicodedata

_SYNC_TERMS = {
    "sincroniza",
    "sincronizar",
    "sube",
    "crear en",
    "agrega a",
    "manda a",
    "conecta",
}
_OUTLOOK_TERMS = {"outlook", "calendario", "calendar", "agenda", "microsoft"}
_STUDY_PLAN_TERMS = {"plan", "sesiones", "sesion", "estudio", "bloques", "cronograma"}
_TODO_TERMS = {"todo", "to do", "microsoft todo", "microsoft to do", "lista de tareas"}


def is_study_calendar_sync_message(text: str | None) -> bool:
    """Detecta si el usuario quiere enviar sesiones del plan a Outlook."""

    normalized = _normalize_text(text)
    if not normalized:
        return False
    if _contains_any(normalized, _TODO_TERMS):
        return False
    return (
        _contains_any(normalized, _SYNC_TERMS)
        and _contains_any(normalized, _OUTLOOK_TERMS)
        and _contains_any(normalized, _STUDY_PLAN_TERMS)
    )


def _contains_any(text: str, terms: set[str]) -> bool:
    return any(
        re.search(rf"(?<!\w){re.escape(_normalize_text(term))}(?!\w)", text)
        for term in terms
        if _normalize_text(term)
    )


def _normalize_text(value: str | None) -> str:
    normalized = (
        unicodedata.normalize("NFKD", str(value or ""))
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )
    return re.sub(r"\s+", " ", normalized).strip()


__all__ = ["is_study_calendar_sync_message"]
