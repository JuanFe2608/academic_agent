"""Flujo confirmable para sincronizar sesiones de estudio con Outlook."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from agents.support.dependencies import (
    get_outlook_calendar_sync_service,
    get_study_plan_materialization_service,
)
from agents.support.nodes.utils import append_message, detect_new_input, parse_yes_no
from agents.support.state import AgentState
from bootstrap.errors import RepositoryConfigurationError
from services.conversation.state_helpers import ensure_interaction_state, update_interaction_state
from services.planning import ensure_study_plan_state, update_study_plan_state
from services.sync import OutlookCalendarSyncPreviewResult, OutlookCalendarSyncResult

_CALENDAR_SYNC_DOMAIN = "calendar_sync"


def sync_study_calendar_turn(state: AgentState) -> dict:
    """Previsualiza y aplica sync de sesiones materializadas hacia Outlook."""

    messages = state.get("messages", [])
    has_new_input, last_text, current_count = detect_new_input(
        messages,
        state.get("user_message_count", 0),
        state.get("awaiting_user_input", False),
        state.get("last_user_text"),
    )
    interaction = ensure_interaction_state(state)
    confirmation_payload = dict(interaction.last_confirmation_payload or {})

    if interaction.confirmation_pending and confirmation_payload.get("domain") == _CALENDAR_SYNC_DOMAIN:
        if not has_new_input:
            return {
                "phase": "running",
                "awaiting_user_input": True,
            }
        return _handle_confirmation(
            state,
            last_text=last_text,
            current_count=current_count,
        )

    return _preview_and_prompt(
        state,
        last_text=last_text,
        current_count=current_count,
        has_new_input=has_new_input,
    )


def _preview_and_prompt(
    state: AgentState,
    *,
    last_text: str,
    current_count: int,
    has_new_input: bool,
) -> dict:
    messages = state.get("messages", [])
    student_id = _student_id(state)
    study_plan = ensure_study_plan_state(state.get("study_plan", {}))
    if not student_id:
        return _closed_update(
            state,
            current_count=current_count if has_new_input else state.get("user_message_count", 0),
            last_text=last_text if has_new_input else state.get("last_user_text"),
            message=(
                "Para sincronizar con Outlook necesito tu perfil persistido. "
                "Termina primero el onboarding y luego vuelvo a intentarlo."
            ),
            study_plan_status="blocked_missing_student",
        )
    if not study_plan.persisted_profile_id or not study_plan.plan_events:
        return _closed_update(
            state,
            current_count=current_count if has_new_input else state.get("user_message_count", 0),
            last_text=last_text if has_new_input else state.get("last_user_text"),
            message=(
                "Aun no tengo un plan de estudio persistido para enviar a Outlook. "
                "Primero genera y guarda el plan semanal."
            ),
            study_plan_status="blocked_missing_plan",
        )

    materialization_update, materialization_error = _materialize_instances_for_calendar(
        state,
        student_id=student_id,
        study_plan_profile_id=study_plan.persisted_profile_id,
    )
    if materialization_error:
        return _closed_update(
            state,
            current_count=current_count if has_new_input else state.get("user_message_count", 0),
            last_text=last_text if has_new_input else state.get("last_user_text"),
            message=materialization_error,
            study_plan_status="blocked_materialization",
            materialization_update=materialization_update,
        )

    service = get_outlook_calendar_sync_service()
    preview = service.preview_student_calendar_sync(
        student_id=student_id,
        calendar_state=state.get("calendar", {}),
        calendar_id=dict(state.get("calendar", {})).get("calendar_id"),
        study_plan_profile_id=None,
    )
    if not preview.previewed:
        return _closed_update(
            state,
            current_count=current_count if has_new_input else state.get("user_message_count", 0),
            last_text=last_text if has_new_input else state.get("last_user_text"),
            message=_preview_failure_message(preview),
            study_plan_status=_sync_status_for_error(preview.error_code),
            error_code=preview.error_code,
            materialization_update=materialization_update,
        )

    if _preview_has_no_external_changes(preview):
        return _closed_update(
            state,
            current_count=current_count if has_new_input else state.get("user_message_count", 0),
            last_text=last_text if has_new_input else state.get("last_user_text"),
            message="No encontre cambios pendientes para Outlook. Tu calendario ya esta alineado.",
            study_plan_status="synced",
            materialization_update=materialization_update,
        )

    prompt = _preview_prompt(preview)
    confirmation_payload = {
        "domain": _CALENDAR_SYNC_DOMAIN,
        "operation": "sync_study_calendar",
        "preview": {
            "create_count": preview.create_count,
            "update_count": preview.update_count,
            "delete_count": preview.delete_count,
            "active_instance_count": preview.active_instance_count,
            "target_instance_count": preview.target_instance_count,
        },
        "study_plan_profile_id": study_plan.persisted_profile_id,
    }
    update = {
        "phase": "running",
        "awaiting_user_input": True,
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_text if has_new_input else state.get("last_user_text"),
        "messages": append_message(messages, "assistant", prompt),
        **_study_plan_sync_state_update(
            state,
            status="awaiting_confirmation",
            preview=confirmation_payload["preview"],
            materialization_update=materialization_update,
        ),
        **_confirmation_interaction(state, confirmation_payload),
    }
    return update


def _handle_confirmation(
    state: AgentState,
    *,
    last_text: str,
    current_count: int,
) -> dict:
    messages = state.get("messages", [])
    decision = parse_yes_no(last_text)
    if decision is None:
        prompt = "Responde si o no para confirmar la sincronizacion con Outlook."
        return {
            "phase": "running",
            "awaiting_user_input": True,
            "user_message_count": current_count,
            "last_user_text": last_text,
            "messages": append_message(messages, "assistant", prompt),
            **_confirmation_interaction(
                state,
                dict(state.interaction_state.last_confirmation_payload or {}),
            ),
        }
    if decision is False:
        return {
            "phase": "end",
            "awaiting_user_input": False,
            "user_message_count": current_count,
            "last_user_text": last_text,
            "messages": append_message(messages, "assistant", "Listo, no sincronice Outlook."),
            **_study_plan_sync_state_update(state, status="rejected"),
            **_clear_interaction(state),
        }

    student_id = _student_id(state)
    service = get_outlook_calendar_sync_service()
    result = service.sync_student_calendar(
        student_id=student_id,
        calendar_state=state.get("calendar", {}),
        calendar_id=dict(state.get("calendar", {})).get("calendar_id"),
        study_plan_profile_id=None,
    )
    if not result.synced:
        return {
            "phase": "end",
            "awaiting_user_input": False,
            "user_message_count": current_count,
            "last_user_text": last_text,
            "messages": append_message(messages, "assistant", _sync_failure_message(result)),
            **_study_plan_sync_state_update(
                state,
                status=_sync_status_for_error(result.error_code),
                error_code=result.error_code,
            ),
            **_calendar_update(state, result),
            **_clear_interaction(state),
        }

    return {
        "phase": "end",
        "awaiting_user_input": False,
        "user_message_count": current_count,
        "last_user_text": last_text,
        "messages": append_message(messages, "assistant", _success_message(result)),
        **_study_plan_sync_state_update(
            state,
            status="synced",
            result={
                "upserted_count": result.upserted_count,
                "deleted_count": result.deleted_count,
                "synced_event_count": len(result.synced_event_map),
            },
        ),
        **_calendar_update(state, result),
        **_clear_interaction(state),
    }


def _materialize_instances_for_calendar(
    state: AgentState,
    *,
    student_id: int,
    study_plan_profile_id: int,
) -> tuple[dict[str, object], str | None]:
    try:
        service = get_study_plan_materialization_service()
    except RepositoryConfigurationError:
        return {}, (
            "No pude preparar las sesiones fechadas para Outlook en este entorno. "
            "El plan local queda intacto."
        )
    result = service.materialize_plan_instances(
        student_id=student_id,
        study_plan_profile_id=study_plan_profile_id,
        study_plan=state.get("study_plan", {}),
        timezone=state.get("timezone", "America/Bogota"),
    )
    study_plan = state.get("study_plan", {})
    if result.materialized:
        return {
            "study_plan": update_study_plan_state(
                study_plan,
                materialized_instance_count=result.materialized_instance_count,
                superseded_instance_count=result.superseded_instance_count,
                materialized_horizon_days=result.horizon_days,
                materialized_through_date=result.materialized_through_date,
                materialization_error=None,
            )
        }, None
    return {
        "study_plan": update_study_plan_state(
            study_plan,
            materialization_error=result.error_code or "study_plan_materialization_error",
            materialized_horizon_days=result.horizon_days,
            materialized_through_date=result.materialized_through_date,
        )
    }, (
        "No pude preparar las sesiones fechadas para Outlook. "
        f"Detalle: {result.error_code or result.detail or 'materialization_error'}."
    )


def _study_plan_sync_state_update(
    state: AgentState,
    *,
    status: str,
    preview: dict[str, object] | None = None,
    result: dict[str, object] | None = None,
    error_code: str | None = None,
    materialization_update: dict[str, object] | None = None,
) -> dict[str, object]:
    study_plan = dict(
        (materialization_update or {}).get("study_plan")
        or _dump_state_model(state.get("study_plan", {}))
    )
    normalized = ensure_study_plan_state(study_plan)
    rules = dict(normalized.rules or {})
    payload = dict(rules.get("external_sync") or {})
    payload.update(
        {
            "provider": "outlook",
            "target": "study_sessions",
            "status": status,
            "requires_confirmation": status == "awaiting_confirmation",
            "last_error": error_code,
            "updated_at": _now_iso(state.get("timezone", "America/Bogota")),
        }
    )
    if preview is not None:
        payload["preview"] = dict(preview)
    if result is not None:
        payload["result"] = dict(result)
    rules["external_sync"] = payload
    rules["external_sync_status"] = status
    rules["external_sync_requires_confirmation"] = status == "awaiting_confirmation"
    return {
        "study_plan": update_study_plan_state(
            normalized.model_copy(update={"rules": rules}),
        )
    }


def _calendar_update(
    state: AgentState,
    result: OutlookCalendarSyncResult,
) -> dict[str, object]:
    calendar = dict(state.get("calendar", {}))
    calendar["provider"] = "outlook"
    if result.synced:
        calendar["authorized"] = True
        calendar["synced_event_map"] = dict(result.synced_event_map)
    elif result.error_code in {"microsoft_connection_not_found", "microsoft_oauth_error"}:
        calendar["authorized"] = False
    return {"calendar": calendar}


def _closed_update(
    state: AgentState,
    *,
    current_count: int,
    last_text: str | None,
    message: str,
    study_plan_status: str,
    error_code: str | None = None,
    materialization_update: dict[str, object] | None = None,
) -> dict:
    return {
        "phase": "end",
        "awaiting_user_input": False,
        "user_message_count": current_count,
        "last_user_text": last_text,
        "messages": append_message(state.get("messages", []), "assistant", message),
        **_study_plan_sync_state_update(
            state,
            status=study_plan_status,
            error_code=error_code,
            materialization_update=materialization_update,
        ),
        **_clear_interaction(state),
    }


def _preview_prompt(preview: OutlookCalendarSyncPreviewResult) -> str:
    parts = []
    if preview.create_count:
        parts.append(f"crear {preview.create_count}")
    if preview.update_count:
        parts.append(f"actualizar {preview.update_count}")
    if preview.delete_count:
        parts.append(f"eliminar {preview.delete_count}")
    summary = ", ".join(parts)
    return (
        "Puedo sincronizar tus sesiones de estudio con Outlook Calendar.\n"
        f"Cambios previstos: {summary} evento(s).\n"
        "No tocare tu plan local ni Microsoft To Do.\n"
        "Confirmas que sincronice Outlook? Responde si o no."
    )


def _preview_has_no_external_changes(preview: OutlookCalendarSyncPreviewResult) -> bool:
    return preview.create_count == 0 and preview.update_count == 0 and preview.delete_count == 0


def _preview_failure_message(preview: OutlookCalendarSyncPreviewResult) -> str:
    if preview.error_code in {"microsoft_connection_not_found", "microsoft_oauth_error"}:
        return (
            "Para sincronizar tus sesiones necesito que conectes Microsoft 365 primero. "
            "No hice cambios en Outlook ni en tu plan local."
        )
    if preview.error_code == "calendar_provider_not_outlook":
        return "La sincronizacion de esta fase solo esta disponible para Outlook Calendar."
    return (
        "No pude revisar que cambios haria en Outlook. "
        f"Detalle: {preview.error_code or preview.detail or 'calendar_preview_error'}."
    )


def _sync_failure_message(result: OutlookCalendarSyncResult) -> str:
    if result.error_code in {"microsoft_connection_not_found", "microsoft_oauth_error"}:
        return (
            "No pude sincronizar Outlook porque Microsoft 365 no esta conectado. "
            "Tu plan local queda intacto."
        )
    if result.error_code == "calendar_provider_not_outlook":
        return "No sincronice porque el calendario configurado no es Outlook."
    return (
        "No pude completar la sincronizacion con Outlook. "
        f"Detalle: {result.error_code or result.detail or 'outlook_calendar_sync_error'}."
    )


def _success_message(result: OutlookCalendarSyncResult) -> str:
    return (
        "Listo, sincronice tus sesiones de estudio con Outlook Calendar. "
        f"Eventos creados o actualizados: {result.upserted_count}; eliminados: {result.deleted_count}."
    )


def _sync_status_for_error(error_code: str | None) -> str:
    if error_code in {"microsoft_connection_not_found", "microsoft_oauth_error"}:
        return "blocked_oauth"
    if error_code == "calendar_provider_not_outlook":
        return "blocked_provider"
    return "failed"


def _confirmation_interaction(state: AgentState, payload: dict[str, object]) -> dict[str, object]:
    return update_interaction_state(
        state,
        active_intent="sync_study_calendar",
        active_subflow="calendar_sync",
        current_domain=_CALENDAR_SYNC_DOMAIN,
        interaction_mode="confirmation",
        pending_action="confirm_study_calendar_sync",
        pending_entity_type="study_plan",
        pending_entity_payload=payload,
        missing_fields_json=[],
        confirmation_pending=True,
        last_confirmation_payload=payload,
        clarification_needed=False,
        current_step="awaiting_calendar_sync_confirmation",
        current_section="calendar_sync",
    )


def _clear_interaction(state: AgentState) -> dict[str, object]:
    return update_interaction_state(
        state,
        active_intent=None,
        active_subflow=None,
        current_domain=_CALENDAR_SYNC_DOMAIN,
        interaction_mode="guided",
        pending_action=None,
        pending_entity_type=None,
        pending_entity_payload={},
        missing_fields_json=[],
        confirmation_pending=False,
        last_confirmation_payload=None,
        clarification_needed=False,
        current_step=None,
        current_section=None,
    )


def _student_id(state: AgentState) -> int | None:
    profile = dict(state.get("student_profile", {}))
    raw_value = profile.get("persisted_student_id")
    try:
        return int(raw_value) if raw_value else None
    except (TypeError, ValueError):
        return None


def _dump_state_model(value: object) -> dict[str, object]:
    if hasattr(value, "model_dump"):
        return dict(value.model_dump(mode="python"))
    if isinstance(value, dict):
        return dict(value)
    return {}


def _now_iso(timezone: str) -> str:
    try:
        return datetime.now(ZoneInfo(str(timezone or "America/Bogota"))).isoformat()
    except Exception:
        return datetime.utcnow().isoformat()


__all__ = ["sync_study_calendar_turn"]
