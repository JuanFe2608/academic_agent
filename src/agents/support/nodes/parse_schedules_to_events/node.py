"""Nodo para convertir horarios crudos en eventos."""

from __future__ import annotations

from typing import Callable

from agents.support.nodes.utils import append_message, has_ambiguous_time_range
from agents.support.state import AgentState, Event, validate_event
from agents.support.tools.llm import (
    llm_normalize_schedule,
)
from agents.support.tools.schedule_parser import (
    parse_academic_schedule_text,
    parse_work_schedule_text,
)

from .prompt import PROMPT_ERROR


def parse_schedules_to_events(state: AgentState) -> dict:
    """Convierte horarios en eventos y avanza a extras."""
    raw_inputs = dict(state.get("raw_inputs", {}))
    messages = state.get("messages", [])
    events: list[Event] = list(state.get("events", []))
    initial_count = len(events)
    errors = list(state.get("errors", []))
    laboral_text = str(raw_inputs.get("horario_laboral_text") or "").strip()
    academico_text = str(raw_inputs.get("horario_academico_text") or "").strip()

    if raw_inputs.get("horario_laboral_img") and not laboral_text:
        return {
            "errors": errors,
            "raw_inputs": raw_inputs,
            "phase": "schedules",
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                "Por ahora solo acepto horario laboral en texto. Comparte el horario por escrito.",
            ),
        }

    if raw_inputs.get("horario_academico_img") and not academico_text:
        return {
            "errors": errors,
            "raw_inputs": raw_inputs,
            "phase": "schedules",
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                "Por ahora solo acepto horario academico en texto. Comparte el horario por escrito.",
            ),
        }

    if laboral_text:
        if has_ambiguous_time_range(laboral_text):
            return {
                "errors": errors,
                "raw_inputs": raw_inputs,
                "phase": "schedules",
                "awaiting_user_input": True,
                "messages": append_message(
                    messages,
                    "assistant",
                    "Tu horario laboral tiene horas ambiguas (ej: 9-10). "
                    "Por favor aclara AM o PM en cada rango.",
                ),
            }
        laboral_parsed, laboral_error = _parse_first_valid(
            _build_schedule_candidates(laboral_text, "laboral"),
            lambda candidate: parse_work_schedule_text(
                candidate, state.get("timezone", "America/Bogota")
            ),
        )
        if not laboral_parsed:
            if laboral_error:
                errors.append(f"Horario laboral invalido: {laboral_error}")
            return {
                "errors": errors,
                "raw_inputs": raw_inputs,
                "phase": "schedules",
                "awaiting_user_input": True,
                "messages": append_message(messages, "assistant", PROMPT_ERROR),
            }

        for event in laboral_parsed:
            try:
                validate_event(event)
            except ValueError as exc:
                errors.append(f"Evento laboral invalido: {exc}")
                continue
            events.append(event)

    if academico_text:
        if has_ambiguous_time_range(academico_text):
            return {
                "errors": errors,
                "raw_inputs": raw_inputs,
                "phase": "schedules",
                "awaiting_user_input": True,
                "messages": append_message(
                    messages,
                    "assistant",
                    "Tu horario academico tiene horas ambiguas (ej: 9-10). "
                    "Por favor aclara AM o PM en cada rango.",
                ),
            }
        academico_parsed, academico_error = _parse_first_valid(
            _build_schedule_candidates(academico_text, "academico"),
            lambda candidate: parse_academic_schedule_text(
                candidate, state.get("timezone", "America/Bogota")
            ),
        )
        if not academico_parsed and academico_error:
            errors.append(f"Horario academico invalido: {academico_error}")

        for event in academico_parsed:
            try:
                validate_event(event)
            except ValueError as exc:
                errors.append(f"Evento academico invalido: {exc}")
                continue
            events.append(event)

    has_schedule_inputs = bool(
        laboral_text
        or academico_text
    )
    if len(events) == initial_count and has_schedule_inputs:
        return {
            "errors": errors,
            "raw_inputs": raw_inputs,
            "phase": "schedules",
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                "No pude interpretar tu horario. "
                "Comparte el texto con formato de dias y horas "
                "(ej: Lunes 08:00-10:00 Algebra).",
            ),
        }

    return {
        "events": events,
        "errors": errors,
        "raw_inputs": raw_inputs,
        "phase": "extras",
        "awaiting_user_input": False,
    }


def _build_schedule_candidates(text: str, hint: str) -> list[str]:
    candidates: list[str] = []
    normalized = llm_normalize_schedule(text, hint)
    if normalized:
        candidates.append(normalized)
    candidates.append(text)
    return _dedupe_candidates(candidates)


def _dedupe_candidates(candidates: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in candidates:
        normalized = str(item or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _parse_first_valid(
    candidates: list[str],
    parser: Callable[[str], list[Event]],
) -> tuple[list[Event], str | None]:
    last_error: str | None = None
    for candidate in candidates:
        try:
            parsed = parser(candidate)
        except ValueError as exc:
            last_error = str(exc)
            continue
        if parsed:
            return parsed, None
    return [], last_error
