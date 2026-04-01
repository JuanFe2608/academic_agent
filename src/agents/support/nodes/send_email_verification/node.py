"""Nodo para generar y enviar el codigo de verificacion al correo."""

from __future__ import annotations

from agents.support.nodes.utils import append_message, copy_onboarding_state
from agents.support.onboarding.config import load_onboarding_config
from agents.support.onboarding.messages import (
    build_field_prompt,
    build_verification_prompt,
    build_verification_sent_prompt,
)
from agents.support.onboarding.repository import (
    OnboardingRepositoryError,
    RepositoryConfigurationError,
)
from agents.support.state import AgentState
from agents.support.tools.db import get_onboarding_service


def send_email_verification(state: AgentState) -> dict:
    """Envia el codigo de verificacion y deja el flujo listo para recibirlo."""

    messages = state.get("messages", [])
    profile = dict(state.get("student_profile", {}))
    onboarding = copy_onboarding_state(state)
    institutional_email = str(profile.get("institutional_email") or "").strip().lower()

    if not institutional_email:
        return {
            "phase": "profile",
            "student_profile": profile,
            "onboarding": onboarding,
            "awaiting_user_input": False,
        }

    try:
        service = get_onboarding_service()
        result = service.send_email_verification(institutional_email)
    except (OnboardingRepositoryError, RepositoryConfigurationError) as exc:
        detail = (
            "No pude preparar la verificacion de correo en este entorno. "
            f"Detalle tecnico: {exc}"
        )
        config = load_onboarding_config()
        onboarding["email_verification"] = {
            "status": "idle",
            "attempts": 0,
            "resend_count": 0,
            "expires_at": None,
            "last_error": detail,
        }
        return {
            "student_profile": profile,
            "onboarding": onboarding,
            "phase": "email_verification",
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                f"{detail}\n{build_verification_prompt(config)}",
            ),
        }

    if not result.sent and result.error_code == "duplicate_email":
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
            "Ese correo institucional ya esta registrado en el sistema.\n"
            f"{build_field_prompt('institutional_email', service.config)}"
        )
        return {
            "student_profile": profile,
            "onboarding": onboarding,
            "phase": "profile",
            "awaiting_user_input": True,
            "messages": append_message(messages, "assistant", prompt),
        }

    if result.error_code == "verification_disabled":
        profile["email_verified"] = True
        onboarding["email_verification"] = {
            "status": "verified",
            "attempts": 0,
            "resend_count": 0,
            "expires_at": None,
            "last_error": None,
        }
        return {
            "student_profile": profile,
            "onboarding": onboarding,
            "phase": "profile",
            "awaiting_user_input": False,
            "messages": append_message(
                messages,
                "assistant",
                "Modo desarrollo activo: omiti la verificacion del correo para que puedas continuar.",
            ),
        }

    if result.error_code == "fixed_code":
        onboarding["email_verification"] = {
            "status": "sent",
            "attempts": result.attempts,
            "resend_count": result.resend_count,
            "expires_at": result.expires_at.isoformat() if result.expires_at else None,
            "last_error": None,
        }
        debug_note = (
            "Modo desarrollo activo. "
            f"Usa este codigo fijo para continuar: {result.debug_code}"
        )
        return {
            "student_profile": profile,
            "onboarding": onboarding,
            "phase": "email_verification",
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                f"{build_verification_sent_prompt(service.config)}\n{debug_note}",
            ),
        }

    if not result.sent:
        detail = (
            "No pude enviar el codigo al correo en este entorno. "
            "Puedes escribir reenviar cuando el servicio de correo este disponible."
        )
        onboarding["email_verification"] = {
            "status": "idle",
            "attempts": 0,
            "resend_count": 0,
            "expires_at": None,
            "last_error": result.error_code,
        }
        return {
            "student_profile": profile,
            "onboarding": onboarding,
            "phase": "email_verification",
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                f"{detail}\n{build_verification_prompt(service.config)}",
            ),
        }

    onboarding["email_verification"] = {
        "status": "sent",
        "attempts": result.attempts,
        "resend_count": result.resend_count,
        "expires_at": result.expires_at.isoformat() if result.expires_at else None,
        "last_error": None,
    }
    return {
        "student_profile": profile,
        "onboarding": onboarding,
        "phase": "email_verification",
        "awaiting_user_input": True,
        "messages": append_message(
            messages,
            "assistant",
            build_verification_sent_prompt(service.config),
        ),
    }
