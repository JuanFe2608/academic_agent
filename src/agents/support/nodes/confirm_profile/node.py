"""Nodo para confirmar la informacion del perfil."""

from __future__ import annotations

from agents.support.nodes.utils import (
    append_message,
    detect_new_input,
    normalize_text,
    parse_yes_no,
)
from agents.support.state import AgentState
from agents.support.nodes.collect_profile.prompt import PROMPTS_BY_FIELD

from .prompt import PROMPT_FIELD

_FIELD_ALIASES = {
    "nombre": "nombre",
    "edad": "edad",
    "correo": "correo",
    "email": "correo",
    "mail": "correo",
    "codigo": "codigo",
    "código": "codigo",
    "semestre": "semestre",
    "promedio": "promedio",
    "ocupacion": "ocupacion",
    "ocupación": "ocupacion",
}


def confirm_profile(state: AgentState) -> dict:
    """Muestra resumen del perfil y solicita confirmacion."""
    messages = state.get("messages", [])
    has_new_input, last_text, current_count = detect_new_input(
        messages,
        state.get("user_message_count", 0),
        state.get("awaiting_user_input", False),
        state.get("last_user_text"),
    )
    profile = dict(state.get("student_profile", {}))
    edit_target = state.get("profile_edit_target")

    if not has_new_input:
        if edit_target:
            return {
                "phase": "profile_confirm",
                "awaiting_user_input": True,
                "messages": append_message(messages, "assistant", PROMPT_FIELD),
            }
        prompt = _build_confirm_prompt(profile)
        return {
            "phase": "profile_confirm",
            "awaiting_user_input": True,
            "messages": append_message(messages, "assistant", prompt),
        }

    last_text = last_text or ""
    normalized = normalize_text(last_text)
    answer = parse_yes_no(last_text)

    if edit_target:
        field = _extract_field(normalized)
        if not field:
            return {
                "phase": "profile_confirm",
                "user_message_count": current_count,
                "last_user_text": last_text,
                "awaiting_user_input": True,
                "messages": append_message(messages, "assistant", PROMPT_FIELD),
            }
        profile[field] = None
        prompt = _prompt_for_field(field, is_edit=True)
        return {
            "student_profile": profile,
            "profile_edit_target": None,
            "phase": "profile",
            "user_message_count": current_count,
            "last_user_text": last_text,
            "awaiting_user_input": True,
            "messages": append_message(messages, "assistant", prompt),
        }

    if answer is True:
        return {
            "phase": "schedules",
            "user_message_count": current_count,
            "last_user_text": last_text,
            "awaiting_user_input": False,
            "messages": append_message(
                messages, "assistant", "Gracias. Ahora necesito tus horarios."
            ),
        }

    if answer is False:
        field = _extract_field(normalized)
        if field:
            profile[field] = None
            prompt = _prompt_for_field(field, is_edit=True)
            return {
                "student_profile": profile,
                "profile_edit_target": None,
                "phase": "profile",
                "user_message_count": current_count,
                "last_user_text": last_text,
                "awaiting_user_input": True,
                "messages": append_message(messages, "assistant", prompt),
            }
        return {
            "profile_edit_target": "awaiting_field",
            "phase": "profile_confirm",
            "user_message_count": current_count,
            "last_user_text": last_text,
            "awaiting_user_input": True,
            "messages": append_message(messages, "assistant", PROMPT_FIELD),
        }

    return {
        "phase": "profile_confirm",
        "user_message_count": current_count,
        "last_user_text": last_text,
        "awaiting_user_input": True,
        "messages": append_message(messages, "assistant", _build_confirm_prompt(profile)),
    }


def _build_confirm_prompt(profile: dict) -> str:
    ocupacion = _format_ocupacion(profile.get("ocupacion"))
    lines = [
        "Verifica tu informacion:",
        f"Nombre: {_display_value(profile.get('nombre'))}",
        f"Edad: {_display_value(profile.get('edad'))}",
        f"Correo: {_display_value(profile.get('correo'))}",
        f"Codigo: {_display_value(profile.get('codigo'))}",
        f"Semestre: {_display_value(profile.get('semestre'))}",
        f"Promedio: {_display_value(profile.get('promedio'))}",
        f"Ocupacion: {ocupacion}",
        "\n¿Es correcta? Responde si o no.",
    ]
    return "\n".join(lines)


def _format_ocupacion(value: str | None) -> str:
    mapping = {
        "solo_estudio": "Solo estudio",
        "solo_trabajo": "Solo trabajo",
        "ambos": "Estudio y trabajo",
        "ninguna": "Ninguna",
    }
    return mapping.get(value or "", "Pendiente")


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
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        if "text" in value:
            return str(value.get("text")).strip()
        if "content" in value:
            return str(value.get("content")).strip()
        return str(value)
    if isinstance(value, (list, tuple)):
        parts = []
        for item in value:
            if isinstance(item, str):
                parts.append(item.strip())
            elif isinstance(item, dict):
                if "text" in item:
                    parts.append(str(item.get("text")).strip())
                elif "content" in item:
                    parts.append(str(item.get("content")).strip())
        combined = " ".join(part for part in parts if part)
        return combined if combined else "Pendiente"
    return str(value)


def _prompt_for_field(field: str, is_edit: bool = False) -> str:
    prompt = PROMPTS_BY_FIELD.get(field, "¿Cuál es el dato correcto?")
    if not is_edit:
        return prompt
    if field == "nombre":
        return prompt.replace("Empecemos. ", "").replace("Empecemos ", "")
    return prompt
