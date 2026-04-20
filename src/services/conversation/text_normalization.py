"""Normalizacion de texto para reglas conversacionales deterministicas."""

from __future__ import annotations

import re
import unicodedata


def strip_accents(value: str) -> str:
    """Elimina acentos para comparaciones por reglas."""

    return (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
    )


def normalize_text(value: str | None) -> str:
    """Normaliza texto preservando solo la forma util para clasificacion."""

    normalized = strip_accents(str(value or "")).lower()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def contains_any(text: str, phrases: set[str]) -> bool:
    """Indica si alguna frase aparece como termino o frase normalizada."""

    if not text:
        return False
    for phrase in phrases:
        normalized_phrase = normalize_text(phrase)
        if not normalized_phrase:
            continue
        if re.search(rf"(?<!\w){re.escape(normalized_phrase)}(?!\w)", text):
            return True
    return False


__all__ = ["contains_any", "normalize_text", "strip_accents"]
