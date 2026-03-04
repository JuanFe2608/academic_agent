"""Nodo para solicitar horarios crudos segun ocupacion."""

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
    PROMPT_LABORAL_TIPO,
    PROMPT_NINGUNA,
)


def request_schedules(state: AgentState) -> dict:
    """Solicita horarios academicos y/o laborales segun ocupacion."""
    messages = state.get("messages", [])
    has_new_input, last_text, current_count = detect_new_input(
        messages,
        state.get("user_message_count", 0),
        state.get("awaiting_user_input", False),
        state.get("last_user_text"),
    )
    raw_inputs = dict(state.get("raw_inputs", {}))
    ocupacion = state.get("student_profile", {}).get("ocupacion")

    if ocupacion == "ninguna":
        return {
            "phase": "end",
            "messages": append_message(messages, "assistant", PROMPT_NINGUNA),
        }

    if has_new_input and last_text:
        raw_inputs = _consume_schedule_text_by_stage(raw_inputs, last_text, ocupacion)

    missing = _missing_schedule_inputs(raw_inputs, ocupacion)
    if missing:
        return {
            "raw_inputs": raw_inputs,
            "phase": "schedules",
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_text if has_new_input else state.get("last_user_text"),
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                _build_prompt_for_missing(missing, ocupacion),
            ),
        }

    return {
        "raw_inputs": raw_inputs,
        "phase": "schedules",
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_text if has_new_input else state.get("last_user_text"),
        "awaiting_user_input": False,
        "messages": append_message(
            messages, "assistant", "Gracias. Voy a procesar tus horarios."
        ),
    }


def _consume_schedule_text_by_stage(raw_inputs: RawInputs, text: str, ocupacion: str | None) -> RawInputs:
    """Consume texto segun el paso pendiente del flujo de horarios."""
    updated = dict(raw_inputs)
    clean_text = str(text or "").strip()
    if not clean_text:
        return updated

    if ocupacion == "solo_trabajo":
        if not updated.get("horario_laboral_tipo"):
            work_type = _parse_work_type(clean_text)
            if work_type:
                updated["horario_laboral_tipo"] = work_type
            return updated
        if not updated.get("horario_laboral_text") and has_time_range(clean_text):
            updated["horario_laboral_text"] = clean_text
        return updated

    if ocupacion == "solo_estudio":
        if not updated.get("horario_academico_text"):
            updated["horario_academico_text"] = clean_text
        return updated

    if ocupacion == "ambos":
        if not updated.get("horario_academico_text"):
            updated["horario_academico_text"] = clean_text
            return updated
        if not updated.get("horario_laboral_tipo"):
            work_type = _parse_work_type(clean_text)
            if work_type:
                updated["horario_laboral_tipo"] = work_type
            return updated
        if not updated.get("horario_laboral_text") and has_time_range(clean_text):
            updated["horario_laboral_text"] = clean_text
        return updated

    return updated


def _missing_schedule_inputs(raw_inputs: RawInputs, ocupacion: str | None) -> list[str]:
    missing: list[str] = []
    if ocupacion == "solo_trabajo":
        if not raw_inputs.get("horario_laboral_tipo"):
            missing.append("horario_laboral_tipo")
        elif not raw_inputs.get("horario_laboral_text"):
            missing.append("horario_laboral_text")
        return missing

    if ocupacion == "solo_estudio":
        if not raw_inputs.get("horario_academico_text"):
            missing.append("horario_academico_text")
        return missing

    if ocupacion == "ambos":
        if not raw_inputs.get("horario_academico_text"):
            missing.append("horario_academico_text")
        elif not raw_inputs.get("horario_laboral_tipo"):
            missing.append("horario_laboral_tipo")
        elif not raw_inputs.get("horario_laboral_text"):
            missing.append("horario_laboral_text")
    return missing


def _build_prompt_for_missing(missing: list[str], ocupacion: str | None) -> str:
    if not missing:
        return "Comparte tus horarios en texto."
    first = missing[0]
    if first == "horario_academico_text":
        return PROMPT_ACADEMICO
    if first == "horario_laboral_tipo":
        return PROMPT_LABORAL_TIPO
    if first == "horario_laboral_text":
        return PROMPT_LABORAL

    if ocupacion == "solo_trabajo":
        return PROMPT_LABORAL
    if ocupacion == "solo_estudio":
        return PROMPT_ACADEMICO
    if ocupacion == "ambos":
        return PROMPT_AMBOS
    return "Comparte tus horarios."


def _parse_work_type(text: str) -> str | None:
    normalized = normalize_text(text)
    if normalized in ("1", "1.", "1)", "fijo", "fija", "estable"):
        return "fijo"
    if normalized in ("2", "2.", "2)", "flexible", "variable", "rotativo"):
        return "flexible"
    if normalized.startswith("1"):
        return "fijo"
    if normalized.startswith("2"):
        return "flexible"
    if "fijo" in normalized or "fija" in normalized or "estable" in normalized:
        return "fijo"
    if "flexible" in normalized or "variable" in normalized or "rotativo" in normalized:
        return "flexible"
    return None
