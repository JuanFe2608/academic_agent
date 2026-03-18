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
from agents.support.tools.activity_matching import resolve_best_title_key
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
        followup_prompt = _menu_followup_prompt(action, state)
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
        replan["return_to_menu"] = True
        return {
            "events_validated": False,
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count,
            "last_user_text": last_text,
            "awaiting_user_input": False,
        }

    if has_new_input:
        replan["return_to_menu"] = True
        return {
            "events_validated": False,
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count,
            "last_user_text": last_text,
            "awaiting_user_input": False,
        }

    if pending_prompt:
        return {
            "events_validated": state.get("events_validated", False),
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_text if has_new_input else state.get("last_user_text"),
            "awaiting_user_input": True,
            "messages": append_message(messages, "assistant", pending_prompt),
        }

    schedule_preview = state.get("schedule_preview", {})
    if schedule_preview.get("text") or schedule_preview.get("image_path"):
        return {
            "events_validated": state.get("events_validated", False),
            "phase": "validate",
            "replan": replan,
            "user_message_count": state.get("user_message_count", 0),
            "last_user_text": state.get("last_user_text"),
            "awaiting_user_input": True,
        }

    return {
        "events_validated": state.get("events_validated", False),
        "phase": "validate",
        "replan": replan,
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_text if has_new_input else state.get("last_user_text"),
        "awaiting_user_input": True,
        "messages": append_message(messages, "assistant", PROMPT_CONFIRM),
    }


def _build_change_request(state: AgentState, text: str) -> dict | None:
    normalized = normalize_text(text)
    if not normalized:
        return None

    operation = _detect_change_operation(normalized)
    scheduled_target, scheduled_activity_name = _resolve_scheduled_activity(normalized, state)
    if operation == "delete":
        activity_name = scheduled_activity_name or _resolve_activity_name(normalized, state)
        explicit_activity_name = _extract_requested_activity_name(normalized)
        if explicit_activity_name and not activity_name:
            activity_name = explicit_activity_name
        return {
            "type": "manual_edit",
            "target": "delete",
            "operation": "delete",
            "activity_name": activity_name,
            "details": text.strip(),
        }

    if operation == "add" and _looks_like_activity_addition(normalized, text):
        return {
            "type": "manual_edit",
            "target": "activity",
            "operation": "add",
            "details": text.strip(),
        }

    if scheduled_target and scheduled_activity_name:
        return {
            "type": "manual_edit",
            "target": scheduled_target,
            "operation": operation,
            "activity_name": scheduled_activity_name,
            "details": text.strip(),
            "apply_to_all": _requests_all_occurrences(normalized),
        }

    llm_request = _build_change_request_with_llm(text)
    if llm_request:
        if llm_request.get("operation") == "delete":
            llm_request["target"] = "delete"
        resolved_target, resolved_activity_name = _resolve_scheduled_activity(
            normalized,
            state,
            preferred=str(llm_request.get("activity_name") or ""),
        )
        if resolved_target and resolved_activity_name:
            llm_request["target"] = resolved_target
            llm_request["activity_name"] = resolved_activity_name
        elif llm_request.get("target") == "extracurricular":
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
    if _looks_like_activity_reference(normalized):
        return {
            "type": "manual_edit",
            "target": "activity_lookup",
            "operation": operation,
            "activity_name": text.strip(),
            "details": text.strip(),
            "apply_to_all": _requests_all_occurrences(normalized),
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


def _resolve_scheduled_activity(
    normalized_text: str,
    state: AgentState,
    preferred: str = "",
) -> tuple[str, str]:
    events = list(state.get("events", []))
    if not events:
        return "", ""

    preferred_normalized = normalize_text(preferred)
    candidate_text = preferred_normalized or normalized_text
    hinted_target = _target_hint_from_text(normalized_text)
    filtered_events = [
        event for event in events if not hinted_target or str(event.get("categoria") or "") == hinted_target
    ] or events
    title_key = _extract_best_title_key(filtered_events, candidate_text)
    if not title_key:
        return "", ""

    matches = [
        event
        for event in filtered_events
        if normalize_text(str(event.get("titulo") or "").strip()) == title_key
    ]
    if not matches:
        return "", ""

    categories = {str(event.get("categoria") or "") for event in matches if event.get("categoria")}
    if len(categories) != 1:
        if hinted_target and hinted_target in categories:
            return hinted_target, str(matches[0].get("titulo") or "").strip()
        return "", ""
    return categories.pop(), str(matches[0].get("titulo") or "").strip()


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


def _extract_best_title_key(events: list[dict], normalized_details: str) -> str:
    return resolve_best_title_key(events, normalized_details)


def _target_hint_from_text(normalized_text: str) -> str:
    if any(token in normalized_text for token in ("academico", "académico", "clase", "materia")):
        return "academico"
    if any(token in normalized_text for token in ("laboral", "trabajo", "turno")):
        return "laboral"
    if "extracurricular" in normalized_text or "actividad" in normalized_text:
        return "extracurricular"
    return ""


def _looks_like_activity_reference(normalized_text: str) -> bool:
    return bool(re.search(r"[a-z]", normalized_text)) and normalized_text not in {"si", "no"}


def _requests_all_occurrences(normalized_text: str) -> bool:
    return any(
        token in normalized_text
        for token in ("todas las actividades", "todos los horarios", "todas", "todos")
    )


def _detect_change_operation(normalized_text: str) -> str:
    if any(token in normalized_text for token in ("eliminar", "borrar", "quitar")):
        return "delete"
    if any(
        token in normalized_text
        for token in (
            "anadir",
            "agregar",
            "sumar",
            "incluir",
            "programar",
            "aniadir",
        )
    ):
        return "add"
    if _looks_like_activity_addition(normalized_text, normalized_text):
        return "add"
    return "update"


def _looks_like_activity_addition(normalized_text: str, raw_text: str) -> bool:
    if any(token in normalized_text for token in ("cambiar", "modificar", "ajustar", "editar")):
        return False
    if not re.search(r"\d{1,2}(?::\d{2})?\s*(?:[ap]m?)?\s*(?:-|a|hasta)\s*\d{1,2}", raw_text):
        return False
    return any(
        token in normalized_text
        for token in (
            "lunes",
            "martes",
            "miercoles",
            "jueves",
            "viernes",
            "sabado",
            "domingo",
            "lun ",
            "mar ",
            "mie ",
            "jue ",
            "vie ",
            "sab ",
            "dom ",
            "todos los dias",
            "cada dia",
            "diario",
            "hago ",
            "estudio ",
            "trabajo ",
            "practico ",
            "voy ",
            "tengo ",
        )
    )


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


def _menu_followup_prompt(action: str, state: AgentState) -> str:
    target_options = _available_target_options(state)
    if action == "update":
        return "Vas a modificar informacion. Indica si el cambio es en:\n" + _format_target_options(
            target_options
        )
    if action == "add":
        return "Vas a anadir informacion. Indica si deseas anadir:\n" + _format_target_options(
            target_options
        )
    return "Cual es la actividad que deseas eliminar?"


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
        target = _parse_target_option(normalized, state)
        if not target:
            replan["pending_prompt"] = _menu_followup_prompt(
                str(change_request.get("operation") or "update"),
                state,
            )
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
        change_request["activity_name"] = _extract_requested_activity_name(normalized) or text.strip()
        change_request["details"] = text.strip()
        change_request["stage"] = None
        replan["change_request"] = change_request
        replan["pending_prompt"] = None
        return {
            **base_update,
            "awaiting_user_input": False,
        }

    return None


def _parse_target_option(normalized: str, state: AgentState) -> str | None:
    if not normalized:
        return None
    options = _available_target_options(state)
    for index, target in enumerate(options, start=1):
        if normalized in {str(index), f"{index}.", f"{index})"}:
            return target
    if "academico" in normalized or "académico" in normalized:
        return "academico" if "academico" in options else None
    if "laboral" in normalized:
        return "laboral" if "laboral" in options else None
    if "extracurricular" in normalized or "actividad" in normalized:
        return "extracurricular" if "extracurricular" in options else None
    return None


def _available_target_options(state: AgentState) -> list[str]:
    occupation = str(state.get("student_profile", {}).get("occupation") or "").strip()
    if occupation == "solo_estudio":
        return ["academico", "extracurricular"]
    if occupation == "solo_trabajo":
        return ["laboral", "extracurricular"]
    if occupation == "ninguna":
        return ["extracurricular"]
    return ["academico", "laboral", "extracurricular"]


def _format_target_options(options: list[str]) -> str:
    labels = {
        "academico": "horario academico",
        "laboral": "horario laboral",
        "extracurricular": "actividad extracurricular",
    }
    return "\n".join(f"{index}) {labels[target]}" for index, target in enumerate(options, start=1))


def _details_prompt_for_action(operation: str, target: str) -> str:
    if operation == "update":
        if target == "academico":
            return "Que actividad academica deseas modificar?"
        if target == "laboral":
            return "Que actividad laboral deseas modificar?"
        return "Que actividad extracurricular deseas modificar?"

    verb = "modificar" if operation == "update" else "anadir"
    if target == "academico":
        return f"Vas a {verb} el horario academico. Indica los dias, horas y materia."
    if target == "laboral":
        return f"Vas a {verb} el horario laboral. Indica los dias y horas."
    return f"Vas a {verb} una actividad extracurricular. Indica nombre, dias y horas."
