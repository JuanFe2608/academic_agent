"""Nodo para aplicar modificaciones solicitadas por el usuario."""

from __future__ import annotations

from agents.support.nodes.collect_extracurricular_details import parse_extracurricular_text
from agents.support.nodes.generate_tentative_extracurricular import build_tentative_events
from agents.support.nodes.utils import (
    append_message,
    detect_new_input,
    has_time_range,
)
from agents.support.state import AgentState, Event, validate_event
from agents.support.tools.schedule_parser import parse_work_schedule_text

from .prompt import PROMPT_EXTRAS, PROMPT_HORARIO


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
    details = (change_request.get("details") or "").strip() or (last_text if has_new_input else "")

    if target == "horario":
        return _apply_horario_change(
            state, details, replan, current_count, has_new_input, last_user_text_value
        )
    if target == "extracurricular":
        return _apply_extracurricular_change(
            state, details, replan, current_count, has_new_input, last_user_text_value
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


def _apply_horario_change(
    state: AgentState,
    details: str,
    replan: dict,
    current_count: int,
    has_new_input: bool,
    last_user_text_value: str | None,
) -> dict:
    messages = state.get("messages", [])
    if not details or not has_time_range(details):
        return {
            "messages": append_message(messages, "assistant", PROMPT_HORARIO),
            "phase": "validate",
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }

    errors = list(state.get("errors", []))
    try:
        parsed = parse_work_schedule_text(details, state.get("timezone", "America/Bogota"))
    except ValueError as exc:
        errors.append(f"Horario laboral invalido: {exc}")
        return {
            "errors": errors,
            "messages": append_message(messages, "assistant", PROMPT_HORARIO),
            "phase": "validate",
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

    remaining = [event for event in state.get("events", []) if event.get("categoria") != "laboral"]
    updated_events = remaining + new_events

    raw_inputs = dict(state.get("raw_inputs", {}))
    raw_inputs["horario_laboral_text"] = details

    replan["change_request"] = None
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
    replan: dict,
    current_count: int,
    has_new_input: bool,
    last_user_text_value: str | None,
) -> dict:
    messages = state.get("messages", [])
    if not details:
        return {
            "messages": append_message(messages, "assistant", PROMPT_EXTRAS),
            "phase": "validate",
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }

    item, missing = parse_extracurricular_text(details)
    if missing:
        prompt = PROMPT_EXTRAS + "\nFaltan: " + ", ".join(missing) + "."
        return {
            "messages": append_message(messages, "assistant", prompt),
            "phase": "validate",
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }

    errors = list(state.get("errors", []))
    timezone = state.get("timezone", "America/Bogota")
    tentativos = build_tentative_events(item, timezone)
    new_events: list[Event] = []
    for event in tentativos:
        try:
            validate_event(event)
        except ValueError as exc:
            errors.append(f"Tentativo extracurricular invalido: {exc}")
            continue
        new_events.append(event)

    remaining = [event for event in state.get("events", []) if event.get("categoria") != "extracurricular"]
    updated_events = remaining + new_events

    replan["change_request"] = None
    return {
        "events": updated_events,
        "errors": errors,
        "extracurricular": [item],
        "replan": replan,
        "phase": "validate",
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_user_text_value,
        "awaiting_user_input": False,
    }
