"""Normalizacion de etiquetas cortas para eventos renderizados."""

from __future__ import annotations

import re


def normalize_activity_label(title: str, category: str | None = None) -> str:
    """Convierte descripciones largas en etiquetas cortas y consistentes."""
    raw = str(title or "").strip()
    if not raw:
        return "Actividad"

    normalized_category = str(category or "").strip().lower()
    if normalized_category == "laboral":
        return "Trabajo laboral"
    if normalized_category == "academico":
        return _compact_academic_label(raw)

    normalized = _normalize_label_text(raw)
    if "trabajo de grado" in normalized:
        return _compact_academic_label(raw)
    if "gym" in normalized or "gimnasio" in normalized:
        return "Gym"
    if "perro" in normalized:
        return "Sacar al perro"
    if "trabaj" in normalized and "universidad" in normalized:
        return "Trabajos universidad"
    if "trabaj" in normalized:
        return "Hacer trabajos"

    words = [word for word in re.findall(r"[a-zA-ZÀ-ÿ]+", raw) if word]
    stopwords = {
        "tengo",
        "que",
        "hacer",
        "todos",
        "los",
        "las",
        "dias",
        "dia",
        "desde",
        "hasta",
        "para",
        "la",
        "el",
        "de",
        "del",
        "mi",
        "mis",
        "por",
    }
    filtered = [word for word in words if _normalize_label_text(word) not in stopwords]
    selected = filtered if filtered else words
    compact = " ".join(selected[:4]).strip()
    if not compact:
        return "Actividad"
    return compact.title()


def _normalize_label_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _compact_academic_label(raw: str) -> str:
    words = [word for word in re.findall(r"[A-Za-zÀ-ÿ0-9&]+", raw) if word]
    if not words:
        return "Materia"
    compact = " ".join(words[:5]).strip()
    return compact
