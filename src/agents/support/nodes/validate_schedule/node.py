"""Nodo para validar el horario con el usuario."""

from __future__ import annotations

import re

from agents.support.nodes.utils import (
    append_message,
    detect_new_input,
    normalize_text,
    parse_yes_no,
)
from agents.support.state import AgentState
from agents.support.tools.llm import llm_extract_json

from .prompt import PROMPT_CONFIRM, PROMPT_MODIFY


def validate_schedule(state: AgentState) -> dict:
    """Solicita confirmacion y registra solicitudes de cambio."""
    messages = state.get("messages", [])
    replan = dict(state.get("replan", {}))
    current_change_request = dict(replan.get("change_request") or {})
    pending_prompt = str(replan.get("pending_prompt") or "").strip()
    has_new_input, last_text, current_count = detect_new_input(
        messages,
        state.get("user_message_count", 0),
        state.get("awaiting_user_input", False),
        state.get("last_user_text"),
    )
    answer = parse_yes_no(last_text) if has_new_input else None
    action = _parse_main_action(last_text or "") if has_new_input else None
    change_request = (
        _build_change_request(state, last_text)
        if has_new_input and action is None
        else None
    )

    if has_new_input and current_change_request.get("stage"):
        handled = _advance_menu_flow(state, replan, last_text or "", current_count)
        if handled is not None:
            return handled

    if has_new_input and pending_prompt and current_change_request:
        replan["pending_prompt"] = None
        return {
            "events_validated": False,
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count,
            "last_user_text": last_text,
            "awaiting_user_input": False,
        }

    if change_request:
        replan["change_request"] = change_request
        replan["pending_prompt"] = None
        return {
            "events_validated": False,
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count,
            "last_user_text": last_text,
            "awaiting_user_input": False,
            "messages": append_message(
                messages, "assistant", "Entendido, aplicare los cambios."
            ),
        }

    if action == "confirm":
        return {
            "events_validated": True,
            "phase": "sync",
            "user_message_count": current_count,
            "last_user_text": last_text,
            "awaiting_user_input": False,
            "messages": append_message(
                messages, "assistant", "Gracias. Guardare este horario."
            ),
        }
    if action in {"update", "add", "delete"}:
        followup_prompt = _menu_followup_prompt(action)
        replan["change_request"] = {
            "operation": action,
            "stage": "awaiting_target" if action in {"update", "add"} else "awaiting_identifier",
        }
        replan["pending_prompt"] = followup_prompt
        return {
            "events_validated": False,
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count,
            "last_user_text": last_text,
            "awaiting_user_input": True,
            "messages": append_message(messages, "assistant", followup_prompt),
        }

    if answer is True:
        return {
            "events_validated": True,
            "phase": "sync",
            "user_message_count": current_count,
            "last_user_text": last_text,
            "awaiting_user_input": False,
            "messages": append_message(
                messages, "assistant", "Gracias. Guardare este horario."
            ),
        }

    if answer is False:
        return {
            "events_validated": False,
            "phase": "validate",
            "user_message_count": current_count,
            "last_user_text": last_text,
            "awaiting_user_input": True,
            "messages": append_message(messages, "assistant", PROMPT_MODIFY),
        }

    return {
        "events_validated": state.get("events_validated", False),
        "phase": "validate",
        "replan": replan,
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_text if has_new_input else state.get("last_user_text"),
        "awaiting_user_input": True,
        "messages": append_message(messages, "assistant", pending_prompt or PROMPT_CONFIRM),
    }


def _build_change_request(state: AgentState, text: str) -> dict | None:
    normalized = normalize_text(text)
    if not normalized:
        return None

    llm_request = _build_change_request_with_llm(text)
    if llm_request:
        if llm_request.get("target") == "extracurricular":
            llm_request["activity_name"] = _resolve_activity_name(
                normalized,
                state,
                preferred=str(llm_request.get("activity_name") or ""),
            )
        llm_request["details"] = str(llm_request.get("details") or text).strip()
        return llm_request

    activity_name = _resolve_activity_name(normalized, state)
    explicit_activity_name = _extract_requested_activity_name(normalized)
    if explicit_activity_name and not activity_name:
        activity_name = explicit_activity_name

    if re.search(r"\b1\b", normalized) or "personal" in normalized or "perfil" in normalized:
        return {"type": "manual_edit", "target": "info_personal", "details": text.strip()}
    if any(token in normalized for token in ("academico", "académico", "clase", "materia")):
        return {
            "type": "manual_edit",
            "target": "academico",
            "operation": _detect_change_operation(normalized),
            "details": text.strip(),
        }
    if any(token in normalized for token in ("laboral", "trabajo", "turno")):
        return {
            "type": "manual_edit",
            "target": "laboral",
            "operation": _detect_change_operation(normalized),
            "details": text.strip(),
        }
    if activity_name or "extracurricular" in normalized or "actividad" in normalized:
        return {
            "type": "manual_edit",
            "target": "extracurricular",
            "operation": _detect_change_operation(normalized),
            "activity_name": activity_name,
            "details": text.strip(),
        }
    if "horario" in normalized:
        return {"type": "manual_edit", "target": "horario", "details": text.strip()}
    return None


def _resolve_activity_name(
    normalized_text: str,
    state: AgentState,
    preferred: str = "",
) -> str:
    extracurricular = state.get("extracurricular", [])
    preferred_normalized = normalize_text(preferred)
    for item in extracurricular:
        item_name = str(item.get("nombre") or "").strip()
        item_normalized = normalize_text(item_name)
        if preferred_normalized and preferred_normalized in item_normalized:
            return item_name
        if item_normalized and item_normalized in normalized_text:
            return item_name
    return ""


def _extract_requested_activity_name(normalized_text: str) -> str:
    match = re.search(
        r"(?:actividad(?:\s+extracurricular)?\s+de|actividad\s+de|cambiar\s+([a-z\s]+?)\s+a|de)\s+([a-z\s]+)",
        normalized_text,
    )
    if not match:
        match = re.search(r"actividad(?:\s+de)?\s+([a-z\s]+)", normalized_text)
    if not match:
        return ""
    candidate = match.group(match.lastindex or 1).strip(" .,:;")
    words = [word for word in candidate.split() if word not in {"la", "el", "los", "las"}]
    return " ".join(words[:4]).strip()


def _build_change_request_with_llm(text: str) -> dict | None:
    prompt = (
        "Extrae un JSON para una solicitud de cambio de horario.\n"
        'Formato: {"target":"academico|laboral|extracurricular|horario|info_personal|null",'
        '"activity_name":"string|null","details":"string"}\n'
        "Reglas:\n"
        "- target=extracurricular si el usuario quiere cambiar una actividad puntual.\n"
        "- activity_name solo si el usuario menciona una actividad concreta.\n"
        "- details debe conservar el texto util para aplicar el cambio.\n"
        "- Si no hay una solicitud clara, responde target=null.\n"
        f"Texto:\n{text}\n"
    )
    data = llm_extract_json(prompt)
    if not data:
        return None
    target = str(data.get("target") or "").strip().lower()
    if target not in {"academico", "laboral", "extracurricular", "horario", "info_personal"}:
        return None
    return {
        "type": "manual_edit",
        "target": target,
        "operation": _detect_change_operation(normalize_text(text)),
        "activity_name": str(data.get("activity_name") or "").strip(),
        "details": str(data.get("details") or text).strip(),
    }


def _detect_change_operation(normalized_text: str) -> str:
    if any(token in normalized_text for token in ("eliminar", "borrar", "quitar")):
        return "delete"
    return "update"


def _parse_main_action(text: str) -> str | None:
    normalized = normalize_text(text)
    if not normalized:
        return None
    if re.fullmatch(r"\s*4[\).:-]?\s*", normalized):
        return "confirm"
    if re.fullmatch(r"\s*1[\).:-]?\s*", normalized):
        return "update"
    if re.fullmatch(r"\s*2[\).:-]?\s*", normalized):
        return "add"
    if re.fullmatch(r"\s*3[\).:-]?\s*", normalized):
        return "delete"
    return None


def _menu_followup_prompt(action: str) -> str:
    if action == "update":
        return (
            "Vas a modificar informacion. Indica si el cambio es en:\n"
            "1) horario academico\n"
            "2) horario laboral\n"
            "3) actividad extracurricular"
        )
    if action == "add":
        return (
            "Vas a anadir informacion. Indica si deseas anadir:\n"
            "1) horario academico\n"
            "2) horario laboral\n"
            "3) actividad extracurricular"
        )
    return (
        "Indica la actividad que deseas eliminar. "
        "Puedes decir solo el nombre, o nombre + dia + hora para ser mas especifico."
    )


def _advance_menu_flow(
    state: AgentState,
    replan: dict,
    text: str,
    current_count: int,
) -> dict | None:
    change_request = dict(replan.get("change_request") or {})
    stage = change_request.get("stage")
    normalized = normalize_text(text)
    base_update = {
        "phase": "validate",
        "replan": replan,
        "user_message_count": current_count,
        "last_user_text": text,
    }

    if stage == "awaiting_target":
        target = _parse_target_option(normalized)
        if not target:
            replan["pending_prompt"] = _menu_followup_prompt(str(change_request.get("operation") or "update"))
            return {
                **base_update,
                "awaiting_user_input": True,
                "messages": append_message(
                    state.get("messages", []),
                    "assistant",
                    str(replan.get("pending_prompt") or ""),
                ),
            }
        change_request["target"] = target
        change_request["stage"] = "awaiting_details"
        replan["change_request"] = change_request
        detail_prompt = _details_prompt_for_action(
            str(change_request.get("operation") or "update"),
            target,
        )
        replan["pending_prompt"] = detail_prompt
        return {
            **base_update,
            "awaiting_user_input": True,
            "messages": append_message(
                state.get("messages", []),
                "assistant",
                detail_prompt,
            ),
        }

    if stage == "awaiting_details":
        change_request["details"] = text.strip()
        change_request["stage"] = None
        replan["change_request"] = change_request
        replan["pending_prompt"] = None
        return {
            **base_update,
            "awaiting_user_input": False,
        }

    if stage == "awaiting_identifier":
        change_request["target"] = "delete"
        change_request["details"] = text.strip()
        change_request["stage"] = None
        replan["change_request"] = change_request
        replan["pending_prompt"] = None
        return {
            **base_update,
            "awaiting_user_input": False,
        }

    return None


def _parse_target_option(normalized: str) -> str | None:
    if not normalized:
        return None
    if normalized in {"1", "1.", "1)", "academico", "académico"} or "academico" in normalized:
        return "academico"
    if normalized in {"2", "2.", "2)", "laboral"} or "laboral" in normalized:
        return "laboral"
    if normalized in {"3", "3.", "3)", "extracurricular"} or "extracurricular" in normalized or "actividad" in normalized:
        return "extracurricular"
    return None


def _details_prompt_for_action(operation: str, target: str) -> str:
    verb = "modificar" if operation == "update" else "anadir"
    if target == "academico":
        return f"Vas a {verb} el horario academico. Indica los dias, horas y materia."
    if target == "laboral":
        return f"Vas a {verb} el horario laboral. Indica los dias y horas."
    return f"Vas a {verb} una actividad extracurricular. Indica nombre, dias y horas."
