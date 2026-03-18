"""Nodo para recolectar detalles de actividades extracurriculares."""

from __future__ import annotations

import re

from agents.support.nodes.utils import (
    append_message,
    detect_new_input,
    normalize_text,
    parse_yes_no,
)
from agents.support.state import AgentState, ExtracurricularItem
from agents.support.tools.llm import llm_normalize_extracurricular_items
from agents.support.tools.schedule_parser import extract_natural_schedule_components, is_ambiguous_time_range

from .prompt import (
    PROMPT_DETAILS,
    PROMPT_MORE,
)

_DAY_MARKER_PATTERN = re.compile(
    r"\b(lunes|martes|miercoles|miércoles|jueves|viernes|sabado|sábado|domingos|domingo|lun|mar|mie|jue|vie|sab|dom|todos\s+los\s+dias|todos\s+los\s+días|cada\s+dia|cada\s+día|diario|diariamente)\b"
)
_STOPWORDS = {
    "a",
    "al",
    "con",
    "de",
    "del",
    "el",
    "la",
    "las",
    "los",
    "mi",
    "mis",
    "solo",
    "para",
    "por",
    "fija",
    "fijo",
    "flexible",
    "variable",
    "tentativo",
    "tentativa",
    "todos",
    "dias",
    "dia",
    "cada",
    "desde",
    "hasta",
    "voy",
    "hago",
    "hacer",
    "voy",
    "actividad",
    "extracurricular",
    "y",
}
_TIME_RANGE_PATTERN = re.compile(
    r"(?:de|desde)?\s*(?:las\s+)?\d{1,2}(?::\d{2})?(?:\s*[ap]\.?\s*m\.?)?\s*(?:-|a|hasta)\s*(?:las\s+)?\d{1,2}(?::\d{2})?(?:\s*[ap]\.?\s*m\.?)?",
    re.IGNORECASE,
)
_ACTIVITY_SEPARATOR_PATTERN = re.compile(
    r"(?:\s*,\s*|\s+(?:y|e|ademas|además|tambien|también)\s+)",
    re.IGNORECASE,
)


def collect_extracurricular_details(state: AgentState) -> dict:
    """Recolecta actividades extracurriculares y avanza al draft."""
    messages = state.get("messages", [])
    has_new_input, last_text, current_count = detect_new_input(
        messages,
        state.get("user_message_count", 0),
        state.get("awaiting_user_input", False),
        state.get("last_user_text"),
    )
    stage = state.get("extras_collect_stage") or "awaiting_type"
    pending_is_variable = state.get("extras_pending_is_variable")

    if stage == "awaiting_more":
        answer = parse_yes_no(last_text) if has_new_input else None
        if answer is True:
            return {
                "extras_collect_stage": "awaiting_details",
                "extras_pending_is_variable": None,
                "phase": "extras",
                "user_message_count": current_count,
                "last_user_text": last_text,
                "awaiting_user_input": True,
                "messages": append_message(messages, "assistant", PROMPT_DETAILS),
            }
        if answer is False:
            return {
                "extras_collect_stage": "done",
                "extras_pending_is_variable": None,
                "phase": "draft",
                "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
                "last_user_text": last_text if has_new_input else state.get("last_user_text"),
                "awaiting_user_input": False,
                "messages": append_message(
                    messages, "assistant", "Listo. Voy a generar la vista previa de tu horario."
                ),
            }
        return {
            "extras_collect_stage": "awaiting_more",
            "phase": "extras",
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_text if has_new_input else state.get("last_user_text"),
            "awaiting_user_input": True,
            "messages": append_message(messages, "assistant", PROMPT_MORE),
        }

    if stage in (None, "awaiting_type"):
        return {
            "extras_collect_stage": "awaiting_details",
            "extras_pending_is_variable": pending_is_variable,
            "phase": "extras",
            "awaiting_user_input": True,
            "messages": append_message(messages, "assistant", PROMPT_DETAILS),
        }

    if not has_new_input or not last_text:
        return {
            "extras_collect_stage": "awaiting_details",
            "extras_pending_is_variable": pending_is_variable,
            "phase": "extras",
            "awaiting_user_input": True,
            "messages": append_message(messages, "assistant", PROMPT_DETAILS),
        }

    items, missing = parse_extracurricular_items(last_text, expected_is_variable=pending_is_variable)
    if missing:
        prompt = PROMPT_DETAILS + "\nFaltan: " + ", ".join(missing) + "."
        return {
            "extras_collect_stage": "awaiting_details",
            "extras_pending_is_variable": pending_is_variable,
            "phase": "extras",
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_text if has_new_input else state.get("last_user_text"),
            "awaiting_user_input": True,
            "messages": append_message(messages, "assistant", prompt),
        }

    extracurricular = list(state.get("extracurricular", []))
    extracurricular.extend(items)
    return {
        "extracurricular": extracurricular,
        "extras_collect_stage": "awaiting_more",
        "extras_pending_is_variable": None,
        "phase": "extras",
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_text if has_new_input else state.get("last_user_text"),
        "awaiting_user_input": True,
        "messages": append_message(messages, "assistant", PROMPT_MORE),
    }


def parse_extracurricular_text(
    text: str,
    expected_is_variable: bool | None = None,
) -> tuple[ExtracurricularItem, list[str]]:
    """Parsea texto de actividad extracurricular."""
    missing: list[str] = []
    normalized = normalize_text(text)

    nombre = _extract_value(normalized, r"nombre\s*[:\-]?\s*([a-z\s]+)")
    if not nombre:
        nombre = _infer_nombre(text)
    if not nombre:
        missing.append("nombre")
    nombre = _compact_activity_name(nombre)

    detalle = text.strip() if text.strip() else ""
    parsed_schedule: dict[str, object] | None = None
    if not detalle:
        missing.append("detalle")
    else:
        try:
            parsed_schedule = extract_natural_schedule_components(detalle)
        except ValueError as exc:
            error_text = str(exc).lower()
            if "ambiguous time range" in error_text or is_ambiguous_time_range(detalle):
                missing.append("aclarar AM o PM en el horario")
            else:
                missing.append("horario con dias y horas")

    es_variable = expected_is_variable
    if es_variable is None:
        es_variable = _parse_variable(normalized)
    if es_variable is None:
        es_variable = _infer_variability(normalized, parsed_schedule)

    detalle_normalizado = _build_normalized_detail(parsed_schedule) if parsed_schedule else detalle
    dias = list(parsed_schedule["days"]) if parsed_schedule else []
    frecuencia = _build_frequency_label(parsed_schedule)
    hora_inicio = str(parsed_schedule["start"]) if parsed_schedule else None
    hora_fin = str(parsed_schedule["end"]) if parsed_schedule else None

    item = ExtracurricularItem(
        nombre=nombre.strip() if nombre else "",
        es_variable=bool(es_variable),
        detalle=detalle_normalizado,
        dias=dias,
        frecuencia=frecuencia,
        hora_inicio=hora_inicio,
        hora_fin=hora_fin,
        tentativo=[],
    )
    return item, missing


def parse_extracurricular_items(
    text: str,
    expected_is_variable: bool | None = None,
) -> tuple[list[ExtracurricularItem], list[str]]:
    """Permite parsear varias actividades en un solo texto."""
    chunks = _split_extracurricular_chunks(text)
    items: list[ExtracurricularItem] = []
    missing: list[str] = []

    for index, chunk in enumerate(chunks, start=1):
        item, item_missing = parse_extracurricular_text(chunk, expected_is_variable)
        if item_missing:
            for field in item_missing:
                missing.append(f"actividad {index}: {field}")
            continue
        items.append(item)

    if items and not missing:
        return items, []

    llm_items = _parse_extracurricular_items_with_llm(text, expected_is_variable)
    if llm_items:
        return llm_items, []

    if not chunks:
        missing.append("detalle")

    return items, missing


def _parse_extracurricular_items_with_llm(
    text: str,
    expected_is_variable: bool | None = None,
) -> list[ExtracurricularItem]:
    normalized = llm_normalize_extracurricular_items(text)
    if not normalized:
        return []

    items: list[ExtracurricularItem] = []
    for item in normalized:
        nombre = str(item.get("nombre") or "").strip()
        detalle = str(item.get("detalle") or "").strip()
        es_variable = item.get("es_variable")
        if expected_is_variable is not None:
            es_variable = expected_is_variable
        if es_variable is None:
            es_variable = _infer_variability(normalize_text(detalle), None)
        if not nombre or not detalle or not isinstance(es_variable, bool):
            continue
        try:
            parsed_schedule = extract_natural_schedule_components(detalle)
        except ValueError:
            continue
        items.append(
            ExtracurricularItem(
                nombre=_compact_activity_name(nombre),
                es_variable=es_variable,
                detalle=_build_normalized_detail(parsed_schedule),
                dias=list(parsed_schedule["days"]),
                frecuencia=_build_frequency_label(parsed_schedule),
                hora_inicio=str(parsed_schedule["start"]),
                hora_fin=str(parsed_schedule["end"]),
                tentativo=[],
            )
        )
    return items


def _extract_value(text: str, pattern: str) -> str:
    match = re.search(pattern, text)
    return match.group(1) if match else ""


def _infer_nombre(text: str) -> str:
    normalized = normalize_text(text)
    cleaned = _TIME_RANGE_PATTERN.sub(" ", normalized)
    cleaned = _DAY_MARKER_PATTERN.sub(" ", cleaned)
    cleaned = re.sub(
        r"\b(?:todos\s+los\s+dias|todos\s+los\s+días|cada\s+dia|cada\s+día|diario|diariamente)\b",
        " ",
        cleaned,
    )
    cleaned = re.sub(
        r"\b(?:voy|hago|hacer|asisto|practico|tengo|voy\s+a|voy\s+al|voy\s+a\s+la)\b",
        " ",
        cleaned,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,:-")
    article_match = re.match(r"^(?:al|a\s+la|a|el|la)\s+([a-z][a-z\s]+)$", cleaned)
    if article_match:
        return article_match.group(1).strip()
    if "," in cleaned:
        candidate = cleaned.split(",", 1)[0].strip(" ,:-")
        if candidate:
            return candidate
    return cleaned


def _parse_variable(text: str) -> bool | None:
    if any(token in text for token in ("variable", "no fijo", "no fija", "flexible", "rotativo")):
        return True
    if any(token in text for token in ("fijo", "fija", "estable")):
        return False
    return None


def _infer_variability(
    normalized_text: str,
    parsed_schedule: dict[str, object] | None,
) -> bool:
    explicit = _parse_variable(normalized_text)
    if explicit is not None:
        return explicit
    if any(token in normalized_text for token in ("veces por semana", "tentativo", "cuando puedo")):
        return True
    return parsed_schedule is None


def _build_normalized_detail(parsed_schedule: dict[str, object] | None) -> str:
    if not parsed_schedule:
        return ""
    days = list(parsed_schedule.get("days") or [])
    start = str(parsed_schedule.get("start") or "")
    end = str(parsed_schedule.get("end") or "")
    if not days or not start or not end:
        return ""
    if parsed_schedule.get("is_all_days"):
        return f"Todos los dias {start}-{end}"
    return f"{', '.join(days)} {start}-{end}"


def _build_frequency_label(parsed_schedule: dict[str, object] | None) -> str | None:
    if not parsed_schedule:
        return None
    days = list(parsed_schedule.get("days") or [])
    if not days:
        return None
    if parsed_schedule.get("is_all_days"):
        return "todos los dias, desde lunes a domingo"
    return ", ".join(days)


def _split_extracurricular_chunks(text: str) -> list[str]:
    """Divide un mensaje libre en posibles actividades independientes."""
    raw = str(text or "").strip()
    if not raw:
        return []

    coarse_parts = [part.strip(" ,") for part in re.split(r"[;\n]+", raw) if part.strip(" ,")]
    chunks: list[str] = []
    for part in coarse_parts:
        chunks.extend(_split_chunk_on_activity_boundaries(part))
    return chunks


def _split_chunk_on_activity_boundaries(text: str) -> list[str]:
    matches = list(_TIME_RANGE_PATTERN.finditer(text))
    if len(matches) <= 1:
        return [text.strip(" ,")]

    chunks: list[str] = []
    cursor = 0
    for index, match in enumerate(matches[:-1]):
        next_match = matches[index + 1]
        boundary = _find_activity_boundary(text, match.end(), next_match.start())
        if boundary is None:
            continue
        chunk_end, next_cursor = boundary
        chunk = text[cursor:chunk_end].strip(" ,")
        if chunk:
            chunks.append(chunk)
        cursor = next_cursor

    tail = text[cursor:].strip(" ,")
    if tail:
        chunks.append(tail)
    return chunks or [text.strip(" ,")]


def _find_activity_boundary(text: str, start: int, end: int) -> tuple[int, int] | None:
    between = text[start:end]
    separator = _ACTIVITY_SEPARATOR_PATTERN.search(between)
    if not separator:
        return None
    return start + separator.start(), start + separator.end()


def _compact_activity_name(name: str) -> str:
    raw = str(name or "").strip()
    if not raw:
        return ""
    normalized = normalize_text(raw)

    if "gym" in normalized or "gimnasio" in normalized:
        return "Gym"
    if "perro" in normalized and ("saco" in normalized or "pase" in normalized):
        return "Sacar al perro"
    if "salida" in normalized and "amig" in normalized:
        return "Salida con amigas"

    day_match = _DAY_MARKER_PATTERN.search(normalized)
    if day_match:
        normalized = normalized[: day_match.start()].strip(" ,:-")

    words = [word for word in re.findall(r"[a-zA-ZÀ-ÿ]+", normalized) if word]
    filtered = [word for word in words if word.lower() not in _STOPWORDS]
    selected = filtered if filtered else words
    if not selected:
        return raw[:40].strip()

    compact = " ".join(selected[:4]).strip()
    if not compact:
        compact = selected[0]
    return compact.title()
