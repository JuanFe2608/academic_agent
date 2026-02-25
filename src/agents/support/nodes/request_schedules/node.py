"""Nodo para solicitar horarios crudos segun ocupacion."""

from __future__ import annotations

from agents.support.nodes.utils import (
    append_message,
    detect_new_input,
    get_last_user_images,
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
    images = get_last_user_images(messages) if has_new_input else []
    raw_inputs = dict(state.get("raw_inputs", {}))
    ocupacion = state.get("student_profile", {}).get("ocupacion")

    if ocupacion == "ninguna":
        return {
            "phase": "end",
            "messages": append_message(messages, "assistant", PROMPT_NINGUNA),
        }

    if _needs_work_type(ocupacion, raw_inputs):
        if has_new_input and last_text:
            work_type = _parse_work_type(last_text)
            if work_type:
                raw_inputs["horario_laboral_tipo"] = work_type
            else:
                return {
                    "raw_inputs": raw_inputs,
                    "phase": "schedules",
                    "user_message_count": current_count
                    if has_new_input
                    else state.get("user_message_count", 0),
                    "last_user_text": last_text if has_new_input else state.get("last_user_text"),
                    "awaiting_user_input": True,
                    "messages": append_message(messages, "assistant", PROMPT_LABORAL_TIPO),
                }
        if _needs_work_type(ocupacion, raw_inputs):
            return {
                "raw_inputs": raw_inputs,
                "phase": "schedules",
                "user_message_count": current_count
                if has_new_input
                else state.get("user_message_count", 0),
                "last_user_text": last_text if has_new_input else state.get("last_user_text"),
                "awaiting_user_input": True,
                "messages": append_message(messages, "assistant", PROMPT_LABORAL_TIPO),
            }

    if has_new_input and last_text:
        raw_inputs = _apply_schedule_text(raw_inputs, last_text, ocupacion)
    if has_new_input and images:
        raw_inputs = _apply_schedule_image(raw_inputs, images, ocupacion, last_text)

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


def _apply_schedule_text(raw_inputs: RawInputs, text: str, ocupacion: str | None) -> RawInputs:
    """Guarda el texto recibido en el campo adecuado."""
    updated = dict(raw_inputs)
    normalized = normalize_text(text)

    if ocupacion == "solo_trabajo":
        if not updated.get("horario_laboral_text") and has_time_range(text):
            updated["horario_laboral_text"] = text.strip()
        return updated

    if ocupacion == "solo_estudio":
        if not updated.get("horario_academico_text"):
            updated["horario_academico_text"] = text.strip()
        return updated

    if ocupacion == "ambos":
        if _looks_like_academic_schedule(normalized):
            if not updated.get("horario_academico_text"):
                updated["horario_academico_text"] = text.strip()
        elif "trabajo" in normalized or "laboral" in normalized:
            if not updated.get("horario_laboral_text") and has_time_range(text):
                updated["horario_laboral_text"] = text.strip()
        elif "academico" in normalized or "clase" in normalized:
            if not updated.get("horario_academico_text"):
                updated["horario_academico_text"] = text.strip()
        elif has_time_range(text):
            if not updated.get("horario_laboral_text"):
                updated["horario_laboral_text"] = text.strip()
            elif not updated.get("horario_academico_text"):
                updated["horario_academico_text"] = text.strip()
        return updated

    return updated


def _missing_schedule_inputs(raw_inputs: RawInputs, ocupacion: str | None) -> list[str]:
    missing: list[str] = []
    if ocupacion in ("solo_trabajo", "ambos"):
        if not raw_inputs.get("horario_laboral_text") and not raw_inputs.get(
            "horario_laboral_img"
        ):
            missing.append("horario_laboral_text")
    if ocupacion in ("solo_estudio", "ambos"):
        if not raw_inputs.get("horario_academico_text") and not raw_inputs.get(
            "horario_academico_img"
        ):
            missing.append("horario_academico_text")
    return missing


def _build_prompt_for_missing(missing: list[str], ocupacion: str | None) -> str:
    if ocupacion == "solo_trabajo":
        return PROMPT_LABORAL
    if ocupacion == "solo_estudio":
        return PROMPT_ACADEMICO
    if ocupacion == "ambos":
        return PROMPT_AMBOS
    return "Comparte tus horarios."


def _apply_schedule_image(
    raw_inputs: RawInputs, images: list[str], ocupacion: str | None, text: str
) -> RawInputs:
    updated = dict(raw_inputs)
    if not images:
        return updated
    normalized = normalize_text(text or "")

    image_ref = images[0]
    if ocupacion == "solo_trabajo":
        if not updated.get("horario_laboral_img"):
            updated["horario_laboral_img"] = image_ref
        return updated

    if ocupacion == "solo_estudio":
        if not updated.get("horario_academico_img"):
            updated["horario_academico_img"] = image_ref
        return updated

    if ocupacion == "ambos":
        if "trabajo" in normalized or "laboral" in normalized:
            if not updated.get("horario_laboral_img"):
                updated["horario_laboral_img"] = image_ref
        elif "academico" in normalized or "clase" in normalized:
            if not updated.get("horario_academico_img"):
                updated["horario_academico_img"] = image_ref
        else:
            if not updated.get("horario_academico_img"):
                updated["horario_academico_img"] = image_ref
            elif not updated.get("horario_laboral_img"):
                updated["horario_laboral_img"] = image_ref
        return updated

    return updated


def _looks_like_academic_schedule(text: str) -> bool:
    markers = (
        "codigo asignatura",
        "periodo academico",
        "asignatura",
        "creditos",
        "grupo",
    )
    return any(marker in text for marker in markers)


def _needs_work_type(ocupacion: str | None, raw_inputs: RawInputs) -> bool:
    if ocupacion not in ("solo_trabajo", "ambos"):
        return False
    return not raw_inputs.get("horario_laboral_tipo")


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
