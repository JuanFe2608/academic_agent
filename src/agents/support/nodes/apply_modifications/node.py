"""Nodo para aplicar modificaciones solicitadas por el usuario."""

from __future__ import annotations

import re

from agents.support.nodes.collect_extracurricular_details import (
    parse_extracurricular_items,
    parse_extracurricular_text,
)
from agents.support.nodes.generate_tentative_extracurricular.node import (
    build_fixed_events,
    build_tentative_events,
)
from agents.support.nodes.utils import (
    append_message,
    detect_new_input,
    has_time_range,
    normalize_text,
    parse_yes_no,
)
from agents.support.state import AgentState, Event, ExtracurricularItem, new_event_id, normalize_time, validate_event
from agents.support.tools.activity_matching import resolve_best_title_key, suggest_similar_titles
from agents.support.tools.schedule_parser import (
    extract_natural_schedule_components,
    parse_academic_schedule_text,
    parse_work_schedule_text,
)

from .prompt import PROMPT_EXTRAS, PROMPT_HORARIO, PROMPT_HORARIO_ACADEMICO

_DAY_MARKER_PATTERN = re.compile(
    r"\b(lunes|martes|miercoles|miércoles|jueves|viernes|sabados|sabado|sábado|domingos|domingo|"
    r"lun|mar|mie|jue|vie|sab|dom|todos\s+los\s+dias|todos\s+los\s+días|"
    r"cada\s+dia|cada\s+día|diario|diariamente)\b"
)
_TIME_RANGE_PATTERN = re.compile(
    r"(?:de|desde)?\s*(?:las\s+)?\d{1,2}(?::\d{2})?(?:\s*[ap]\.?\s*m\.?)?"
    r"\s*(?:-|a|hasta)\s*(?:las\s+)?\d{1,2}(?::\d{2})?(?:\s*[ap]\.?\s*m\.?)?",
    re.IGNORECASE,
)
_ACTIVITY_SEPARATOR_PATTERN = re.compile(
    r"(?:\s*,\s*|\s+(?:y|e|ademas|además|tambien|también)\s+)",
    re.IGNORECASE,
)
_ACADEMIC_KEYWORDS = (
    "academica",
    "academico",
    "clase",
    "clases",
    "estudio",
    "estudiar",
    "materia",
    "parcial",
    "parciales",
    "examen",
    "tarea",
    "curso",
)
_WORK_KEYWORDS = (
    "trabajo",
    "trabajar",
    "laboral",
    "turno",
    "empleo",
    "oficina",
)


def apply_modifications(state: AgentState) -> dict:
    """Aplica cambios a horarios laborales o extracurriculares."""
    messages = state.get("messages", [])
    has_new_input, last_text, current_count = detect_new_input(
        messages,
        state.get("user_message_count", 0),
        state.get("awaiting_user_input", False),
        state.get("last_user_text"),
    )
    last_user_text_value = last_text if has_new_input else state.get("last_user_text")
    replan = dict(state.get("replan", {}))
    change_request = replan.get("change_request") or {}

    target = change_request.get("target")
    operation = str(change_request.get("operation") or "update").strip().lower()
    activity_name = str(change_request.get("activity_name") or "").strip()
    stage = str(change_request.get("stage") or "").strip()
    if has_new_input and stage:
        details = str(last_text or "").strip()
    else:
        details = (change_request.get("details") or "").strip() or (last_text if has_new_input else "")

    if target == "delete":
        return _apply_delete_change(
            state, details, replan, current_count, has_new_input, last_user_text_value
        )
    if target == "activity":
        return _apply_activity_additions(
            state, details, replan, current_count, has_new_input, last_user_text_value
        )
    if operation == "update" and target in {"academico", "laboral", "extracurricular", "activity_lookup"}:
        return _handle_activity_update(
            state,
            target,
            activity_name,
            details,
            replan,
            current_count,
            has_new_input,
            last_user_text_value,
        )
    if target == "horario":
        replan["pending_prompt"] = "Aclara si deseas cambiar el horario academico o el laboral. Usa la tabla anterior como referencia."
        return {
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }
    if target == "laboral":
        return _apply_laboral_change(
            state, details, operation, replan, current_count, has_new_input, last_user_text_value
        )
    if target == "academico":
        return _apply_academic_change(
            state, details, operation, replan, current_count, has_new_input, last_user_text_value
        )
    if target == "extracurricular":
        return _apply_extracurricular_change(
            state,
            details,
            operation,
            activity_name,
            replan,
            current_count,
            has_new_input,
            last_user_text_value,
        )

    return {
        "messages": append_message(
            messages,
            "assistant",
            "Por ahora solo puedo modificar horario o actividades extracurriculares.",
        ),
        "phase": "validate",
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_user_text_value,
        "awaiting_user_input": True,
    }


def _handle_activity_update(
    state: AgentState,
    target: str,
    activity_name: str,
    details: str,
    replan: dict,
    current_count: int,
    has_new_input: bool,
    last_user_text_value: str | None,
) -> dict:
    change_request = dict(replan.get("change_request") or {})
    stage = str(change_request.get("stage") or "")
    details = str(details or "").strip()
    candidate_ids = list(change_request.get("candidate_event_ids") or [])
    selected_event_id = str(change_request.get("selected_event_id") or "")
    selected_event = _event_from_id(state.get("events", []), selected_event_id)
    selected_event_ids = list(change_request.get("selected_event_ids") or [])
    selected_events = _events_from_ids(state.get("events", []), selected_event_ids)
    apply_to_all = bool(change_request.get("apply_to_all"))

    if stage == "awaiting_update_identifier":
        options = _events_from_ids(_candidate_events_for_target(state, target), candidate_ids)
        selected = _select_update_candidate(options, details)
        if not selected:
            replan["pending_prompt"] = _build_multiple_update_prompt(options)
            return {
                "phase": "validate",
                "replan": replan,
                "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
                "last_user_text": last_user_text_value,
                "awaiting_user_input": True,
            }
        change_request["selected_event_id"] = str(selected.get("id"))
        change_request["candidate_event_ids"] = None
        change_request["stage"] = "awaiting_update_candidate_confirmation"
        replan["change_request"] = change_request
        replan["pending_prompt"] = _build_update_candidate_confirmation_prompt(selected)
        return {
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }

    if stage == "awaiting_update_candidate_confirmation":
        answer = parse_yes_no(details)
        if answer is None:
            replan["pending_prompt"] = str(
                replan.get("pending_prompt") or "Responde si o no para confirmar la actividad a modificar."
            )
            return {
                "phase": "validate",
                "replan": replan,
                "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
                "last_user_text": last_user_text_value,
                "awaiting_user_input": True,
            }
        if answer is False:
            change_request["stage"] = "awaiting_update_reference"
            change_request["selected_event_id"] = None
            change_request["candidate_event_ids"] = None
            change_request["update_payload"] = None
            change_request["update_summary"] = None
            replan["change_request"] = change_request
            replan["pending_prompt"] = _build_available_update_reference_prompt(
                target,
                _candidate_events_for_target(state, target),
            )
            return {
                "phase": "validate",
                "replan": replan,
                "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
                "last_user_text": last_user_text_value,
                "awaiting_user_input": True,
            }
        if not selected_event:
            replan["pending_prompt"] = _build_available_update_reference_prompt(
                target,
                _candidate_events_for_target(state, target),
            )
            change_request["stage"] = "awaiting_update_reference"
            replan["change_request"] = change_request
            return {
                "phase": "validate",
                "replan": replan,
                "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
                "last_user_text": last_user_text_value,
                "awaiting_user_input": True,
            }
        if str(change_request.get("update_payload") or "").strip():
            return _queue_update_apply_confirmation(
                state,
                target,
                selected_event,
                str(change_request.get("update_payload") or "").strip(),
                change_request,
                replan,
                current_count,
                has_new_input,
                last_user_text_value,
            )
        change_request["stage"] = "awaiting_update_new_details"
        replan["change_request"] = change_request
        replan["pending_prompt"] = _build_update_details_prompt(target, selected_event)
        return {
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }

    if stage == "awaiting_update_new_details":
        if not details:
            replan["pending_prompt"] = _build_update_details_prompt(
                _effective_update_target(target, selected_event),
                selected_event,
            )
            return {
                "phase": "validate",
                "replan": replan,
                "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
                "last_user_text": last_user_text_value,
                "awaiting_user_input": True,
            }
        return _queue_update_apply_confirmation(
            state,
            target,
            selected_event,
            details,
            change_request,
            replan,
            current_count,
            has_new_input,
            last_user_text_value,
        )

    if stage == "awaiting_update_all_details":
        if not details:
            replan["pending_prompt"] = _build_update_all_details_prompt(selected_events)
            return {
                "phase": "validate",
                "replan": replan,
                "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
                "last_user_text": last_user_text_value,
                "awaiting_user_input": True,
            }
        return _queue_update_all_apply_confirmation(
            state,
            target,
            selected_events,
            details,
            change_request,
            replan,
            current_count,
            has_new_input,
            last_user_text_value,
        )

    if stage == "awaiting_update_apply_confirmation":
        answer = parse_yes_no(details)
        if answer is None:
            replan["pending_prompt"] = str(
                replan.get("pending_prompt") or "Responde si o no para confirmar la modificacion."
            )
            return {
                "phase": "validate",
                "replan": replan,
                "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
                "last_user_text": last_user_text_value,
                "awaiting_user_input": True,
            }
        if answer is False:
            replan["change_request"] = None
            replan["pending_prompt"] = None
            return {
                "phase": "validate",
                "replan": replan,
                "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
                "last_user_text": last_user_text_value,
                "awaiting_user_input": False,
            }
        if selected_events:
            return _apply_confirmed_activity_update_all(
                state,
                target,
                selected_events,
                str(change_request.get("update_payload") or "").strip(),
                replan,
                current_count,
                has_new_input,
                last_user_text_value,
            )
        return _apply_confirmed_activity_update(
            state,
            target,
            selected_event,
            str(change_request.get("update_payload") or "").strip(),
            replan,
            current_count,
            has_new_input,
            last_user_text_value,
        )

    if not details:
        replan["pending_prompt"] = _build_initial_update_reference_prompt(target)
        return {
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }

    candidate_events = _candidate_events_for_target(state, target)
    reference_text, update_payload = _extract_update_reference_and_payload(details, activity_name)
    matches = _find_delete_matches(candidate_events, reference_text)
    if not matches and len(candidate_events) == 1 and not activity_name:
        matches = candidate_events
    if not matches:
        replan["pending_prompt"] = _build_not_found_update_prompt(
            target,
            candidate_events,
            activity_name or reference_text or details,
        )
        return {
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }

    if len(matches) > 1:
        if apply_to_all:
            change_request["selected_event_ids"] = [str(event.get("id")) for event in matches]
            change_request["candidate_event_ids"] = None
            if update_payload:
                return _queue_update_all_apply_confirmation(
                    state,
                    target,
                    matches,
                    update_payload,
                    change_request,
                    replan,
                    current_count,
                    has_new_input,
                    last_user_text_value,
                )
            change_request["stage"] = "awaiting_update_all_details"
            replan["change_request"] = change_request
            replan["pending_prompt"] = _build_update_all_details_prompt(matches)
            return {
                "phase": "validate",
                "replan": replan,
                "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
                "last_user_text": last_user_text_value,
                "awaiting_user_input": True,
            }
        selected = _select_update_candidate(matches, reference_text)
        if not selected:
            change_request["stage"] = "awaiting_update_identifier"
            change_request["candidate_event_ids"] = [str(event.get("id")) for event in matches]
            change_request["update_payload"] = update_payload or None
            replan["change_request"] = change_request
            replan["pending_prompt"] = _build_multiple_update_prompt(matches)
            return {
                "phase": "validate",
                "replan": replan,
                "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
                "last_user_text": last_user_text_value,
                "awaiting_user_input": True,
            }
        matches = [selected]

    selected_event = matches[0]
    if not update_payload and _reference_is_name_only(reference_text, selected_event):
        change_request["selected_event_id"] = str(selected_event.get("id"))
        change_request["candidate_event_ids"] = None
        change_request["update_payload"] = None
        change_request["stage"] = "awaiting_update_new_details"
        replan["change_request"] = change_request
        replan["pending_prompt"] = _build_update_name_only_prompt(selected_event)
        return {
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }
    change_request["selected_event_id"] = str(selected_event.get("id"))
    change_request["candidate_event_ids"] = None
    change_request["update_payload"] = update_payload or None
    change_request["stage"] = "awaiting_update_candidate_confirmation"
    replan["change_request"] = change_request
    replan["pending_prompt"] = _build_update_candidate_confirmation_prompt(selected_event)
    return {
        "phase": "validate",
        "replan": replan,
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_user_text_value,
        "awaiting_user_input": True,
    }


def _candidate_events_for_target(state: AgentState, target: str) -> list[Event]:
    if target == "activity_lookup":
        return list(state.get("events", []))
    events = [event for event in state.get("events", []) if event.get("categoria") == target]
    if events or target != "extracurricular":
        return events
    generated: list[Event] = []
    for item in [_ensure_item(item) for item in state.get("extracurricular", [])]:
        generated.extend(_build_events_from_extracurricular_item(item, state.get("timezone", "America/Bogota")))
    return generated


def _extract_update_reference_and_payload(details: str, activity_name: str) -> tuple[str, str]:
    text = str(details or "").strip()
    if not text:
        return "", ""
    if activity_name:
        pattern = re.compile(
            rf"(?:cambiar|modificar|ajustar).{{0,80}}{re.escape(activity_name)}\s+a\s+(.+)",
            re.IGNORECASE,
        )
        match = pattern.search(text)
        return (activity_name, match.group(1).strip()) if match else (text, "")

    match = re.search(
        r"(?:quiero\s+|necesito\s+|por\s+favor\s+)?(?:cambiar|modificar|ajustar)\s+"
        r"(?:la\s+actividad\s+)?(?:de\s+)?(.+?)(?:\s+a\s+(.+))?$",
        text,
        re.IGNORECASE,
    )
    if not match:
        return text, ""
    reference = str(match.group(1) or "").strip(" ,.:;")
    payload = str(match.group(2) or "").strip()
    return reference or text, payload


def _build_update_candidate_confirmation_prompt(event: Event | dict | None) -> str:
    if not event:
        return "No pude identificar la actividad. Indica nuevamente cual deseas modificar."
    return (
        "Esta es la actividad que quieres cambiar?\n\n"
        f"Actividad: {event.get('titulo')}\n"
        f"Dia(s): {event.get('dia')}\n"
        f"Horario: {event.get('inicio')}-{event.get('fin')}\n"
        f"Tipo: {_format_event_type(str(event.get('categoria') or ''))}"
    )


def _build_multiple_update_prompt(matches: list[Event]) -> str:
    if not matches:
        return "No encontre coincidencias. Indica nombre, dia u horario de la actividad."
    activity_name = str(matches[0].get("titulo") or "la actividad")
    lines = [
        f"Encontre varias actividades con el nombre {activity_name}.",
        "Indica cual deseas modificar especificando el dia o el horario.",
    ]
    for index, event in enumerate(matches, start=1):
        lines.append(
            f"{index}. {event.get('titulo')} - {event.get('dia')} {event.get('inicio')}-{event.get('fin')}"
        )
    return "\n".join(lines)


def _build_update_details_prompt(target: str, event: Event | dict | None) -> str:
    if target == "academico":
        return (
            "Indica el nuevo dia y horario de la actividad academica. "
            "Si cambia, incluye tambien la materia."
        )
    if target == "laboral":
        return "Indica el nuevo dia y horario de la actividad laboral."
    activity_name = str(event.get("titulo") or "la actividad") if event else "la actividad"
    return (
        f"Indica el nuevo dia y horario de {activity_name}. "
        "Si cambia el nombre, tambien puedes incluirlo."
    )


def _build_final_update_confirmation_prompt(event: Event | dict | None, update_summary: str) -> str:
    if not event:
        return "No pude identificar la actividad a modificar. Indica nuevamente cual deseas cambiar."
    return (
        "Estas seguro de que deseas modificar esta actividad?\n\n"
        f"Actividad actual: {event.get('titulo')}\n"
        f"Dia(s) actuales: {event.get('dia')}\n"
        f"Horario actual: {event.get('inicio')}-{event.get('fin')}\n"
        f"Tipo: {_format_event_type(str(event.get('categoria') or ''))}\n\n"
        "Quedara asi:\n"
        f"{update_summary}"
    )


def _build_final_update_all_confirmation_prompt(
    events: list[Event],
    update_summary: str,
) -> str:
    activity_name = str(events[0].get("titulo") or "la actividad") if events else "la actividad"
    return (
        f"Se modificaran todas las actividades llamadas '{activity_name}'.\n\n"
        "Coincidencias actuales:\n"
        f"{_build_match_table(events)}\n\n"
        "Quedaran asi:\n"
        f"{update_summary}\n\n"
        "Deseas continuar?"
    )


def _format_event_type(category: str) -> str:
    return {
        "academico": "academica",
        "laboral": "laboral",
        "extracurricular": "extracurricular",
    }.get(category, category or "desconocido")


def _select_update_candidate(matches: list[Event], details: str) -> Event | None:
    if not matches:
        return None
    selected_index = _parse_numeric_selection(details, len(matches))
    if selected_index is not None:
        return matches[selected_index]
    filtered = _filter_events_by_hint(matches, details)
    if len(filtered) == 1:
        return filtered[0]
    if len(filtered) > 1:
        return None
    exact_matches = _find_delete_matches(matches, details)
    if len(exact_matches) == 1:
        return exact_matches[0]
    return None


def _parse_numeric_selection(details: str, total: int) -> int | None:
    normalized = normalize_text(details)
    match = re.fullmatch(r"(\d+)[\).:-]?", normalized)
    if not match:
        return None
    index = int(match.group(1)) - 1
    if 0 <= index < total:
        return index
    return None


def _apply_confirmed_activity_update(
    state: AgentState,
    target: str,
    selected_event: Event | dict | None,
    update_payload: str,
    replan: dict,
    current_count: int,
    has_new_input: bool,
    last_user_text_value: str | None,
) -> dict:
    if not selected_event:
        replan["pending_prompt"] = "No encontre la actividad seleccionada. Indica nuevamente cual deseas modificar."
        return {
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }
    effective_target = _effective_update_target(target, selected_event)
    if effective_target == "academico":
        return _apply_selected_academic_update(
            state,
            selected_event,
            update_payload,
            replan,
            current_count,
            has_new_input,
            last_user_text_value,
        )
    if effective_target == "laboral":
        return _apply_selected_laboral_update(
            state,
            selected_event,
            update_payload,
            replan,
            current_count,
            has_new_input,
            last_user_text_value,
        )
    return _apply_selected_extracurricular_update(
        state,
        selected_event,
        update_payload,
        replan,
        current_count,
        has_new_input,
        last_user_text_value,
    )


def _apply_confirmed_activity_update_all(
    state: AgentState,
    target: str,
    selected_events: list[Event],
    update_payload: str,
    replan: dict,
    current_count: int,
    has_new_input: bool,
    last_user_text_value: str | None,
) -> dict:
    if not selected_events:
        replan["pending_prompt"] = "No encontre las actividades seleccionadas."
        return {
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }
    effective_target = _effective_update_target(target, selected_events[0])
    if effective_target == "academico":
        return _apply_selected_academic_update_all(
            state,
            selected_events,
            update_payload,
            replan,
            current_count,
            has_new_input,
            last_user_text_value,
        )
    if effective_target == "laboral":
        return _apply_selected_laboral_update_all(
            state,
            selected_events,
            update_payload,
            replan,
            current_count,
            has_new_input,
            last_user_text_value,
        )
    return _apply_selected_extracurricular_update(
        state,
        selected_events[0],
        update_payload,
        replan,
        current_count,
        has_new_input,
        last_user_text_value,
    )


def _event_from_id(events: list[Event], event_id: str) -> Event | None:
    for event in events:
        if str(event.get("id")) == str(event_id):
            return event
    return None


def _queue_update_apply_confirmation(
    state: AgentState,
    target: str,
    selected_event: Event | dict | None,
    update_payload: str,
    change_request: dict,
    replan: dict,
    current_count: int,
    has_new_input: bool,
    last_user_text_value: str | None,
) -> dict:
    preview = _preview_update_payload(
        state,
        _effective_update_target(target, selected_event),
        selected_event,
        update_payload,
    )
    if preview["prompt"]:
        change_request["stage"] = "awaiting_update_new_details"
        change_request["update_payload"] = None
        change_request["update_summary"] = None
        replan["change_request"] = change_request
        replan["pending_prompt"] = str(preview["prompt"])
        return {
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }

    change_request["update_payload"] = update_payload
    change_request["update_summary"] = str(preview["summary"] or "").strip()
    change_request["stage"] = "awaiting_update_apply_confirmation"
    replan["change_request"] = change_request
    replan["pending_prompt"] = _build_final_update_confirmation_prompt(
        selected_event,
        str(preview["summary"] or "").strip(),
    )
    return {
        "phase": "validate",
        "replan": replan,
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_user_text_value,
        "awaiting_user_input": True,
    }


def _queue_update_all_apply_confirmation(
    state: AgentState,
    target: str,
    selected_events: list[Event],
    update_payload: str,
    change_request: dict,
    replan: dict,
    current_count: int,
    has_new_input: bool,
    last_user_text_value: str | None,
) -> dict:
    preview = _preview_update_payload_for_all(state, target, selected_events, update_payload)
    if preview["prompt"]:
        change_request["stage"] = "awaiting_update_all_details"
        change_request["update_payload"] = None
        change_request["update_summary"] = None
        replan["change_request"] = change_request
        replan["pending_prompt"] = str(preview["prompt"])
        return {
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }

    change_request["selected_event_ids"] = [str(event.get("id")) for event in selected_events]
    change_request["update_payload"] = update_payload
    change_request["update_summary"] = str(preview["summary"] or "").strip()
    change_request["stage"] = "awaiting_update_apply_confirmation"
    replan["change_request"] = change_request
    replan["pending_prompt"] = _build_final_update_all_confirmation_prompt(
        selected_events,
        str(preview["summary"] or "").strip(),
    )
    return {
        "phase": "validate",
        "replan": replan,
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_user_text_value,
        "awaiting_user_input": True,
    }


def _preview_update_payload(
    state: AgentState,
    target: str,
    selected_event: Event | dict | None,
    update_payload: str,
) -> dict[str, str | None]:
    if not selected_event:
        return {
            "prompt": _build_available_update_reference_prompt(
                target,
                _candidate_events_for_target(state, target),
            ),
            "summary": None,
        }
    if target in {"academico", "laboral"}:
        parsed = _parse_updated_schedule_payload(
            target=target,
            update_payload=update_payload,
            selected_event=selected_event,
            timezone=state.get("timezone", "America/Bogota"),
        )
        if parsed["prompt"]:
            return {"prompt": str(parsed["prompt"]), "summary": None}
        return {
            "prompt": None,
            "summary": _format_update_events_summary(list(parsed["events"])),
        }

    extracurricular_items = [_ensure_item(item) for item in state.get("extracurricular", [])]
    target_item_index = _find_extracurricular_item_index(extracurricular_items, selected_event)
    if target_item_index is None:
        return {
            "prompt": _build_available_update_reference_prompt(
                target,
                _candidate_events_for_target(state, target),
            ),
            "summary": None,
        }

    target_item = extracurricular_items[target_item_index]
    normalized_details = _strip_change_intent(update_payload, target_item.nombre)
    item, missing = parse_extracurricular_text(
        normalized_details,
        expected_is_variable=target_item.es_variable,
    )
    missing = [field for field in missing if field != "nombre"]
    if missing:
        return {
            "prompt": (
                f"{PROMPT_EXTRAS}\nActividad a cambiar: {target_item.nombre}.\n"
                "Faltan: " + ", ".join(missing) + "."
            ),
            "summary": None,
        }

    updated_name = target_item.nombre
    if _has_explicit_activity_name(update_payload):
        updated_name = item.nombre or target_item.nombre
    updated_item = (
        item.model_copy(update={"nombre": updated_name})
        if hasattr(item, "model_copy")
        else item.copy(update={"nombre": updated_name})
    )
    return {
        "prompt": None,
        "summary": _format_extracurricular_update_summary(updated_item),
    }


def _preview_update_payload_for_all(
    state: AgentState,
    target: str,
    selected_events: list[Event],
    update_payload: str,
) -> dict[str, str | None]:
    if not selected_events:
        return {"prompt": "No encontre las actividades seleccionadas.", "summary": None}
    return _preview_update_payload(
        state,
        _effective_update_target(target, selected_events[0]),
        selected_events[0],
        update_payload,
    )


def _build_initial_update_reference_prompt(target: str) -> str:
    if target == "academico":
        return "Que actividad academica deseas modificar?"
    if target == "laboral":
        return "Que actividad laboral deseas modificar?"
    if target == "activity_lookup":
        return "Que actividad deseas modificar?"
    return "Que actividad extracurricular deseas modificar?"


def _build_available_update_reference_prompt(
    target: str,
    events: list[Event],
    requested_name: str = "",
) -> str:
    target_label = {
        "academico": "academica",
        "laboral": "laboral",
        "extracurricular": "extracurricular",
    }.get(target, "registrada")
    if not events:
        return (
            "No encontre la actividad indicada. "
            f"No hay actividades de tipo {target_label} registradas."
        )

    requested = str(requested_name or "").strip()
    intro = "No pude identificar con claridad la actividad que deseas modificar."
    if requested:
        intro = f"No encontre una coincidencia clara para '{requested}'."
    return (
        f"{intro} Vuelve a escribirla indicando nombre, dia o horario.\n"
        "Estas son las actividades registradas:\n"
        f"{_build_match_table(events)}"
    )


def _effective_update_target(target: str, event: Event | dict | None) -> str:
    if target != "activity_lookup":
        return target
    return str(event.get("categoria") or "") if event else "extracurricular"


def _build_update_name_only_prompt(event: Event | dict | None) -> str:
    activity_name = str(event.get("titulo") or "la actividad") if event else "la actividad"
    return (
        f"Encontre la actividad '{activity_name}'.\n"
        "Indica que dias y horarios deseas modificar."
    )


def _build_update_all_details_prompt(events: list[Event]) -> str:
    activity_name = str(events[0].get("titulo") or "la actividad") if events else "la actividad"
    return (
        f"Encontre varias actividades llamadas '{activity_name}'.\n"
        "Indica los nuevos dias y horarios que deseas aplicar a todas."
    )


def _build_not_found_update_prompt(
    target: str,
    events: list[Event],
    requested_name: str,
) -> str:
    base = (
        "No encontre ninguna actividad con ese nombre en tu horario.\n"
        "Por favor verifica el nombre de la actividad."
    )
    if not events:
        return base
    suggestions = suggest_similar_titles(events, requested_name)
    if suggestions:
        return (
            f"{base}\n"
            "Actividades parecidas en tu horario:\n"
            + "\n".join(f"- {title}" for title in suggestions)
        )
    return f"{base}\nEstas son las actividades registradas:\n{_build_match_table(events)}"


def _reference_is_name_only(reference_text: str, event: Event | dict | None) -> bool:
    if not event:
        return False
    return normalize_text(reference_text) == normalize_text(str(event.get("titulo") or ""))


def _format_update_events_summary(events: list[Event]) -> str:
    if not events:
        return "Sin cambios."
    lines = []
    for event in events:
        line = f"- {event.get('dia')} {event.get('inicio')}-{event.get('fin')}"
        title = str(event.get("titulo") or "").strip()
        if title:
            line = f"{line} {title}"
        lines.append(line)
    return "\n".join(lines)


def _format_extracurricular_update_summary(item: ExtracurricularItem) -> str:
    days = ", ".join(item.dias) if item.dias else "Sin dias definidos"
    hours = (
        f"{item.hora_inicio}-{item.hora_fin}"
        if item.hora_inicio and item.hora_fin
        else item.detalle or "Sin horario definido"
    )
    return (
        f"- Actividad: {item.nombre}\n"
        f"- Dia(s): {days}\n"
        f"- Horario: {hours}"
    )

def _apply_laboral_change(
    state: AgentState,
    details: str,
    operation: str,
    replan: dict,
    current_count: int,
    has_new_input: bool,
    last_user_text_value: str | None,
) -> dict:
    messages = state.get("messages", [])
    if not details or not has_time_range(details):
        replan["pending_prompt"] = PROMPT_HORARIO
        return {
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }

    errors = list(state.get("errors", []))
    try:
        parsed = parse_work_schedule_text(details, state.get("timezone", "America/Bogota"))
    except ValueError as exc:
        errors.append(f"Horario laboral invalido: {exc}")
        replan["pending_prompt"] = PROMPT_HORARIO
        return {
            "errors": errors,
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }

    new_events: list[Event] = []
    for event in parsed:
        try:
            validate_event(event)
        except ValueError as exc:
            errors.append(f"Evento laboral invalido: {exc}")
            continue
        new_events.append(event)

    if operation == "add":
        updated_events = list(state.get("events", [])) + new_events
    else:
        remaining = [event for event in state.get("events", []) if event.get("categoria") != "laboral"]
        updated_events = remaining + new_events

    raw_inputs = dict(state.get("raw_inputs", {}))
    raw_inputs["horario_laboral_text"] = details

    replan["change_request"] = None
    replan["pending_prompt"] = None
    return {
        "events": updated_events,
        "errors": errors,
        "raw_inputs": raw_inputs,
        "replan": replan,
        "phase": "validate",
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_user_text_value,
        "awaiting_user_input": False,
    }


def _apply_academic_change(
    state: AgentState,
    details: str,
    operation: str,
    replan: dict,
    current_count: int,
    has_new_input: bool,
    last_user_text_value: str | None,
) -> dict:
    messages = state.get("messages", [])
    if not details or not has_time_range(details):
        replan["pending_prompt"] = PROMPT_HORARIO_ACADEMICO
        return {
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }

    errors = list(state.get("errors", []))
    try:
        parsed = parse_academic_schedule_text(details, state.get("timezone", "America/Bogota"))
    except ValueError as exc:
        errors.append(f"Horario academico invalido: {exc}")
        replan["pending_prompt"] = PROMPT_HORARIO_ACADEMICO
        return {
            "errors": errors,
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }

    new_events: list[Event] = []
    for event in parsed:
        try:
            validate_event(event)
        except ValueError as exc:
            errors.append(f"Evento academico invalido: {exc}")
            continue
        new_events.append(event)

    if operation == "add":
        updated_events = list(state.get("events", [])) + new_events
    else:
        remaining = [event for event in state.get("events", []) if event.get("categoria") != "academico"]
        updated_events = remaining + new_events

    raw_inputs = dict(state.get("raw_inputs", {}))
    raw_inputs["horario_academico_text"] = details

    replan["change_request"] = None
    replan["pending_prompt"] = None
    return {
        "events": updated_events,
        "errors": errors,
        "raw_inputs": raw_inputs,
        "replan": replan,
        "phase": "validate",
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_user_text_value,
        "awaiting_user_input": False,
    }


def _apply_extracurricular_change(
    state: AgentState,
    details: str,
    operation: str,
    activity_name: str,
    replan: dict,
    current_count: int,
    has_new_input: bool,
    last_user_text_value: str | None,
) -> dict:
    extracurricular_items = [_ensure_item(item) for item in state.get("extracurricular", [])]
    if not extracurricular_items and operation != "add":
        replan["pending_prompt"] = "No hay actividades extracurriculares registradas para modificar."
        return {
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }

    target_item = _match_extracurricular(activity_name, extracurricular_items)
    if operation == "add":
        target_item = None
    if not target_item and activity_name and operation != "add":
        disponibles = ", ".join(item.nombre for item in extracurricular_items)
        replan["pending_prompt"] = (
            f"La actividad '{activity_name}' no existe. "
            f"Actividades disponibles: {disponibles}. Usa la tabla anterior como referencia."
        )
        return {
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }
    if not target_item and len(extracurricular_items) == 1 and operation != "add":
        target_item = extracurricular_items[0]
    if not target_item and operation != "add":
        disponibles = ", ".join(item.nombre for item in extracurricular_items)
        replan["pending_prompt"] = (
            f"Indica que actividad quieres modificar. "
            f"Actividades disponibles: {disponibles}. Usa la tabla anterior como referencia."
        )
        return {
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }

    if operation == "delete":
        updated_extracurricular = [
            item
            for item in extracurricular_items
            if normalize_text(item.nombre) != normalize_text(target_item.nombre)
        ]
        updated_events = [
            event
            for event in state.get("events", [])
            if not (
                event.get("categoria") == "extracurricular"
                and normalize_text(str(event.get("titulo") or "")) == normalize_text(target_item.nombre)
            )
        ]
        replan["change_request"] = None
        replan["pending_prompt"] = None
        return {
            "events": updated_events,
            "errors": list(state.get("errors", [])),
            "extracurricular": updated_extracurricular,
            "replan": replan,
            "phase": "validate",
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": False,
        }

    if not details:
        activity_label = target_item.nombre if target_item else "nueva actividad"
        replan["pending_prompt"] = f"{PROMPT_EXTRAS}\nActividad actual: {activity_label}."
        return {
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }

    if operation == "add":
        items, missing = parse_extracurricular_items(details)
        if missing:
            replan["pending_prompt"] = _build_add_clarification_prompt(missing)
            return {
                "phase": "validate",
                "replan": replan,
                "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
                "last_user_text": last_user_text_value,
                "awaiting_user_input": True,
            }

        new_events, errors = _build_events_for_new_extracurricular_items(
            items,
            state.get("timezone", "America/Bogota"),
            list(state.get("errors", [])),
        )
        replan["change_request"] = None
        replan["pending_prompt"] = None
        return {
            "events": list(state.get("events", [])) + new_events,
            "errors": errors,
            "extracurricular": extracurricular_items + items,
            "replan": replan,
            "phase": "validate",
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": False,
        }

    reference_name = target_item.nombre if target_item else ""
    normalized_details = _strip_change_intent(details, reference_name)
    item, missing = parse_extracurricular_text(
        normalized_details,
        expected_is_variable=target_item.es_variable if target_item else None,
    )
    missing = [field for field in missing if field != "nombre"]
    if missing:
        replan["pending_prompt"] = (
            f"{PROMPT_EXTRAS}\nActividad a cambiar: {reference_name or 'nueva actividad'}.\n"
            "Faltan: " + ", ".join(missing) + "."
        )
        return {
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }

    if operation == "add":
        updated_item = item
        updated_extracurricular = extracurricular_items + [updated_item]
    else:
        updated_item = item.model_copy(update={"nombre": target_item.nombre}) if hasattr(item, "model_copy") else item.copy(update={"nombre": target_item.nombre})
        updated_extracurricular = [
            updated_item if normalize_text(existing.nombre) == normalize_text(target_item.nombre) else existing
            for existing in extracurricular_items
        ]
    updated_events, errors = _rebuild_extracurricular_events(
        updated_extracurricular,
        state.get("events", []),
        state.get("timezone", "America/Bogota"),
        list(state.get("errors", [])),
    )

    replan["change_request"] = None
    replan["pending_prompt"] = None
    return {
        "events": updated_events,
        "errors": errors,
        "extracurricular": updated_extracurricular,
        "replan": replan,
        "phase": "validate",
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_user_text_value,
        "awaiting_user_input": False,
    }


def _ensure_item(item: ExtracurricularItem | dict) -> ExtracurricularItem:
    if isinstance(item, ExtracurricularItem):
        return item
    return ExtracurricularItem(**item)


def _build_events_for_new_extracurricular_items(
    items: list[ExtracurricularItem],
    timezone: str,
    errors: list[str],
) -> tuple[list[Event], list[str]]:
    new_events: list[Event] = []
    for item in items:
        generated = _build_events_from_extracurricular_item(item, timezone)
        for event in generated:
            try:
                validate_event(event)
            except ValueError as exc:
                errors.append(f"Evento extracurricular invalido: {exc}")
                continue
            new_events.append(event)
    return new_events, errors


def _match_extracurricular(
    activity_name: str,
    items: list[ExtracurricularItem],
) -> ExtracurricularItem | None:
    normalized_name = normalize_text(activity_name)
    if not normalized_name:
        return None
    for item in items:
        item_name = normalize_text(item.nombre)
        if normalized_name == item_name or normalized_name in item_name or item_name in normalized_name:
            return item
    return None


def _strip_change_intent(details: str, activity_name: str) -> str:
    text = str(details or "").strip()
    if not text:
        return ""
    lowered = normalize_text(text)
    if activity_name:
        pattern = re.compile(re.escape(normalize_text(activity_name)))
        lowered = pattern.sub("", lowered)
    lowered = re.sub(
        r"\b(?:quiero|necesito|por favor|cambiar|modificar|ajustar|la|el|actividad|de|extracurricular|horario)\b",
        " ",
        lowered,
    )
    lowered = re.sub(r"\s+", " ", lowered).strip(" ,.:;")
    return lowered or text


def _rebuild_extracurricular_events(
    extracurricular_items: list[ExtracurricularItem],
    current_events: list[Event],
    timezone: str,
    errors: list[str],
) -> tuple[list[Event], list[str]]:
    new_events: list[Event] = []
    for item in extracurricular_items:
        generated = _build_events_from_extracurricular_item(item, timezone)
        for event in generated:
            try:
                validate_event(event)
            except ValueError as exc:
                errors.append(f"Evento extracurricular invalido: {exc}")
                continue
            new_events.append(event)

    remaining = [event for event in current_events if event.get("categoria") != "extracurricular"]
    return remaining + new_events, errors


def _build_events_from_extracurricular_item(
    item: ExtracurricularItem,
    timezone: str,
) -> list[Event]:
    if item.es_variable:
        return build_tentative_events(item, timezone)
    if item.dias and item.hora_inicio and item.hora_fin:
        return [
            Event(
                id=new_event_id(),
                dia=day,
                inicio=item.hora_inicio,
                fin=item.hora_fin,
                titulo=item.nombre,
                tipo="confirmado",
                categoria="extracurricular",
                origen="user_text",
                timezone=timezone,
            )
            for day in item.dias
        ]
    return build_fixed_events(item, timezone)


def _apply_activity_additions(
    state: AgentState,
    details: str,
    replan: dict,
    current_count: int,
    has_new_input: bool,
    last_user_text_value: str | None,
) -> dict:
    if not details or not has_time_range(details):
        replan["pending_prompt"] = (
            "Indica la actividad que deseas anadir con nombre, dias y horario. "
            "Si vas a anadir varias, puedes escribirlas en un solo mensaje."
        )
        return {
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }

    parsed = _parse_activity_additions(details, state.get("timezone", "America/Bogota"))
    if parsed["prompt"]:
        replan["pending_prompt"] = str(parsed["prompt"])
        return {
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }

    errors = list(state.get("errors", []))
    validated_events: list[Event] = []
    for event in list(parsed["events"]):
        try:
            validate_event(event)
        except ValueError as exc:
            errors.append(f"Evento invalido al anadir actividad: {exc}")
            continue
        validated_events.append(event)

    replan["change_request"] = None
    replan["pending_prompt"] = None
    return {
        "events": list(state.get("events", [])) + validated_events,
        "errors": errors,
        "extracurricular": [_ensure_item(item) for item in state.get("extracurricular", [])]
        + list(parsed["extracurricular"]),
        "replan": replan,
        "phase": "validate",
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_user_text_value,
        "awaiting_user_input": False,
    }


def _apply_selected_academic_update(
    state: AgentState,
    selected_event: Event | dict,
    update_payload: str,
    replan: dict,
    current_count: int,
    has_new_input: bool,
    last_user_text_value: str | None,
) -> dict:
    parsed = _parse_updated_schedule_payload(
        target="academico",
        update_payload=update_payload,
        selected_event=selected_event,
        timezone=state.get("timezone", "America/Bogota"),
    )
    if parsed["prompt"]:
        replan["pending_prompt"] = str(parsed["prompt"])
        change_request = dict(replan.get("change_request") or {})
        change_request["stage"] = "awaiting_update_new_details"
        replan["change_request"] = change_request
        return {
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }

    updated_events = _replace_selected_event(
        state.get("events", []),
        str(selected_event.get("id")),
        list(parsed["events"]),
    )
    raw_inputs = dict(state.get("raw_inputs", {}))
    raw_inputs["horario_academico_text"] = _serialize_events_for_category(updated_events, "academico")
    replan["change_request"] = None
    replan["pending_prompt"] = None
    return {
        "events": updated_events,
        "errors": list(state.get("errors", [])),
        "raw_inputs": raw_inputs,
        "replan": replan,
        "phase": "validate",
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_user_text_value,
        "awaiting_user_input": False,
    }


def _apply_selected_laboral_update(
    state: AgentState,
    selected_event: Event | dict,
    update_payload: str,
    replan: dict,
    current_count: int,
    has_new_input: bool,
    last_user_text_value: str | None,
) -> dict:
    parsed = _parse_updated_schedule_payload(
        target="laboral",
        update_payload=update_payload,
        selected_event=selected_event,
        timezone=state.get("timezone", "America/Bogota"),
    )
    if parsed["prompt"]:
        replan["pending_prompt"] = str(parsed["prompt"])
        change_request = dict(replan.get("change_request") or {})
        change_request["stage"] = "awaiting_update_new_details"
        replan["change_request"] = change_request
        return {
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }

    updated_events = _replace_selected_event(
        state.get("events", []),
        str(selected_event.get("id")),
        list(parsed["events"]),
    )
    raw_inputs = dict(state.get("raw_inputs", {}))
    raw_inputs["horario_laboral_text"] = _serialize_events_for_category(updated_events, "laboral")
    replan["change_request"] = None
    replan["pending_prompt"] = None
    return {
        "events": updated_events,
        "errors": list(state.get("errors", [])),
        "raw_inputs": raw_inputs,
        "replan": replan,
        "phase": "validate",
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_user_text_value,
        "awaiting_user_input": False,
    }


def _apply_selected_academic_update_all(
    state: AgentState,
    selected_events: list[Event],
    update_payload: str,
    replan: dict,
    current_count: int,
    has_new_input: bool,
    last_user_text_value: str | None,
) -> dict:
    parsed = _parse_updated_schedule_payload(
        target="academico",
        update_payload=update_payload,
        selected_event=selected_events[0],
        timezone=state.get("timezone", "America/Bogota"),
    )
    if parsed["prompt"]:
        replan["pending_prompt"] = str(parsed["prompt"])
        change_request = dict(replan.get("change_request") or {})
        change_request["stage"] = "awaiting_update_all_details"
        replan["change_request"] = change_request
        return {
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }

    updated_events = _replace_selected_events(
        state.get("events", []),
        [str(event.get("id")) for event in selected_events],
        list(parsed["events"]),
    )
    raw_inputs = dict(state.get("raw_inputs", {}))
    raw_inputs["horario_academico_text"] = _serialize_events_for_category(updated_events, "academico")
    replan["change_request"] = None
    replan["pending_prompt"] = None
    return {
        "events": updated_events,
        "errors": list(state.get("errors", [])),
        "raw_inputs": raw_inputs,
        "replan": replan,
        "phase": "validate",
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_user_text_value,
        "awaiting_user_input": False,
    }


def _apply_selected_laboral_update_all(
    state: AgentState,
    selected_events: list[Event],
    update_payload: str,
    replan: dict,
    current_count: int,
    has_new_input: bool,
    last_user_text_value: str | None,
) -> dict:
    parsed = _parse_updated_schedule_payload(
        target="laboral",
        update_payload=update_payload,
        selected_event=selected_events[0],
        timezone=state.get("timezone", "America/Bogota"),
    )
    if parsed["prompt"]:
        replan["pending_prompt"] = str(parsed["prompt"])
        change_request = dict(replan.get("change_request") or {})
        change_request["stage"] = "awaiting_update_all_details"
        replan["change_request"] = change_request
        return {
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }

    updated_events = _replace_selected_events(
        state.get("events", []),
        [str(event.get("id")) for event in selected_events],
        list(parsed["events"]),
    )
    raw_inputs = dict(state.get("raw_inputs", {}))
    raw_inputs["horario_laboral_text"] = _serialize_events_for_category(updated_events, "laboral")
    replan["change_request"] = None
    replan["pending_prompt"] = None
    return {
        "events": updated_events,
        "errors": list(state.get("errors", [])),
        "raw_inputs": raw_inputs,
        "replan": replan,
        "phase": "validate",
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_user_text_value,
        "awaiting_user_input": False,
    }


def _apply_selected_extracurricular_update(
    state: AgentState,
    selected_event: Event | dict,
    update_payload: str,
    replan: dict,
    current_count: int,
    has_new_input: bool,
    last_user_text_value: str | None,
) -> dict:
    extracurricular_items = [_ensure_item(item) for item in state.get("extracurricular", [])]
    target_item_index = _find_extracurricular_item_index(extracurricular_items, selected_event)
    if target_item_index is None:
        replan["pending_prompt"] = (
            "No pude ubicar la actividad extracurricular seleccionada. "
            "Indica nuevamente cual deseas modificar."
        )
        return {
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }

    target_item = extracurricular_items[target_item_index]
    normalized_details = _strip_change_intent(update_payload, target_item.nombre)
    item, missing = parse_extracurricular_text(
        normalized_details,
        expected_is_variable=target_item.es_variable,
    )
    missing = [field for field in missing if field != "nombre"]
    if missing:
        replan["pending_prompt"] = (
            f"{PROMPT_EXTRAS}\nActividad a cambiar: {target_item.nombre}.\n"
            "Faltan: " + ", ".join(missing) + "."
        )
        change_request = dict(replan.get("change_request") or {})
        change_request["stage"] = "awaiting_update_new_details"
        replan["change_request"] = change_request
        return {
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }

    updated_name = target_item.nombre
    if _has_explicit_activity_name(update_payload):
        updated_name = item.nombre or target_item.nombre
    updated_item = (
        item.model_copy(update={"nombre": updated_name})
        if hasattr(item, "model_copy")
        else item.copy(update={"nombre": updated_name})
    )
    extracurricular_items[target_item_index] = updated_item
    updated_events, errors = _rebuild_extracurricular_events(
        extracurricular_items,
        state.get("events", []),
        state.get("timezone", "America/Bogota"),
        list(state.get("errors", [])),
    )
    replan["change_request"] = None
    replan["pending_prompt"] = None
    return {
        "events": updated_events,
        "errors": errors,
        "extracurricular": extracurricular_items,
        "replan": replan,
        "phase": "validate",
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_user_text_value,
        "awaiting_user_input": False,
    }


def _parse_updated_schedule_payload(
    target: str,
    update_payload: str,
    selected_event: Event | dict,
    timezone: str,
) -> dict[str, object]:
    text = str(update_payload or "").strip()
    if not text:
        return {"events": [], "prompt": "Indica los nuevos datos de la actividad."}
    try:
        schedule = extract_natural_schedule_components(text)
    except ValueError as exc:
        error_text = str(exc).lower()
        if "no day found" in error_text:
            return {"events": [], "prompt": "Indica los dias exactos para la actividad."}
        if "ambiguous time range" in error_text:
            return {"events": [], "prompt": "Aclara AM o PM en el nuevo horario."}
        return {"events": [], "prompt": "No pude interpretar el nuevo horario de la actividad."}

    title = str(selected_event.get("titulo") or "Actividad")
    if target == "academico" and _has_explicit_activity_name(text):
        title = _infer_activity_title(text) or title
    if target == "laboral":
        title = "Trabajo"

    return {
        "events": _build_events_from_schedule(schedule, title, target, timezone),
        "prompt": None,
    }


def _replace_selected_event(
    events: list[Event],
    selected_event_id: str,
    replacement_events: list[Event],
) -> list[Event]:
    updated = [event for event in events if str(event.get("id")) != str(selected_event_id)]
    return updated + replacement_events


def _replace_selected_events(
    events: list[Event],
    selected_event_ids: list[str],
    replacement_events: list[Event],
) -> list[Event]:
    id_set = {str(event_id) for event_id in selected_event_ids}
    updated = [event for event in events if str(event.get("id")) not in id_set]
    return updated + replacement_events


def _serialize_events_for_category(events: list[Event], category: str) -> str:
    filtered = [
        event
        for event in events
        if event.get("categoria") == category
    ]
    filtered.sort(key=lambda event: (str(event.get("dia")), str(event.get("inicio"))))
    if category == "laboral":
        return "\n".join(
            f"{event.get('dia')} {event.get('inicio')}-{event.get('fin')}"
            for event in filtered
        )
    return "\n".join(
        f"{event.get('dia')} {event.get('inicio')}-{event.get('fin')} {event.get('titulo')}"
        for event in filtered
    )


def _find_extracurricular_item_index(
    items: list[ExtracurricularItem],
    event: Event | dict,
) -> int | None:
    event_title = normalize_text(str(event.get("titulo") or ""))
    event_day = normalize_text(str(event.get("dia") or ""))
    event_start = str(event.get("inicio") or "")
    event_end = str(event.get("fin") or "")
    for index, item in enumerate(items):
        if normalize_text(item.nombre) != event_title:
            continue
        if item.hora_inicio and item.hora_fin and item.hora_inicio == event_start and item.hora_fin == event_end:
            if any(normalize_text(day) == event_day for day in item.dias):
                return index
        if not item.dias and not item.hora_inicio and not item.hora_fin:
            return index
    return None


def _has_explicit_activity_name(text: str) -> bool:
    inferred = _infer_activity_title(text)
    return inferred not in {"", "Actividad", "Y", "E"}


def _apply_delete_change(
    state: AgentState,
    details: str,
    replan: dict,
    current_count: int,
    has_new_input: bool,
    last_user_text_value: str | None,
) -> dict:
    change_request = dict(replan.get("change_request") or {})
    stage = str(change_request.get("stage") or "")
    candidate_ids = list(change_request.get("candidate_event_ids") or [])
    details = details.strip()

    if stage == "awaiting_delete_confirmation":
        answer = parse_yes_no(details)
        if answer is None:
            replan["pending_prompt"] = str(
                replan.get("pending_prompt") or "Responde si o no para confirmar la eliminacion."
            )
            return {
                "phase": "validate",
                "replan": replan,
                "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
                "last_user_text": last_user_text_value,
                "awaiting_user_input": True,
            }
        if answer is False:
            replan["change_request"] = None
            replan["pending_prompt"] = None
            return {
                "phase": "validate",
                "replan": replan,
                "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
                "last_user_text": last_user_text_value,
                "awaiting_user_input": False,
            }
        return _delete_selected_events(
            state,
            candidate_ids,
            replan,
            current_count,
            has_new_input,
            last_user_text_value,
        )

    if stage == "awaiting_delete_scope":
        scope = _parse_delete_scope(details)
        if scope == "all":
            selected = _events_from_ids(state.get("events", []), candidate_ids)
            change_request["stage"] = "awaiting_delete_confirmation"
            change_request["candidate_event_ids"] = [str(event.get("id")) for event in selected]
            replan["change_request"] = change_request
            replan["pending_prompt"] = _build_delete_confirmation_prompt(selected)
            return {
                "phase": "validate",
                "replan": replan,
                "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
                "last_user_text": last_user_text_value,
                "awaiting_user_input": True,
            }
        if scope == "specific":
            change_request["stage"] = "awaiting_delete_identifier"
            replan["change_request"] = change_request
            replan["pending_prompt"] = "Indica el dia y horario exactos de la actividad que deseas eliminar."
            return {
                "phase": "validate",
                "replan": replan,
                "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
                "last_user_text": last_user_text_value,
                "awaiting_user_input": True,
            }
        if _has_day_or_time_hint(details):
            change_request["stage"] = "awaiting_delete_identifier"
            replan["change_request"] = change_request
            return _apply_delete_change(
                state,
                details,
                replan,
                current_count,
                has_new_input,
                last_user_text_value,
            )
        replan["pending_prompt"] = (
            "Se encontraron varias actividades con ese nombre.\n"
            "Deseas eliminar todas las actividades con ese nombre o solo una especifica?\n"
            "1) Eliminar todas\n"
            "2) Especificar dia y horario"
        )
        return {
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }

    if stage == "awaiting_delete_identifier":
        if not _has_day_or_time_hint(details):
            replan["pending_prompt"] = "Indica el dia y horario exactos de la actividad que deseas eliminar."
            return {
                "phase": "validate",
                "replan": replan,
                "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
                "last_user_text": last_user_text_value,
                "awaiting_user_input": True,
            }
        selected = _filter_events_by_hint(_events_from_ids(state.get("events", []), candidate_ids), details)
        if not selected:
            replan["pending_prompt"] = (
                "No encontre una coincidencia exacta con ese dia y horario. "
                "Indica el dia y horario exactos."
            )
            return {
                "phase": "validate",
                "replan": replan,
                "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
                "last_user_text": last_user_text_value,
                "awaiting_user_input": True,
            }
        if len(selected) > 1:
            replan["pending_prompt"] = (
                "Aun hay varias coincidencias con ese criterio.\n"
                f"{_build_match_table(selected)}\n"
                "Indica un dia y horario mas especificos."
            )
            return {
                "phase": "validate",
                "replan": replan,
                "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
                "last_user_text": last_user_text_value,
                "awaiting_user_input": True,
            }
        change_request["stage"] = "awaiting_delete_confirmation"
        change_request["candidate_event_ids"] = [str(selected[0].get("id"))]
        replan["change_request"] = change_request
        replan["pending_prompt"] = _build_delete_confirmation_prompt(selected)
        return {
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }

    events = [event for event in state.get("events", [])]
    requested_name = (
        str(change_request.get("activity_name") or "").strip()
        or _extract_activity_name_from_delete_text(details)
        or details
    )
    if not requested_name:
        replan["pending_prompt"] = "Cual es la actividad que deseas eliminar?"
        change_request["stage"] = "awaiting_delete_name"
        replan["change_request"] = change_request
        return {
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }

    matches = _find_delete_matches(events, requested_name)
    if not matches:
        disponibles = ", ".join(sorted({str(event.get("titulo") or "") for event in events if event.get("titulo")}))
        replan["pending_prompt"] = (
            f"No encontre la actividad indicada. Actividades disponibles: {disponibles}."
        )
        return {
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }

    if len(matches) > 1 and not _has_day_or_time_hint(details):
        activity_name = str(matches[0].get("titulo") or requested_name)
        change_request["stage"] = "awaiting_delete_scope"
        change_request["activity_name"] = activity_name
        change_request["candidate_event_ids"] = [str(event.get("id")) for event in matches]
        replan["change_request"] = change_request
        replan["pending_prompt"] = (
            f"Se encontraron varias actividades con el nombre {activity_name}.\n"
            "Deseas eliminar todas las actividades con ese nombre o solo una especifica?\n"
            "1) Eliminar todas\n"
            "2) Especificar dia y horario"
        )
        return {
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }

    selected = matches
    if len(matches) > 1 and _has_day_or_time_hint(details):
        selected = _filter_events_by_hint(matches, details)
        if not selected:
            replan["pending_prompt"] = (
                "No encontre una coincidencia exacta con ese dia y horario. "
                "Indica el dia y horario exactos."
            )
            return {
                "phase": "validate",
                "replan": replan,
                "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
                "last_user_text": last_user_text_value,
                "awaiting_user_input": True,
            }
    selected_ids = [str(event.get("id")) for event in selected]
    change_request["candidate_event_ids"] = selected_ids
    change_request["stage"] = "awaiting_delete_confirmation"
    change_request["activity_name"] = requested_name
    replan["change_request"] = change_request
    replan["pending_prompt"] = _build_delete_confirmation_prompt(selected)
    return {
        "phase": "validate",
        "replan": replan,
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_user_text_value,
        "awaiting_user_input": True,
    }


def _delete_selected_events(
    state: AgentState,
    candidate_ids: list[str],
    replan: dict,
    current_count: int,
    has_new_input: bool,
    last_user_text_value: str | None,
) -> dict:
    id_set = set(candidate_ids)
    selected_events = [event for event in state.get("events", []) if str(event.get("id")) in id_set]
    updated_events = [event for event in state.get("events", []) if str(event.get("id")) not in id_set]
    updated_extracurricular = _delete_from_extracurricular(
        [_ensure_item(item) for item in state.get("extracurricular", [])],
        selected_events,
    )
    replan["change_request"] = None
    replan["pending_prompt"] = None
    return {
        "events": updated_events,
        "extracurricular": updated_extracurricular,
        "errors": list(state.get("errors", [])),
        "replan": replan,
        "phase": "validate",
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_user_text_value,
        "awaiting_user_input": False,
    }


def _find_delete_matches(events: list[Event], details: str) -> list[Event]:
    normalized = normalize_text(details)
    hinted_day = _extract_day_hint(normalized)
    hinted_time = _extract_time_hint(details)
    title_key = _extract_best_title_key(events, normalized)
    if not title_key and not hinted_day and not hinted_time and normalized:
        return []

    matches = []
    for event in events:
        event_title = str(event.get("titulo") or "").strip()
        if not event_title:
            continue
        event_normalized = normalize_text(event_title)
        if title_key and event_normalized != title_key:
            continue
        if hinted_day and normalize_text(str(event.get("dia") or "")) != hinted_day:
            continue
        if hinted_time and hinted_time != f"{event.get('inicio')}-{event.get('fin')}":
            continue
        matches.append(event)
    return matches


def _extract_best_title_key(events: list[Event], normalized_details: str) -> str:
    return resolve_best_title_key(events, normalized_details)


def _extract_day_hint(normalized: str) -> str:
    aliases = {
        "lunes": "lunes",
        "lun": "lunes",
        "martes": "martes",
        "mar": "martes",
        "miercoles": "miercoles",
        "mie": "miercoles",
        "jueves": "jueves",
        "jue": "jueves",
        "viernes": "viernes",
        "vie": "viernes",
        "sabado": "sabado",
        "sab": "sabado",
        "domingo": "domingo",
        "dom": "domingo",
    }
    for token, canonical in aliases.items():
        if re.search(rf"\b{re.escape(token)}\b", normalized):
            return canonical
    return ""


def _extract_time_hint(details: str) -> str:
    match = re.search(
        r"(\d{1,2}(?::\d{2})?\s*(?:[ap]\.?\s*m\.?)?)\s*(?:-|a|hasta)\s*"
        r"(\d{1,2}(?::\d{2})?\s*(?:[ap]\.?\s*m\.?)?)",
        details,
        re.IGNORECASE,
    )
    if not match:
        return ""
    start_raw = _normalize_meridiem_text(match.group(1))
    end_raw = _normalize_meridiem_text(match.group(2))
    start_has_meridiem = bool(re.search(r"[ap]m$", start_raw))
    end_has_meridiem = bool(re.search(r"[ap]m$", end_raw))
    if start_has_meridiem and not end_has_meridiem:
        end_raw = f"{end_raw}{start_raw[-2:]}"
    elif end_has_meridiem and not start_has_meridiem:
        start_raw = f"{start_raw}{end_raw[-2:]}"
    try:
        if not start_has_meridiem and not end_has_meridiem and ":" not in start_raw and ":" not in end_raw:
            return ""
        return f"{normalize_time(start_raw)}-{normalize_time(end_raw)}"
    except ValueError:
        return ""


def _normalize_meridiem_text(value: str) -> str:
    normalized = normalize_text(value)
    normalized = normalized.replace(".", "")
    normalized = normalized.replace(" ", "")
    normalized = normalized.replace("a m", "am").replace("p m", "pm")
    return normalized


def _has_day_or_time_hint(details: str) -> bool:
    normalized = normalize_text(details)
    return bool(_extract_day_hint(normalized) or _extract_time_hint(details))


def _build_match_table(matches: list[Event]) -> str:
    rows = [
        (str(event.get("dia") or ""), str(event.get("titulo") or ""), f"{event.get('inicio')}-{event.get('fin')}")
        for event in matches
    ]
    day_width = max(len("Dia"), *(len(row[0]) for row in rows))
    title_width = max(len("Actividad"), *(len(row[1]) for row in rows))
    hour_width = max(len("Hora"), *(len(row[2]) for row in rows))
    separator = "+" + "-" * (day_width + 2) + "+" + "-" * (title_width + 2) + "+" + "-" * (hour_width + 2) + "+"
    lines = [
        separator,
        f"| {'Dia'.ljust(day_width)} | {'Actividad'.ljust(title_width)} | {'Hora'.ljust(hour_width)} |",
        separator,
    ]
    for row in rows:
        lines.append(
            f"| {row[0].ljust(day_width)} | {row[1].ljust(title_width)} | {row[2].ljust(hour_width)} |"
        )
        lines.append(separator)
    return "\n".join(lines)


def _build_delete_confirmation_prompt(matches: list[Event]) -> str:
    if len(matches) == 1:
        event = matches[0]
        return (
            "Estas seguro de que deseas eliminar la actividad:\n"
            f"{event.get('titulo')}\n"
            f"{event.get('dia')} {event.get('inicio')}-{event.get('fin')} ?"
        )
    activity_name = str(matches[0].get("titulo") or "actividad")
    schedules = "\n".join(
        f"- {event.get('dia')} {event.get('inicio')}-{event.get('fin')}" for event in matches
    )
    return (
        "Estas seguro de que deseas eliminar la actividad:\n"
        f"{activity_name}\n"
        f"{schedules}"
    )


def _delete_from_extracurricular(
    items: list[ExtracurricularItem],
    deleted_events: list[Event],
) -> list[ExtracurricularItem]:
    if not deleted_events:
        return items
    deleted_by_name: dict[str, set[tuple[str, str, str]]] = {}
    for event in deleted_events:
        deleted_by_name.setdefault(normalize_text(str(event.get("titulo") or "")), set()).add(
            (
                normalize_text(str(event.get("dia") or "")),
                str(event.get("inicio") or ""),
                str(event.get("fin") or ""),
            )
        )

    updated: list[ExtracurricularItem] = []
    for item in items:
        key = normalize_text(item.nombre)
        matches = deleted_by_name.get(key, set())
        if not matches:
            updated.append(item)
            continue
        if item.hora_inicio and item.hora_fin:
            remaining_days = [
                day
                for day in item.dias
                if (normalize_text(day), item.hora_inicio, item.hora_fin) not in matches
            ]
        else:
            remaining_days = [day for day in item.dias if (normalize_text(day), "", "") not in matches]
        if not remaining_days:
            continue
        detail = item.detalle
        if item.hora_inicio and item.hora_fin:
            detail = f"{', '.join(remaining_days)} {item.hora_inicio}-{item.hora_fin}"
        updated_item = item.model_copy(update={"dias": remaining_days, "detalle": detail}) if hasattr(item, "model_copy") else item.copy(update={"dias": remaining_days, "detalle": detail})
        updated.append(updated_item)
    return updated


def _parse_activity_additions(text: str, timezone: str) -> dict[str, object]:
    chunks = _split_activity_chunks(text)
    if not chunks:
        return {"events": [], "extracurricular": [], "prompt": "Indica la actividad con nombre, dias y horario."}

    events: list[Event] = []
    extracurricular_items: list[ExtracurricularItem] = []
    for chunk in chunks:
        try:
            schedule = extract_natural_schedule_components(chunk)
        except ValueError as exc:
            error_text = str(exc).lower()
            title = _infer_activity_title(chunk)
            if "no day found" in error_text:
                return {
                    "events": [],
                    "extracurricular": [],
                    "prompt": f"Indica los dias exactos para la actividad {title}.",
                }
            if "ambiguous time range" in error_text:
                return {
                    "events": [],
                    "extracurricular": [],
                    "prompt": f"Aclara AM o PM para la actividad {title}.",
                }
            return {
                "events": [],
                "extracurricular": [],
                "prompt": f"No pude interpretar el horario de la actividad {title}.",
            }

        category = _infer_activity_category(chunk)
        if category == "extracurricular":
            item, missing = parse_extracurricular_text(chunk, expected_is_variable=False)
            if missing:
                return {
                    "events": [],
                    "extracurricular": [],
                    "prompt": _build_add_clarification_prompt(missing),
                }
            extracurricular_items.append(item)
            events.extend(_build_events_from_extracurricular_item(item, timezone))
            continue

        title = _infer_activity_title(chunk)
        chunk_events = _build_events_from_schedule(
            schedule,
            title,
            category,
            timezone,
        )
        events.extend(chunk_events)

    return {"events": events, "extracurricular": extracurricular_items, "prompt": None}


def _split_activity_chunks(text: str) -> list[str]:
    raw = str(text or "").strip()
    if not raw:
        return []

    coarse_parts = [part.strip(" ,") for part in re.split(r"[;\n]+", raw) if part.strip(" ,")]
    chunks: list[str] = []
    for part in coarse_parts:
        matches = list(_TIME_RANGE_PATTERN.finditer(part))
        if len(matches) <= 1:
            chunks.append(part)
            continue
        cursor = 0
        for index, match in enumerate(matches[:-1]):
            next_match = matches[index + 1]
            boundary = _find_activity_boundary(part, match.end(), next_match.start())
            if boundary is None:
                continue
            chunk_end, next_cursor = boundary
            chunk = part[cursor:chunk_end].strip(" ,")
            if chunk:
                chunks.append(chunk)
            cursor = next_cursor
        tail = part[cursor:].strip(" ,")
        if tail:
            chunks.append(tail)
    return chunks


def _find_activity_boundary(text: str, start: int, end: int) -> tuple[int, int] | None:
    between = text[start:end]
    separator = _ACTIVITY_SEPARATOR_PATTERN.search(between)
    if not separator:
        return None
    return start + separator.start(), start + separator.end()


def _infer_activity_title(text: str) -> str:
    item, missing = parse_extracurricular_text(text, expected_is_variable=False)
    if item.nombre and "nombre" not in missing:
        return item.nombre

    normalized = normalize_text(text)
    without_time = _TIME_RANGE_PATTERN.sub(" ", normalized)
    without_days = _DAY_MARKER_PATTERN.sub(" ", without_time)
    without_fillers = re.sub(
        r"\b(?:de|desde|hasta|las|actividad|tipo|academica|academico|laboral|extracurricular|"
        r"quiero|anadir|agregar|sumar|incluir|hago|voy|tengo|solo|para|mi|mis|y|e)\b",
        " ",
        without_days,
    )
    words = [word for word in re.findall(r"[a-z]+", without_fillers) if word]
    if not words:
        return "Actividad"
    return " ".join(words[:4]).title()


def _infer_activity_category(text: str) -> str:
    normalized = normalize_text(text)
    if any(token in normalized for token in _WORK_KEYWORDS):
        return "laboral"
    if any(token in normalized for token in _ACADEMIC_KEYWORDS):
        return "academico"
    return "extracurricular"


def _build_events_from_schedule(
    schedule: dict[str, object],
    title: str,
    category: str,
    timezone: str,
) -> list[Event]:
    events: list[Event] = []
    start = str(schedule["start"])
    end = str(schedule["end"])
    overnight = bool(schedule.get("overnight"))
    for day in list(schedule["days"]):
        if not overnight:
            events.append(
                Event(
                    id=new_event_id(),
                    dia=day,
                    inicio=start,
                    fin=end,
                    titulo=title,
                    tipo="confirmado",
                    categoria=category,
                    origen="user_text",
                    timezone=timezone,
                )
            )
            continue
        events.append(
            Event(
                id=new_event_id(),
                dia=day,
                inicio=start,
                fin="23:59",
                titulo=title,
                tipo="confirmado",
                categoria=category,
                origen="user_text",
                timezone=timezone,
            )
        )
        if end != "00:00":
            events.append(
                Event(
                    id=new_event_id(),
                    dia=_next_day(day),
                    inicio="00:00",
                    fin=end,
                    titulo=title,
                    tipo="confirmado",
                    categoria=category,
                    origen="user_text",
                    timezone=timezone,
                )
            )
    return events


def _next_day(day: str) -> str:
    order = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"]
    return order[(order.index(day) + 1) % len(order)]


def _build_schedule_detail(schedule: dict[str, object]) -> str:
    days = list(schedule.get("days") or [])
    start = str(schedule.get("start") or "")
    end = str(schedule.get("end") or "")
    if schedule.get("is_all_days"):
        return f"Todos los dias {start}-{end}"
    return f"{', '.join(days)} {start}-{end}"


def _build_frequency_label(schedule: dict[str, object]) -> str | None:
    days = list(schedule.get("days") or [])
    if not days:
        return None
    if schedule.get("is_all_days"):
        return "todos los dias, desde lunes a domingo"
    return ", ".join(days)


def _build_add_clarification_prompt(missing: list[str]) -> str:
    if any("aclarar am o pm" in field.lower() for field in missing):
        return "Aclara AM o PM para las actividades que deseas anadir."
    if any("horario con dias y horas" in field.lower() for field in missing):
        return "Indica el nombre, los dias exactos y el horario de cada actividad que deseas anadir."
    return "Necesito un poco mas de detalle para anadir esas actividades: " + ", ".join(missing) + "."


def _parse_delete_scope(text: str) -> str | None:
    normalized = normalize_text(text)
    if normalized in {"1", "1.", "1)", "todas", "toda", "eliminar todas"} or "todas" in normalized:
        return "all"
    if normalized in {"2", "2.", "2)", "especificar", "una", "solo una", "especifica"}:
        return "specific"
    return None


def _events_from_ids(events: list[Event], candidate_ids: list[str]) -> list[Event]:
    id_set = set(candidate_ids)
    return [event for event in events if str(event.get("id")) in id_set]


def _filter_events_by_hint(events: list[Event], details: str) -> list[Event]:
    hinted_day = _extract_day_hint(normalize_text(details))
    hinted_time = _extract_time_hint(details)
    filtered: list[Event] = []
    for event in events:
        if hinted_day and normalize_text(str(event.get("dia") or "")) != hinted_day:
            continue
        if hinted_time and hinted_time != f"{event.get('inicio')}-{event.get('fin')}":
            continue
        filtered.append(event)
    return filtered


def _extract_activity_name_from_delete_text(details: str) -> str:
    normalized = normalize_text(details)
    if not normalized:
        return ""
    match = re.search(
        r"(?:eliminar|borrar|quitar)\s+(?:la\s+actividad\s+)?(?:de\s+)?([a-z\s]+)",
        normalized,
    )
    if match:
        candidate = match.group(1)
        candidate = _DAY_MARKER_PATTERN.split(candidate)[0]
        candidate = _TIME_RANGE_PATTERN.split(candidate)[0]
        cleaned = re.sub(r"\b(?:el|la|los|las|de)\b", " ", candidate)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.:;")
        if cleaned:
            return cleaned.title()
    return ""
