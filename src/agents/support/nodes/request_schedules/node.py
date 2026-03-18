"""Nodo para solicitar el horario semanal según la ocupación."""

from __future__ import annotations

from agents.support.nodes.utils import (
    append_message,
    detect_new_input,
    has_time_range,
    normalize_text,
)
from agents.support.state import AgentState, RawInputs

from .prompt import (
    PROMPT_ACADEMICO,
    PROMPT_AMBOS,
    PROMPT_LABORAL,
    PROMPT_NINGUNA,
    PROMPT_OCCUPATION,
)


def request_schedules(state: AgentState) -> dict:
    """Solicita horarios académicos y/o laborales según ocupación."""
    messages = state.get("messages", [])
    has_new_input, last_text, current_count = detect_new_input(
        messages,
        state.get("user_message_count", 0),
        state.get("awaiting_user_input", False),
        state.get("last_user_text"),
    )
    raw_inputs = dict(state.get("raw_inputs", {}))
    profile = dict(state.get("student_profile", {}))
    occupation = profile.get("occupation")

    if has_new_input and last_text:
        if not occupation:
            occupation = _parse_occupation(last_text)
            if occupation:
                profile["occupation"] = occupation
        else:
            raw_inputs = _consume_schedule_text_by_stage(raw_inputs, last_text, occupation)

    if not occupation:
        return {
            "student_profile": profile,
            "raw_inputs": raw_inputs,
            "phase": "schedules",
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_text if has_new_input else state.get("last_user_text"),
            "awaiting_user_input": True,
            "messages": append_message(messages, "assistant", PROMPT_OCCUPATION),
        }

    if occupation == "ninguna":
        return {
            "student_profile": profile,
            "phase": "end",
            "awaiting_user_input": False,
            "messages": append_message(messages, "assistant", PROMPT_NINGUNA),
        }

    missing = _missing_schedule_inputs(raw_inputs, occupation)
    if missing:
        return {
            "student_profile": profile,
            "raw_inputs": raw_inputs,
            "phase": "schedules",
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_text if has_new_input else state.get("last_user_text"),
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                _build_prompt_for_missing(missing, occupation),
            ),
        }

    return {
        "student_profile": profile,
        "raw_inputs": raw_inputs,
        "phase": "schedules",
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_text if has_new_input else state.get("last_user_text"),
        "awaiting_user_input": False,
        "messages": append_message(
            messages, "assistant", "Gracias. Voy a procesar tus horarios."
        ),
    }


def _consume_schedule_text_by_stage(raw_inputs: RawInputs, text: str, occupation: str | None) -> RawInputs:
    """Consume texto segun el paso pendiente del flujo de horarios."""
    updated = dict(raw_inputs)
    clean_text = str(text or "").strip()
    if not clean_text:
        return updated

    if occupation == "solo_estudio":
        if not updated.get("horario_academico_text"):
            updated["horario_academico_text"] = clean_text
        return updated

    if occupation == "ambos":
        if not updated.get("horario_academico_text"):
            updated["horario_academico_text"] = clean_text
            return updated
        if not updated.get("horario_laboral_text"):
            updated["horario_laboral_text"] = clean_text
        return updated

    return updated


def _missing_schedule_inputs(raw_inputs: RawInputs, occupation: str | None) -> list[str]:
    missing: list[str] = []
    if occupation == "solo_estudio":
        if not raw_inputs.get("horario_academico_text"):
            missing.append("horario_academico_text")
        return missing

    if occupation == "ambos":
        if not raw_inputs.get("horario_academico_text"):
            missing.append("horario_academico_text")
        elif not raw_inputs.get("horario_laboral_text"):
            missing.append("horario_laboral_text")
    return missing


def _build_prompt_for_missing(missing: list[str], occupation: str | None) -> str:
    if not missing:
        return "Comparte tus horarios en texto."
    first = missing[0]
    if first == "horario_academico_text":
        return PROMPT_AMBOS if occupation == "ambos" else PROMPT_ACADEMICO
    if first == "horario_laboral_text":
        return PROMPT_LABORAL

    if occupation == "solo_estudio":
        return PROMPT_ACADEMICO
    if occupation == "ambos":
        return PROMPT_AMBOS
    return "Comparte tus horarios."


def _parse_occupation(text: str) -> str | None:
    normalized = normalize_text(text)
    if normalized in {"1", "solo estudio", "solo estudiar"} or normalized.startswith("1"):
        return "solo_estudio"
    if normalized in {"2", "ambos", "estudio y trabajo"} or normalized.startswith("2"):
        return "ambos"
    if normalized in {"3", "ninguna"} or normalized.startswith("3"):
        return "ninguna"
    return None
