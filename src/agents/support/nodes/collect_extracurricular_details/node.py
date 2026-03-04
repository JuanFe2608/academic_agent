"""Nodo para recolectar detalles de actividades extracurriculares."""

from __future__ import annotations

import re

from agents.support.nodes.utils import (
    append_message,
    detect_new_input,
    has_ambiguous_time_range,
    has_time_range,
    normalize_text,
    parse_yes_no,
)
from agents.support.state import AgentState, ExtracurricularItem
from agents.support.tools.llm import llm_normalize_extracurricular_items

from .prompt import (
    PROMPT_FIXED_DETAILS,
    PROMPT_FLEXIBLE_DETAILS,
    PROMPT_MORE,
    PROMPT_TYPE,
)

_DAY_MARKER_PATTERN = re.compile(
    r"\b(lunes|martes|miercoles|miércoles|jueves|viernes|sabado|sábado|domingo|lun|mar|mie|jue|vie|sab|dom)\b"
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
    "para",
    "por",
    "fija",
    "fijo",
    "flexible",
    "variable",
    "tentativo",
    "tentativa",
    "y",
}


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
                "extras_collect_stage": "awaiting_type",
                "extras_pending_is_variable": None,
                "phase": "extras",
                "user_message_count": current_count,
                "last_user_text": last_text,
                "awaiting_user_input": True,
                "messages": append_message(messages, "assistant", PROMPT_TYPE),
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

    if stage == "awaiting_type":
        if not has_new_input or not last_text:
            return {
                "extras_collect_stage": "awaiting_type",
                "extras_pending_is_variable": None,
                "phase": "extras",
                "awaiting_user_input": True,
                "messages": append_message(messages, "assistant", PROMPT_TYPE),
            }
        parsed_type = _parse_activity_type(last_text)
        if parsed_type is None:
            return {
                "extras_collect_stage": "awaiting_type",
                "extras_pending_is_variable": None,
                "phase": "extras",
                "user_message_count": current_count,
                "last_user_text": last_text,
                "awaiting_user_input": True,
                "messages": append_message(
                    messages,
                    "assistant",
                    f"{PROMPT_TYPE}\nResponde con fija o flexible.",
                ),
            }
        return {
            "extras_collect_stage": "awaiting_details",
            "extras_pending_is_variable": parsed_type,
            "phase": "extras",
            "user_message_count": current_count,
            "last_user_text": last_text,
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                _details_prompt(parsed_type),
            ),
        }

    if pending_is_variable is None:
        return {
            "extras_collect_stage": "awaiting_type",
            "extras_pending_is_variable": None,
            "phase": "extras",
            "awaiting_user_input": True,
            "messages": append_message(messages, "assistant", PROMPT_TYPE),
        }

    if not has_new_input or not last_text:
        return {
            "extras_collect_stage": "awaiting_details",
            "extras_pending_is_variable": pending_is_variable,
            "phase": "extras",
            "awaiting_user_input": True,
            "messages": append_message(messages, "assistant", _details_prompt(pending_is_variable)),
        }

    items, missing = parse_extracurricular_items(last_text, expected_is_variable=pending_is_variable)
    if missing:
        prompt = _details_prompt(pending_is_variable) + "\nFaltan: " + ", ".join(missing) + "."
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
        nombre = _infer_nombre(normalized)
    if not nombre:
        missing.append("nombre")
    nombre = _compact_activity_name(nombre)

    es_variable = expected_is_variable
    if es_variable is None:
        es_variable = _parse_variable(normalized)
    if es_variable is None:
        missing.append("tipo (fija o variable)")

    detalle = text.strip() if text.strip() else ""
    if not detalle:
        missing.append("detalle")
    elif not _has_schedule_info(detalle):
        missing.append("horario con dias y horas")
    elif has_ambiguous_time_range(detalle):
        missing.append("aclarar AM o PM en el horario")

    item = ExtracurricularItem(
        nombre=nombre.strip().title() if nombre else "",
        es_variable=bool(es_variable),
        detalle=detalle,
        tentativo=[],
    )
    return item, missing


def parse_extracurricular_items(
    text: str,
    expected_is_variable: bool | None = None,
) -> tuple[list[ExtracurricularItem], list[str]]:
    """Permite parsear varias actividades en un solo texto."""
    llm_items = _parse_extracurricular_items_with_llm(text, expected_is_variable)
    if llm_items:
        return llm_items, []

    chunks = [chunk.strip() for chunk in re.split(r"[;\n]+", text) if chunk.strip()]
    items: list[ExtracurricularItem] = []
    missing: list[str] = []

    for index, chunk in enumerate(chunks, start=1):
        item, item_missing = parse_extracurricular_text(chunk, expected_is_variable)
        if item_missing:
            for field in item_missing:
                missing.append(f"actividad {index}: {field}")
            continue
        items.append(item)

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
        if not nombre or not detalle or not isinstance(es_variable, bool):
            continue
        if not _has_schedule_info(detalle):
            continue
        if has_ambiguous_time_range(detalle):
            continue
        items.append(
            ExtracurricularItem(
                nombre=_compact_activity_name(nombre),
                es_variable=es_variable,
                detalle=detalle,
                tentativo=[],
            )
        )
    return items


def _extract_value(text: str, pattern: str) -> str:
    match = re.search(pattern, text)
    return match.group(1) if match else ""


def _infer_nombre(text: str) -> str:
    day_match = _DAY_MARKER_PATTERN.search(text)
    if day_match and day_match.start() > 0:
        candidate = text[: day_match.start()].strip(" ,:-")
        if candidate:
            return candidate
    for marker in ("fijo", "fija", "variable"):
        index = text.find(marker)
        if index > 0:
            candidate = text[:index].strip(" ,:-")
            if candidate:
                return candidate
    if "," in text:
        candidate = text.split(",", 1)[0].strip(" ,:-")
        if candidate:
            return candidate
    words = text.split()
    if words:
        return " ".join(words[:3])
    return ""


def _parse_variable(text: str) -> bool | None:
    if "variable" in text or "no fijo" in text or "no fija" in text:
        return True
    if "fijo" in text or "fija" in text or "estable" in text:
        return False
    return None


def _parse_activity_type(text: str) -> bool | None:
    normalized = normalize_text(text)
    if normalized in ("1", "1.", "1)", "fija", "fijo", "estable"):
        return False
    if normalized in ("2", "2.", "2)", "flexible", "variable", "rotativo"):
        return True
    if normalized.startswith("1"):
        return False
    if normalized.startswith("2"):
        return True
    if "fija" in normalized or "fijo" in normalized or "estable" in normalized:
        return False
    if "flexible" in normalized or "variable" in normalized or "rotativo" in normalized:
        return True
    return None


def _details_prompt(is_variable: bool) -> str:
    return PROMPT_FLEXIBLE_DETAILS if is_variable else PROMPT_FIXED_DETAILS


def _has_schedule_info(text: str) -> bool:
    normalized = normalize_text(text)
    return bool(_DAY_MARKER_PATTERN.search(normalized) and has_time_range(normalized))


def _compact_activity_name(name: str) -> str:
    raw = str(name or "").strip()
    if not raw:
        return ""
    normalized = normalize_text(raw)

    if "gym" in normalized or "gimnasio" in normalized:
        return "Gym"
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
