"""Nodo que bloquea onboarding hasta completar OAuth Microsoft."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from agents.support.dependencies import (
    get_microsoft_oauth_flow_service,
    get_onboarding_service,
)
from agents.support.nodes.utils import (
    append_message,
    copy_onboarding_state,
    detect_new_input,
    normalize_text,
)
from agents.support.state import AgentState
from services.sync.microsoft_oauth_flow_service import is_microsoft_oauth_required

_RETRY_TOKENS = {
    "reenviar",
    "reintentar",
    "nuevo enlace",
    "generar enlace",
    "enlace vencido",
    "el enlace vencio",
}
_COMPLETION_TOKENS = {
    "listo",
    "ya",
    "ya autorice",
    "ya lo autorice",
    "autorice",
    "autorizado",
    "termine",
}


def request_microsoft_oauth(state: AgentState) -> dict:
    """Solicita OAuth y no permite avanzar hasta que exista conexion."""

    messages = state.get("messages", [])
    profile = dict(state.get("student_profile", {}))
    onboarding = copy_onboarding_state(state)
    interaction = state.interaction_state.model_dump(mode="python")
    has_new_input, last_text, current_count = detect_new_input(
        messages,
        state.get("user_message_count", 0),
        state.get("awaiting_user_input", False),
        state.get("last_user_text"),
    )

    if not is_microsoft_oauth_required():
        onboarding["microsoft_oauth"] = _oauth_state(
            onboarding,
            status="idle",
            state_token=None,
            authorization_url=None,
            expires_at=None,
            last_error=None,
        )
        interaction["is_waiting_for_oauth"] = False
        return {
            "student_profile": profile,
            "onboarding": onboarding,
            "interaction": interaction,
            "phase": "profile",
            "awaiting_user_input": False,
        }

    if not _profile_ready_for_oauth(profile):
        return {
            "student_profile": profile,
            "onboarding": onboarding,
            "phase": "profile",
            "awaiting_user_input": False,
        }

    student_id = _profile_student_id(profile)
    if student_id is None:
        identity_result = get_onboarding_service().persist_verified_identity(profile)
        if identity_result.persisted and identity_result.student_id is not None:
            student_id = int(identity_result.student_id)
            profile["persisted_student_id"] = student_id
        else:
            detail = identity_result.detail or "No pude preparar tu identidad para Microsoft."
            onboarding["microsoft_oauth"] = _oauth_state(
                onboarding,
                status="failed",
                last_error=identity_result.error_code or "identity_persistence_error",
            )
            interaction["is_waiting_for_oauth"] = True
            interaction["current_step"] = "microsoft_oauth"
            return {
                "student_profile": profile,
                "onboarding": onboarding,
                "interaction": interaction,
                "phase": "microsoft_oauth",
                "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
                "last_user_text": last_text if has_new_input else state.get("last_user_text"),
                "awaiting_user_input": True,
                "messages": append_message(
                    messages,
                    "assistant",
                    (
                        "Antes de conectar Microsoft necesito dejar lista tu identidad academica. "
                        f"{detail} Escribe reintentar cuando este corregido."
                    ),
                ),
            }

    try:
        service = get_microsoft_oauth_flow_service()
    except Exception as exc:  # pragma: no cover - depende de configuracion runtime
        onboarding["microsoft_oauth"] = _oauth_state(
            onboarding,
            status="failed",
            last_error="microsoft_oauth_service_unavailable",
        )
        interaction["is_waiting_for_oauth"] = True
        interaction["current_step"] = "microsoft_oauth"
        return {
            "student_profile": profile,
            "onboarding": onboarding,
            "interaction": interaction,
            "phase": "microsoft_oauth",
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_text if has_new_input else state.get("last_user_text"),
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                (
                    "No pude preparar la conexion con Microsoft en este entorno. "
                    f"Detalle tecnico: {exc}. Escribe reintentar cuando este configurado."
                ),
            ),
        }
    if service.has_connection(student_id=student_id):
        onboarding["microsoft_oauth"] = _oauth_state(
            onboarding,
            status="authorized",
            state_token=None,
            authorization_url=None,
            expires_at=None,
            last_error=None,
        )
        interaction["is_waiting_for_oauth"] = False
        interaction["current_step"] = None
        calendar = dict(state.get("calendar", {}))
        calendar.update({"provider": "outlook", "authorized": True})
        return {
            "student_profile": profile,
            "onboarding": onboarding,
            "interaction": interaction,
            "calendar": calendar,
            "phase": "profile",
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_text if has_new_input else state.get("last_user_text"),
            "awaiting_user_input": False,
        }

    oauth_substate = dict(onboarding.get("microsoft_oauth", {}))
    should_retry = has_new_input and _matches_any(last_text, _RETRY_TOKENS)
    user_claims_done = has_new_input and _matches_any(last_text, _COMPLETION_TOKENS)
    pending_url = str(oauth_substate.get("authorization_url") or "").strip()
    pending_is_current = (
        oauth_substate.get("status") == "pending"
        and pending_url
        and not _is_expired(oauth_substate.get("expires_at"))
    )

    if pending_is_current and not should_retry:
        interaction["is_waiting_for_oauth"] = True
        interaction["current_step"] = "microsoft_oauth"
        message = _pending_message(pending_url, user_claims_done=user_claims_done)
        update = {
            "student_profile": profile,
            "onboarding": onboarding,
            "interaction": interaction,
            "phase": "microsoft_oauth",
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_text if has_new_input else state.get("last_user_text"),
            "awaiting_user_input": True,
        }
        if has_new_input:
            update["messages"] = append_message(messages, "assistant", message)
        return update

    try:
        result = service.start_authorization(
            student_id=student_id,
            institutional_email=profile.get("institutional_email"),
        )
    except Exception as exc:  # pragma: no cover - depende de repositorio/entorno real
        onboarding["microsoft_oauth"] = _oauth_state(
            onboarding,
            status="failed",
            last_error="microsoft_oauth_start_error",
            increment_attempts=True,
        )
        interaction["is_waiting_for_oauth"] = True
        interaction["current_step"] = "microsoft_oauth"
        return {
            "student_profile": profile,
            "onboarding": onboarding,
            "interaction": interaction,
            "phase": "microsoft_oauth",
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_text if has_new_input else state.get("last_user_text"),
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                (
                    "No pude generar el enlace de Microsoft en este momento. "
                    f"Detalle tecnico: {exc}. Escribe reintentar."
                ),
            ),
        }
    if result.already_authorized:
        onboarding["microsoft_oauth"] = _oauth_state(
            onboarding,
            status="authorized",
            state_token=None,
            authorization_url=None,
            expires_at=None,
            last_error=None,
        )
        interaction["is_waiting_for_oauth"] = False
        interaction["current_step"] = None
        return {
            "student_profile": profile,
            "onboarding": onboarding,
            "interaction": interaction,
            "phase": "profile",
            "awaiting_user_input": False,
        }

    if not result.ok:
        onboarding["microsoft_oauth"] = _oauth_state(
            onboarding,
            status="failed",
            last_error=result.error_code or "microsoft_oauth_error",
            increment_attempts=True,
        )
        interaction["is_waiting_for_oauth"] = True
        interaction["current_step"] = "microsoft_oauth"
        detail = result.detail or "No pude generar el enlace de Microsoft."
        return {
            "student_profile": profile,
            "onboarding": onboarding,
            "interaction": interaction,
            "phase": "microsoft_oauth",
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_text if has_new_input else state.get("last_user_text"),
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                f"{detail} Escribe reintentar cuando la configuracion este lista.",
            ),
        }

    onboarding["microsoft_oauth"] = _oauth_state(
        onboarding,
        status="pending",
        state_token=result.state_token,
        authorization_url=result.authorization_url,
        expires_at=result.expires_at.isoformat() if result.expires_at else None,
        last_error=None,
        increment_attempts=True,
    )
    interaction["is_waiting_for_oauth"] = True
    interaction["current_step"] = "microsoft_oauth"
    return {
        "student_profile": profile,
        "onboarding": onboarding,
        "interaction": interaction,
        "phase": "microsoft_oauth",
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_text if has_new_input else state.get("last_user_text"),
        "awaiting_user_input": True,
        "messages": append_message(
            messages,
            "assistant",
            _authorization_message(str(result.authorization_url or "")),
        ),
    }


def _profile_ready_for_oauth(profile: dict[str, Any]) -> bool:
    return bool(
        profile.get("full_name")
        and profile.get("student_code")
        and profile.get("age")
        and profile.get("institutional_email")
        and profile.get("email_verified")
    )


def _profile_student_id(profile: dict[str, Any]) -> int | None:
    raw = profile.get("persisted_student_id")
    if raw in (None, ""):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _oauth_state(
    onboarding: dict[str, Any],
    *,
    status: str,
    state_token: str | None = None,
    authorization_url: str | None = None,
    expires_at: str | None = None,
    last_error: str | None = None,
    increment_attempts: bool = False,
) -> dict[str, Any]:
    current = dict(onboarding.get("microsoft_oauth", {}))
    attempts = int(current.get("attempts") or 0)
    if increment_attempts:
        attempts += 1
    return {
        "status": status,
        "state_token": state_token,
        "authorization_url": authorization_url,
        "expires_at": expires_at,
        "attempts": attempts,
        "last_error": last_error,
    }


def _authorization_message(authorization_url: str) -> str:
    return (
        "Para sincronizar tu calendario y recordatorios necesito que autorices "
        "el acceso con Microsoft.\n"
        f"Abre este enlace seguro y completa el inicio de sesion:\n{authorization_url}\n"
        "Cuando termines, vuelve aqui y escribe listo. Si el enlace vence, escribe reintentar."
    )


def _pending_message(authorization_url: str, *, user_claims_done: bool) -> str:
    if user_claims_done:
        return (
            "Aun no veo la conexion Microsoft confirmada. Revisa si terminaste "
            "la autorizacion en el navegador.\n"
            f"Puedes usar este enlace:\n{authorization_url}\n"
            "Si vencio o fallo, escribe reintentar."
        )
    return (
        "Sigo esperando la autorizacion de Microsoft.\n"
        f"Usa este enlace:\n{authorization_url}\n"
        "Cuando termines, escribe listo. Si vencio o fallo, escribe reintentar."
    )


def _matches_any(raw: str, tokens: set[str]) -> bool:
    normalized = normalize_text(raw or "")
    return normalized in tokens


def _is_expired(raw_expires_at: Any) -> bool:
    if not raw_expires_at:
        return False
    try:
        expires_at = datetime.fromisoformat(str(raw_expires_at))
    except ValueError:
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= datetime.now(timezone.utc)
