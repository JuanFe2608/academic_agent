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
_EMAIL_CORRECTION_TOKENS = {
    "cambiar correo",
    "corregir correo",
    "editar correo",
    "modificar correo",
    "actualizar correo",
    "me equivoque de correo",
    "me equivoque con el correo",
    "escribi mal el correo",
    "correo incorrecto",
    "correo mal escrito",
    "otro correo",
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
            conflict_update = _identity_conflict_update(
                state=state,
                messages=messages,
                profile=profile,
                onboarding=onboarding,
                interaction=interaction,
                error_code=identity_result.error_code,
                has_new_input=has_new_input,
                current_count=current_count,
                last_text=last_text,
            )
            if conflict_update is not None:
                return conflict_update

            detail = _identity_persistence_error_message(identity_result.error_code)
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
                    detail,
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
        profile["email_verified"] = True
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
    should_correct_email = has_new_input and _is_email_correction_request(last_text)
    user_claims_done = has_new_input and _matches_any(last_text, _COMPLETION_TOKENS)
    pending_url = str(oauth_substate.get("authorization_url") or "").strip()
    pending_is_current = (
        oauth_substate.get("status") == "pending"
        and pending_url
        and not _is_expired(oauth_substate.get("expires_at"))
    )

    if should_correct_email:
        _mark_pending_oauth_failed(
            service=service,
            state_token=oauth_substate.get("state_token"),
            last_error="email_correction_requested",
        )
        profile.pop("institutional_email", None)
        profile["email_verified"] = False
        onboarding["current_field"] = "institutional_email"
        onboarding["profile_stage"] = "collecting"
        onboarding["persistence_error"] = None
        slot_errors = dict(onboarding.get("slot_errors", {}))
        slot_errors.pop("institutional_email", None)
        onboarding["slot_errors"] = slot_errors
        onboarding["microsoft_oauth"] = _oauth_state(
            onboarding,
            status="idle",
            state_token=None,
            authorization_url=None,
            expires_at=None,
            last_error="email_correction_requested",
        )
        interaction["is_waiting_for_oauth"] = False
        interaction["current_step"] = "institutional_email"
        return {
            "student_profile": profile,
            "onboarding": onboarding,
            "interaction": interaction,
            "phase": "profile",
            "user_message_count": current_count,
            "last_user_text": last_text,
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                (
                    "Listo, vamos a corregir el correo Microsoft. "
                    "Escribe el correo correcto, por ejemplo: usuario@outlook.com"
                ),
            ),
        }

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
        profile["email_verified"] = True
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
    """Verifica que el email este ingresado (aun no verificado — la verificacion la hace OAuth)."""
    return bool(
        profile.get("full_name")
        and profile.get("student_code")
        and profile.get("age")
        and profile.get("institutional_email")
    )


def _profile_student_id(profile: dict[str, Any]) -> int | None:
    raw = profile.get("persisted_student_id")
    if raw in (None, ""):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _identity_conflict_update(
    *,
    state: AgentState,
    messages: list,
    profile: dict[str, Any],
    onboarding: dict[str, Any],
    interaction: dict[str, Any],
    error_code: str | None,
    has_new_input: bool,
    current_count: int,
    last_text: str,
) -> dict | None:
    conflict_field = _identity_conflict_field(error_code)
    if conflict_field is None:
        return None

    _clear_conflicting_identity_field(profile, conflict_field)
    slot_errors = dict(onboarding.get("slot_errors", {}))
    slot_errors[conflict_field] = error_code or "identity_conflict"
    onboarding["slot_errors"] = slot_errors
    onboarding["current_field"] = conflict_field
    onboarding["persistence_error"] = error_code or "identity_conflict"
    onboarding["microsoft_oauth"] = _oauth_state(
        onboarding,
        status="idle",
        state_token=None,
        authorization_url=None,
        expires_at=None,
        last_error=error_code or "identity_conflict",
    )
    interaction["is_waiting_for_oauth"] = False
    interaction["current_step"] = conflict_field
    return {
        "student_profile": profile,
        "onboarding": onboarding,
        "interaction": interaction,
        "phase": "profile",
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_text if has_new_input else state.get("last_user_text"),
        "awaiting_user_input": True,
        "messages": append_message(
            messages,
            "assistant",
            _identity_conflict_message(error_code),
        ),
    }


def _identity_conflict_field(error_code: str | None) -> str | None:
    if error_code == "duplicate_student_code":
        return "student_code"
    if error_code == "duplicate_email":
        return "institutional_email"
    return None


def _clear_conflicting_identity_field(profile: dict[str, Any], field: str) -> None:
    profile.pop("persisted_student_id", None)
    if field == "student_code":
        profile.pop("student_code", None)
        profile.pop("supported_program", None)
        profile.pop("academic_program", None)
        return
    if field == "institutional_email":
        profile.pop("institutional_email", None)
        profile["email_verified"] = False


def _identity_conflict_message(error_code: str | None) -> str:
    if error_code == "duplicate_student_code":
        return (
            "Ese codigo estudiantil ya esta registrado en otra cuenta 🆔 "
            "Escribe un codigo diferente 😊"
        )
    if error_code == "duplicate_email":
        return (
            "Ese correo Microsoft ya esta registrado en otra cuenta de estudiante. "
            "Escribe otro correo Microsoft personal 📧 "
            "Puedes usar @outlook.com, @hotmail.com o @live.com. "
            "Por ejemplo: usuario@outlook.com"
        )
    return (
        "No pude conectar Microsoft todavia porque encontre un conflicto en tu identidad academica. "
        "Revisa los datos y escribe el dato correcto para continuar."
    )


def _identity_persistence_error_message(error_code: str | None) -> str:
    if error_code == "missing_identity_fields":
        return (
            "Antes de conectar Microsoft necesito completar tus datos basicos. "
            "Voy a pedirte el dato que falta para poder continuar."
        )
    return (
        "No pude preparar tu identidad academica para conectar Microsoft por un problema interno. "
        "No cambies tus datos todavia; escribe reintentar en unos segundos. Si vuelve a pasar, "
        "hay que revisar el registro en la base de datos."
    )


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
        "📅 Necesito conectar tu cuenta Microsoft conmigo.\n\n"
        "Para ayudarte a organizar tu tiempo y planificar tus actividades academicas, "
        "necesito acceso a tu calendario y tareas (To Do).\n\n"
        "Esto me permitira:\n"
        "🗓️ Crear eventos en tu calendario academico\n"
        "✅ Registrar tareas y recordatorios de estudio\n"
        "⏰ Ayudarte a gestionar mejor tus tiempos y entregas\n\n"
        "🔒 Tu informacion es segura:\n"
        "Solo usare estos permisos para apoyarte en tu planificacion academica.\n\n"
        "Toca el link para iniciar sesion en Microsoft y autorizar el acceso:\n"
        f"🔗 {authorization_url}\n\n"
        "Cuando termines, vuelve aqui y escribe listo ✅. "
        "Si el enlace vence, escribe reintentar 🔃. "
        "Si escribiste mal tu correo, escribe cambiar correo."
    )


def _pending_message(authorization_url: str, *, user_claims_done: bool) -> str:
    if user_claims_done:
        return (
            "Aun no veo la conexion Microsoft confirmada. "
            "Revisa que hayas completado el inicio de sesion en el navegador.\n\n"
            f"🔗 {authorization_url}\n\n"
            "Si ya te aparecio la pantalla de Listo, escribe listo ✅. "
            "Si el enlace vencio o fallo, escribe reintentar 🔃. "
            "Si escribiste mal tu correo, escribe cambiar correo."
        )
    return (
        "Sigo esperando la autorizacion de Microsoft. "
        "Usa este enlace para completar el acceso:\n\n"
        f"🔗 {authorization_url}\n\n"
        "Cuando termines, escribe listo ✅. "
        "Si vencio o fallo, escribe reintentar 🔃. "
        "Si escribiste mal tu correo, escribe cambiar correo."
    )


def _matches_any(raw: str, tokens: set[str]) -> bool:
    normalized = normalize_text(raw or "")
    return normalized in tokens


def _is_email_correction_request(raw: str) -> bool:
    normalized = normalize_text(raw or "")
    return any(token in normalized for token in _EMAIL_CORRECTION_TOKENS)


def _mark_pending_oauth_failed(
    *,
    service: Any,
    state_token: Any,
    last_error: str,
) -> None:
    token = str(state_token or "").strip()
    if not token:
        return
    try:
        service.state_repository.mark_oauth_pending_state_failed(
            state_token=token,
            last_error=last_error,
        )
    except Exception:
        return


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
