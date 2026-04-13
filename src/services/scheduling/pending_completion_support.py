"""Helpers puros para completar pendientes sin duplicar texto anterior."""

from __future__ import annotations

import re

_DAY_REFERENCE_PATTERN = re.compile(
    r"\b(?:lunes|martes|miercoles|miércoles|jueves|viernes|sabado|sábado|domingo|"
    r"lun|mar|mie|jue|vie|sab|dom|l-v|lun-vie|lunes\s+a\s+viernes|"
    r"todos\s+los\s+dias|todos\s+los\s+días|cada\s+dia|cada\s+día)\b",
    re.IGNORECASE,
)
_TIME_REFERENCE_PATTERN = re.compile(
    r"\b\d{1,2}(?::\d{2})?(?:\s*[ap]\.?\s*m\.?)?\b",
    re.IGNORECASE,
)
_STRUCTURE_HINT_PATTERN = re.compile(r"(?:\s[-—–]\s|:\s|\n)")
_TRAILING_TIME_FRAGMENT_PATTERN = re.compile(
    r"(?:\s[-—–:]\s*|\s+)\d{1,2}(?::\d{2})?(?:\s*[ap]\.?\s*m\.?)?"
    r"(?:\s*(?:a|hasta|-)\s*\d{0,2}(?::\d{2})?(?:\s*[ap]\.?\s*m\.?)?)?\s*$",
    re.IGNORECASE,
)


def build_pending_completion_text(
    pending_raw_text: str | None,
    response_text: str,
) -> tuple[str, bool]:
    """Elige si la respuesta completa reemplaza el texto previo o se concatena."""

    pending_raw = str(pending_raw_text or "").strip()
    response = str(response_text or "").strip()
    if not response:
        return pending_raw, False
    if _looks_like_full_schedule_rewrite(response):
        return response, True
    combined = " ".join(part for part in [pending_raw, response] if part)
    return combined, False


def _looks_like_full_schedule_rewrite(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    has_day_reference = bool(_DAY_REFERENCE_PATTERN.search(raw))
    has_structure_hint = bool(_STRUCTURE_HINT_PATTERN.search(raw))
    time_references = _TIME_REFERENCE_PATTERN.findall(raw)
    has_time_range_hint = len(time_references) >= 2
    return has_day_reference and (has_structure_hint or has_time_range_hint)


def clean_pending_display_label(text: str | None) -> str:
    """Limpia restos de horario incrustados en títulos pendientes."""

    raw = str(text or "").strip()
    if not raw:
        return ""
    cleaned = _TRAILING_TIME_FRAGMENT_PATTERN.sub("", raw).strip(" ,.-—–:")
    return cleaned or raw


__all__ = [
    "build_pending_completion_text",
    "clean_pending_display_label",
]
