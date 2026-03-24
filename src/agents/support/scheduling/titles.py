"""Normalización corta y estable de títulos para horarios fijos."""

from __future__ import annotations

import re
import unicodedata

from .constants import ScheduleBlockType

_STOPWORDS = {
    "a",
    "al",
    "ademas",
    "con",
    "de",
    "del",
    "el",
    "en",
    "la",
    "las",
    "los",
    "mis",
    "mi",
    "para",
    "por",
    "que",
    "voy",
    "voyal",
    "voyala",
    "ir",
    "luego",
    "despues",
    "después",
    "tengo",
    "hago",
    "hacer",
    "salgo",
    "salir",
    "los",
    "variable",
    "variables",
    "fijo",
    "fija",
}


def normalize_schedule_title(
    raw_title: str,
    schedule_type: ScheduleBlockType,
    raw_text: str = "",
) -> tuple[str, str]:
    """Retorna `(original_title, normalized_title)` para el bloque."""

    original_title = _clean_title(raw_title)
    normalized_text = _normalize_text(raw_text or original_title)
    if schedule_type == "work":
        return original_title or "Trabajo", "Trabajo"
    if schedule_type == "academic":
        normalized_title = _smart_title_case(
            _strip_leading_connectors(original_title or raw_text or "Clase")
        )
        return original_title or normalized_title, normalized_title

    normalized_title = _normalize_extracurricular_title(original_title or raw_text)
    return original_title or normalized_title, normalized_title


def _normalize_extracurricular_title(text: str) -> str:
    raw = _clean_title(text)
    normalized = _normalize_text(raw)
    if not normalized:
        return "Actividad extracurricular"

    if "gym" in normalized or "gimnasio" in normalized:
        return "Gimnasio"
    if "perro" in normalized and ("saco" in normalized or "pase" in normalized):
        return "Sacar al perro"
    if "compr" in normalized and "amig" in normalized:
        return "Compras con amigas"
    if "salida" in normalized and "amig" in normalized:
        return "Salida con amigas"
    if "natacion" in normalized:
        return "Natación"
    if "trot" in normalized:
        return "Trotar"
    if "igles" in normalized:
        return "Iglesia"
    if "laboratorio" in normalized:
        return "Laboratorio"

    words = [word for word in re.findall(r"[A-Za-zÀ-ÿ0-9]+", raw) if word]
    filtered = [word for word in words if _normalize_text(word) not in _STOPWORDS]
    selected = filtered if filtered else words
    compact = " ".join(selected[:4]).strip()
    return _smart_title_case(compact or raw or "Actividad extracurricular")


def _clean_title(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip(" ,.;:-")
    return text


def _normalize_text(value: str) -> str:
    folded = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", folded.lower()).strip()


def _smart_title_case(value: str) -> str:
    text = _clean_title(value)
    if not text:
        return ""
    letters = [char for char in text if char.isalpha()]
    uppercase_ratio = (
        sum(1 for char in letters if char.isupper()) / len(letters)
        if letters
        else 0.0
    )
    if uppercase_ratio >= 0.7 or text.islower():
        return text.title()
    return text


def _strip_leading_connectors(value: str) -> str:
    return re.sub(
        r"^\s*(?:y|e|luego|despues|después|ademas|además)\s+",
        "",
        str(value or ""),
        flags=re.IGNORECASE,
    ).strip()
