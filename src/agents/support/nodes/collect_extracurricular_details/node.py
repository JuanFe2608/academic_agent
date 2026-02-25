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

from .prompt import PROMPT, PROMPT_MORE


def collect_extracurricular_details(state: AgentState) -> dict:
    """Recolecta actividades extracurriculares y avanza al draft."""
    messages = state.get("messages", [])
    has_new_input, last_text, current_count = detect_new_input(
        messages,
        state.get("user_message_count", 0),
        state.get("awaiting_user_input", False),
        state.get("last_user_text"),
    )
    stage = state.get("extras_collect_stage")

    if stage == "awaiting_more":
        answer = parse_yes_no(last_text) if has_new_input else None
        if answer is True:
            return {
                "extras_collect_stage": "awaiting_details",
                "phase": "extras",
                "user_message_count": current_count,
                "last_user_text": last_text,
                "awaiting_user_input": True,
                "messages": append_message(messages, "assistant", PROMPT),
            }
        if answer is False:
            return {
                "extras_collect_stage": "done",
                "phase": "draft",
                "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
                "last_user_text": last_text if has_new_input else state.get("last_user_text"),
                "awaiting_user_input": False,
                "messages": append_message(
                    messages, "assistant", "Listo, continuemos con el horario."
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

    if not last_text or not has_new_input:
        return {
            "extras_collect_stage": "awaiting_details",
            "phase": "extras",
            "awaiting_user_input": True,
            "messages": append_message(messages, "assistant", PROMPT),
        }

    items, missing = parse_extracurricular_items(last_text)
    if missing:
        prompt = PROMPT + "\nFaltan: " + ", ".join(missing) + "."
        return {
            "extras_collect_stage": "awaiting_details",
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
        "phase": "extras",
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_text if has_new_input else state.get("last_user_text"),
        "awaiting_user_input": True,
        "messages": append_message(messages, "assistant", PROMPT_MORE),
    }


def parse_extracurricular_text(text: str) -> tuple[ExtracurricularItem, list[str]]:
    """Parsea texto de actividad extracurricular."""
    missing: list[str] = []
    normalized = normalize_text(text)

    nombre = _extract_value(normalized, r"nombre\s*[:\-]?\s*([a-z\s]+)")
    if not nombre:
        nombre = _infer_nombre(normalized)
    if not nombre:
        missing.append("nombre")

    es_variable = _parse_variable(normalized)
    if es_variable is None:
        missing.append("tipo (fija o variable)")

    detalle = text.strip() if text.strip() else ""
    if not detalle:
        missing.append("detalle")

    item = ExtracurricularItem(
        nombre=nombre.strip().title() if nombre else "",
        es_variable=bool(es_variable),
        detalle=detalle,
        tentativo=[],
    )
    return item, missing


def parse_extracurricular_items(text: str) -> tuple[list[ExtracurricularItem], list[str]]:
    """Permite parsear varias actividades en un solo texto."""
    chunks = [chunk.strip() for chunk in re.split(r"[;\n]+", text) if chunk.strip()]
    items: list[ExtracurricularItem] = []
    missing: list[str] = []

    for index, chunk in enumerate(chunks, start=1):
        item, item_missing = parse_extracurricular_text(chunk)
        if item_missing:
            for field in item_missing:
                missing.append(f"actividad {index}: {field}")
            continue
        items.append(item)

    if not chunks:
        missing.append("detalle")

    return items, missing


def _extract_value(text: str, pattern: str) -> str:
    match = re.search(pattern, text)
    return match.group(1) if match else ""


def _infer_nombre(text: str) -> str:
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
