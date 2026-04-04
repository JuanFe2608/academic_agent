"""Nodo para validar el codigo de verificacion del correo."""

from __future__ import annotations

from bootstrap.errors import RepositoryConfigurationError

from agents.support.dependencies import get_onboarding_service
from agents.support.nodes.utils import (
    append_message,
    copy_onboarding_state,
    detect_new_input,
)
from agents.support.onboarding.messages import (
    build_verification_error_prompt,
    build_verification_prompt,
)
from agents.support.onboarding.validators import normalize_text, validate_verification_code
from agents.support.state import AgentState
from services.onboarding import OnboardingRepositoryError
from services.onboarding import load_onboarding_config

_RESEND_TOKENS = {
    "reenviar",
    "reenviar codigo",
    "reenviar codigo de verificacion",
    "enviar de nuevo",
    "nuevo codigo",
}


def verify_email_code(state: AgentState) -> dict:
    """Verifica el codigo o permite reenviarlo."""

    messages = state.get("messages", [])
    has_new_input, last_text, current_count = detect_new_input(
        messages,
        state.get("user_message_count", 0),
        state.get("awaiting_user_input", False),
        state.get("last_user_text"),
    )
    profile = dict(state.get("student_profile", {}))
    onboarding = copy_onboarding_state(state)
    institutional_email = str(profile.get("institutional_email") or "").strip().lower()
    config = load_onboarding_config()

    if not institutional_email:
        return {
            "student_profile": profile,
            "onboarding": onboarding,
            "phase": "profile",
            "awaiting_user_input": False,
        }

    if not has_new_input:
        return {
            "student_profile": profile,
            "onboarding": onboarding,
            "phase": "email_verification",
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                build_verification_prompt(config),
            ),
        }

    submitted_text = last_text or ""
    if _is_resend_request(submitted_text):
        return {
            "student_profile": profile,
            "onboarding": onboarding,
            "phase": "email_verification_send",
            "user_message_count": current_count,
            "last_user_text": submitted_text,
            "awaiting_user_input": False,
        }

    format_result = validate_verification_code(submitted_text, config)
    if not format_result.is_valid:
        onboarding["email_verification"]["last_error"] = "invalid_format"
        return {
            "student_profile": profile,
            "onboarding": onboarding,
            "phase": "email_verification",
            "user_message_count": current_count,
            "last_user_text": submitted_text,
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                build_verification_error_prompt(config),
            ),
        }

    try:
        service = get_onboarding_service()
        result = service.verify_email_code(institutional_email, format_result.value)
    except (OnboardingRepositoryError, RepositoryConfigurationError) as exc:
        detail = (
            "No pude validar el codigo en este entorno. "
            f"Detalle tecnico: {exc}"
        )
        onboarding["email_verification"]["last_error"] = detail
        return {
            "student_profile": profile,
            "onboarding": onboarding,
            "phase": "email_verification",
            "user_message_count": current_count,
            "last_user_text": submitted_text,
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                build_verification_error_prompt(config, detail),
            ),
        }

    onboarding["email_verification"] = {
        "status": "verified" if result.verified else "sent",
        "attempts": result.attempts,
        "resend_count": onboarding["email_verification"].get("resend_count", 0),
        "expires_at": result.expires_at.isoformat() if result.expires_at else None,
        "last_error": result.error_code,
    }

    if result.verified:
        profile["email_verified"] = True
        return {
            "student_profile": profile,
            "onboarding": onboarding,
            "phase": "profile",
            "user_message_count": current_count,
            "last_user_text": submitted_text,
            "awaiting_user_input": False,
        }

    detail = _verification_detail(result.error_code, result.attempts, result.max_attempts)
    return {
        "student_profile": profile,
        "onboarding": onboarding,
        "phase": "email_verification",
        "user_message_count": current_count,
        "last_user_text": submitted_text,
        "awaiting_user_input": True,
        "messages": append_message(
            messages,
            "assistant",
            build_verification_error_prompt(config, detail),
        ),
    }


def _verification_detail(
    error_code: str | None,
    attempts: int,
    max_attempts: int,
) -> str:
    if error_code == "expired":
        return "El codigo ya vencio. Escribe reenviar para recibir uno nuevo."
    if error_code == "challenge_not_found":
        return "No encontre un codigo activo para ese correo. Escribe reenviar."
    if error_code == "max_attempts_exceeded":
        return (
            "Ya alcanzaste el maximo de intentos permitidos. "
            "Escribe reenviar para generar un codigo nuevo."
        )
    if error_code == "invalid_code" and max_attempts > 0:
        remaining = max(max_attempts - attempts, 0)
        return f"Te quedan {remaining} intento(s) antes de bloquear este codigo."
    return None


def _is_resend_request(raw: str) -> bool:
    normalized = normalize_text(raw)
    return normalized in _RESEND_TOKENS
