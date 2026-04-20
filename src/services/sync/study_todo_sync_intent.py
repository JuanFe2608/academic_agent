"""Deteccion de solicitudes para sincronizar pendientes con Microsoft To Do."""

from __future__ import annotations

import re
import unicodedata

_SYNC_TERMS = {
    "sincroniza",
    "sincronizar",
    "sube",
    "crear en",
    "crea en",
    "agrega a",
    "manda a",
    "proyecta",
}
_TODO_TERMS = {
    "todo",
    "to do",
    "microsoft todo",
    "microsoft to do",
    "lista de tareas",
    "tareas",
    "pendientes",
}
_ACTIONABLE_TERMS = {
    "sesiones",
    "sesion",
    "estudio",
    "omitidas",
    "perdidas",
    "atrasadas",
    "no resueltas",
    "accionables",
    "pendientes",
}


def is_study_todo_sync_message(text: str | None) -> bool:
    """Detecta si el usuario quiere proyectar pendientes academicos a To Do."""

    normalized = _normalize_text(text)
    if not normalized:
        return False
    return (
        _contains_any(normalized, _SYNC_TERMS)
        and _contains_any(normalized, _TODO_TERMS)
        and _contains_any(normalized, _ACTIONABLE_TERMS)
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


__all__ = ["is_study_todo_sync_message"]
