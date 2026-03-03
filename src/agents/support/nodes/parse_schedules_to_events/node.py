"""Nodo para convertir horarios crudos en eventos."""

from __future__ import annotations

from agents.support.nodes.utils import append_message
from agents.support.state import AgentState, Event, validate_event
from agents.support.tools.llm import llm_normalize_schedule
from agents.support.tools.schedule_parser import (
    parse_academic_schedule_text,
    parse_work_schedule_text,
)

from .prompt import PROMPT_ERROR


def parse_schedules_to_events(state: AgentState) -> dict:
    """Convierte horarios en eventos y avanza a extras."""
    raw_inputs = state.get("raw_inputs", {})
    messages = state.get("messages", [])
    events: list[Event] = list(state.get("events", []))
    initial_count = len(events)
    errors = list(state.get("errors", []))

    laboral_text = raw_inputs.get("horario_laboral_text")
    if laboral_text:
        try:
            parsed = parse_work_schedule_text(
                laboral_text, state.get("timezone", "America/Bogota")
            )
        except ValueError as exc:
            errors.append(f"Horario laboral invalido: {exc}")
            return {
                "errors": errors,
                "phase": "schedules",
                "awaiting_user_input": True,
                "messages": append_message(messages, "assistant", PROMPT_ERROR),
            }

        for event in parsed:
            try:
                validate_event(event)
            except ValueError as exc:
                errors.append(f"Evento laboral invalido: {exc}")
                continue
            events.append(event)

    academico_text = raw_inputs.get("horario_academico_text")
    if academico_text:
        candidate_texts: list[str] = []
        normalized = llm_normalize_schedule(academico_text)
        if normalized:
            candidate_texts.append(normalized)
        candidate_texts.append(academico_text)

        parsed: list[Event] = []
        for candidate in candidate_texts:
            try:
                parsed = parse_academic_schedule_text(
                    candidate, state.get("timezone", "America/Bogota")
                )
            except ValueError as exc:
                errors.append(f"Horario academico invalido: {exc}")
                parsed = []
            if parsed:
                break

        for event in parsed:
            try:
                validate_event(event)
            except ValueError as exc:
                errors.append(f"Evento academico invalido: {exc}")
                continue
            events.append(event)

    if len(events) == initial_count and (laboral_text or academico_text):
        return {
            "errors": errors,
            "phase": "schedules",
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                "No pude interpretar tu horario. "
                "Puedes enviar el texto del correo con el detalle de clases "
                "o un formato como: Lunes 6-7 Materia.",
            ),
        }

    return {
        "events": events,
        "errors": errors,
        "phase": "extras",
        "awaiting_user_input": False,
    }
