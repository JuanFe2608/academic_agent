"""Nodo para confirmar la informacion del perfil."""

from __future__ import annotations

from agents.support.nodes.utils import (
    append_message,
    copy_onboarding_state,
    detect_new_input,
)
from agents.support.onboarding.messages import build_field_prompt
from agents.support.onboarding.validators import normalize_text, parse_yes_no
from agents.support.state import AgentState
from services.onboarding import load_onboarding_config

from .prompt import PROMPT_FIELD

_FIELD_ALIASES = {
    "nombre": "full_name",
    "nombre completo": "full_name",
    "codigo": "student_code",
    "codigo estudiantil": "student_code",
    "edad": "age",
    "semestre": "semester",
    "promedio": "average_grade",
}


def confirm_profile(state: AgentState) -> dict:
    """Muestra resumen del perfil y solicita confirmacion final."""

    config = load_onboarding_config()
    messages = state.get("messages", [])
    has_new_input, last_text, current_count = detect_new_input(
        messages,
        state.get("user_message_count", 0),
        state.get("awaiting_user_input", False),
        state.get("last_user_text"),
    )
    profile = dict(state.get("student_profile", {}))
    onboarding = copy_onboarding_state(state)
    edit_target = state.get("profile_edit_target")

    if not has_new_input:
        prompt = PROMPT_FIELD if edit_target else _build_confirm_prompt(profile)
        onboarding["profile_stage"] = "confirming"
        return {
            "onboarding": onboarding,
            "phase": "profile",
            "awaiting_user_input": True,
            "messages": append_message(messages, "assistant", prompt),
        }

    last_text = last_text or ""
    normalized = normalize_text(last_text)
    answer = parse_yes_no(last_text)

    if edit_target:
        field = _extract_field(normalized)
        if not field:
            onboarding["profile_stage"] = "confirming"
            return {
                "onboarding": onboarding,
                "phase": "profile",
                "user_message_count": current_count,
                "last_user_text": last_text,
                "awaiting_user_input": True,
                "messages": append_message(messages, "assistant", PROMPT_FIELD),
            }
        _reset_profile_field(profile, onboarding, field)
        onboarding["profile_stage"] = "collecting"
        return {
            "student_profile": profile,
            "onboarding": onboarding,
            "profile_edit_target": None,
            "phase": "profile",
            "user_message_count": current_count,
            "last_user_text": last_text,
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                _prompt_for_field(field, config),
            ),
        }

    if answer is True:
        onboarding["profile_stage"] = "persisting"
        return {
            "onboarding": onboarding,
            "phase": "profile",
            "user_message_count": current_count,
            "last_user_text": last_text,
            "awaiting_user_input": False,
        }

    if answer is False:
        field = _extract_field(normalized)
        if field:
            _reset_profile_field(profile, onboarding, field)
            onboarding["profile_stage"] = "collecting"
            return {
                "student_profile": profile,
                "onboarding": onboarding,
                "profile_edit_target": None,
                "phase": "profile",
                "user_message_count": current_count,
                "last_user_text": last_text,
                "awaiting_user_input": True,
                "messages": append_message(
                    messages,
                    "assistant",
                    _prompt_for_field(field, config),
                ),
            }
        onboarding["profile_stage"] = "confirming"
        return {
            "profile_edit_target": "awaiting_field",
            "onboarding": onboarding,
            "phase": "profile",
            "user_message_count": current_count,
            "last_user_text": last_text,
            "awaiting_user_input": True,
            "messages": append_message(messages, "assistant", PROMPT_FIELD),
        }

    onboarding["profile_stage"] = "confirming"
    return {
        "onboarding": onboarding,
        "phase": "profile",
        "user_message_count": current_count,
        "last_user_text": last_text,
        "awaiting_user_input": True,
        "messages": append_message(
            messages,
            "assistant",
            _build_confirm_prompt(profile),
        ),
    }


def _build_confirm_prompt(profile: dict) -> str:
    program = profile.get("academic_program") or "Pendiente"
    lines = [
        "Verifica tu informacion:",
        f"Nombre: {_display_value(profile.get('full_name'))}",
        f"Codigo estudiantil: {_display_value(profile.get('student_code'))}",
        f"Edad: {_display_value(profile.get('age'))}",
        f"Programa: {program}",
        f"Semestre: {_display_value(profile.get('semester'))}",
        f"Promedio acumulado: {_display_value(profile.get('average_grade'))}",
        "\n¿Es correcta? Responde si o no.",
    ]
    return "\n".join(lines)


def _extract_field(text: str) -> str | None:
    for key, field in _FIELD_ALIASES.items():
        if key in text:
            return field
    return None


def _display_value(value: object) -> str:
    if value is None:
        return "Pendiente"
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned if cleaned else "Pendiente"
    if isinstance(value, (int, float, bool)):
        return str(value)
    return str(value)


def _reset_profile_field(profile: dict, onboarding: dict, field: str) -> None:
    if field == "supported_program":
        profile["supported_program"] = None
        profile["academic_program"] = None
        return

    profile[field] = None
    if field == "institutional_email":
        profile["email_verified"] = False


def _prompt_for_field(field: str, config) -> str:
    prompt = build_field_prompt(field, config)
    if field != "full_name":
        return prompt
    return (
        "¿Como te llamas? Puedes escribirme tu nombre y apellido, por ejemplo: "
        "Juan Perez"
    )
