"""Nodo para persistir el perfil confirmado del estudiante."""

from __future__ import annotations

from types import SimpleNamespace

from agents.support.dependencies import get_onboarding_service
from agents.support.nodes.utils import append_message, copy_onboarding_state
from agents.support.onboarding.messages import build_field_prompt
from agents.support.state import AgentState
from services.onboarding import load_onboarding_config


def persist_profile(state: AgentState) -> dict:
    """Guarda el perfil validado en la base de datos."""

    messages = state.get("messages", [])
    profile = dict(state.get("student_profile", {}))
    onboarding = copy_onboarding_state(state)
    config = load_onboarding_config()

    try:
        result = get_onboarding_service().persist_student(profile)
    except Exception as exc:  # pragma: no cover - ruta defensiva
        result = SimpleNamespace(
            persisted=False,
            error_code="persistence_error",
            detail=str(exc),
        )
    if result.persisted:
        profile["persisted_student_id"] = result.student_id
        onboarding["persistence_error"] = None
        return {
            "student_profile": profile,
            "onboarding": onboarding,
            "phase": "schedules",
            "awaiting_user_input": False,
        }

    onboarding["persistence_error"] = result.error_code

    if result.error_code == "duplicate_email":
        profile["institutional_email"] = None
        profile["email_verified"] = False
        onboarding["email_verification"] = {
            "status": "idle",
            "attempts": 0,
            "resend_count": 0,
            "expires_at": None,
            "last_error": "duplicate_email",
        }
        prompt = (
            "Ese correo institucional ya esta registrado, asi que necesito uno distinto.\n"
            f"{build_field_prompt('institutional_email', config)}"
        )
        return {
            "student_profile": profile,
            "onboarding": onboarding,
            "phase": "profile",
            "awaiting_user_input": True,
            "messages": append_message(messages, "assistant", prompt),
        }

    if result.error_code == "duplicate_student_code":
        profile["student_code"] = None
        prompt = (
            "Ese codigo estudiantil ya esta registrado en el sistema.\n"
            f"{build_field_prompt('student_code', config)}"
        )
        return {
            "student_profile": profile,
            "onboarding": onboarding,
            "phase": "profile",
            "awaiting_user_input": True,
            "messages": append_message(messages, "assistant", prompt),
        }

    if result.error_code == "email_not_verified":
        return {
            "student_profile": profile,
            "onboarding": onboarding,
            "phase": "email_verification",
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                result.detail or "Aun necesito verificar tu correo institucional.",
            ),
        }

    return {
        "student_profile": profile,
        "onboarding": onboarding,
        "phase": "profile_confirm",
        "awaiting_user_input": True,
        "messages": append_message(
            messages,
            "assistant",
            (
                "No pude guardar tu informacion en este momento. "
                "Tu perfil sigue en memoria, pero la persistencia necesita revision.\n"
                f"Detalle: {result.detail or 'sin detalle'}"
            ),
        ),
    }
