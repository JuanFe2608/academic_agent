"""Flujo confirmable para proyectar sesiones accionables a Microsoft To Do."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from agents.support.dependencies import get_microsoft_todo_sync_service
from agents.support.nodes.utils import append_message, detect_new_input, parse_yes_no
from agents.support.state import AgentState
from services.conversation.state_helpers import ensure_interaction_state, update_interaction_state
from services.planning import ensure_study_plan_state, update_study_plan_state
from services.sync import MicrosoftTodoSyncPreviewResult, MicrosoftTodoSyncResult

_TODO_SYNC_DOMAIN = "todo_sync"


def sync_study_todo_turn(state: AgentState) -> dict:
    """Previsualiza y aplica sync de sesiones no resueltas hacia To Do."""

    messages = state.get("messages", [])
    has_new_input, last_text, current_count = detect_new_input(
        messages,
        state.get("user_message_count", 0),
        state.get("awaiting_user_input", False),
        state.get("last_user_text"),
    )
    interaction = ensure_interaction_state(state)
    confirmation_payload = dict(interaction.last_confirmation_payload or {})

    if interaction.confirmation_pending and confirmation_payload.get("domain") == _TODO_SYNC_DOMAIN:
        if not has_new_input:
            return {
                "phase": "todo_sync",
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
    student_id = _student_id(state)
    if not student_id:
        return _closed_update(
            state,
            current_count=current_count if has_new_input else state.get("user_message_count", 0),
            last_text=last_text if has_new_input else state.get("last_user_text"),
            message=(
                "Para sincronizar Microsoft To Do necesito tu perfil persistido. "
                "Termina primero el onboarding y luego vuelvo a intentarlo."
            ),
            study_plan_status="blocked_missing_student",
        )

    service = get_microsoft_todo_sync_service()
    preview = service.preview_actionable_sessions(
        student_id=student_id,
        task_list_id=_task_list_id_from_state(state),
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
        )

    if _preview_has_no_external_changes(preview):
        return _closed_update(
            state,
            current_count=current_count if has_new_input else state.get("user_message_count", 0),
            last_text=last_text if has_new_input else state.get("last_user_text"),
            message=(
                "No encontre sesiones perdidas u omitidas pendientes para Microsoft To Do. "
                "Tus tareas accionables ya estan alineadas."
            ),
            study_plan_status="synced",
            result={
                "actionable_count": preview.actionable_count,
                "active_task_count": preview.active_task_count,
            },
        )

    prompt = _preview_prompt(preview)
    confirmation_payload = {
        "domain": _TODO_SYNC_DOMAIN,
        "operation": "sync_study_todo",
        "preview": {
            "create_count": preview.create_count,
            "update_count": preview.update_count,
            "delete_count": preview.delete_count,
            "actionable_count": preview.actionable_count,
            "active_task_count": preview.active_task_count,
            "target_task_count": preview.target_task_count,
        },
        "task_list_id": preview.task_list_id,
        "study_plan_profile_id": None,
    }
    return {
        "phase": "todo_sync",
        "awaiting_user_input": True,
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_text if has_new_input else state.get("last_user_text"),
        "messages": append_message(state.get("messages", []), "assistant", prompt),
        **_study_plan_todo_sync_state_update(
            state,
            status="awaiting_confirmation",
            preview=confirmation_payload["preview"],
            task_list_id=preview.task_list_id,
        ),
        **_confirmation_interaction(state, confirmation_payload),
    }


def _handle_confirmation(
    state: AgentState,
    *,
    last_text: str,
    current_count: int,
) -> dict:
    messages = state.get("messages", [])
    decision = parse_yes_no(last_text)
    if decision is None:
        return {
            "phase": "todo_sync",
            "awaiting_user_input": True,
            "user_message_count": current_count,
            "last_user_text": last_text,
            "messages": append_message(
                messages,
                "assistant",
                "Responde si o no para confirmar la sincronizacion con Microsoft To Do.",
            ),
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
            "messages": append_message(messages, "assistant", "Listo, no sincronice Microsoft To Do."),
            **_study_plan_todo_sync_state_update(state, status="rejected"),
            **_clear_interaction(state),
        }

    student_id = _student_id(state)
    payload = dict(state.interaction_state.last_confirmation_payload or {})
    service = get_microsoft_todo_sync_service()
    result = service.sync_actionable_sessions(
        student_id=student_id,
        task_list_id=_payload_task_list_id(payload) or _task_list_id_from_state(state),
        study_plan_profile_id=None,
    )
    if not result.synced:
        return {
            "phase": "end",
            "awaiting_user_input": False,
            "user_message_count": current_count,
            "last_user_text": last_text,
            "messages": append_message(messages, "assistant", _sync_failure_message(result)),
            **_study_plan_todo_sync_state_update(
                state,
                status=_sync_status_for_error(result.error_code),
                error_code=result.error_code,
                result={
                    "synced_task_count": len(result.synced_task_map),
                },
            ),
            **_clear_interaction(state),
        }

    return {
        "phase": "end",
        "awaiting_user_input": False,
        "user_message_count": current_count,
        "last_user_text": last_text,
        "messages": append_message(messages, "assistant", _success_message(result)),
        **_study_plan_todo_sync_state_update(
            state,
            status="synced",
            result={
                "upserted_count": result.upserted_count,
                "deleted_count": result.deleted_count,
                "synced_task_count": len(result.synced_task_map),
            },
            synced_task_map=result.synced_task_map,
        ),
        **_clear_interaction(state),
    }


def _study_plan_todo_sync_state_update(
    state: AgentState,
    *,
    status: str,
    preview: dict[str, object] | None = None,
    result: dict[str, object] | None = None,
    error_code: str | None = None,
    task_list_id: str | None = None,
    synced_task_map: dict[str, str] | None = None,
) -> dict[str, object]:
    study_plan = _dump_state_model(state.get("study_plan", {}))
    normalized = ensure_study_plan_state(study_plan)
    rules = dict(normalized.rules or {})
    payload = dict(rules.get("todo_sync") or {})
    payload.update(
        {
            "provider": "microsoft_todo",
            "target": "actionable_study_sessions",
            "status": status,
            "requires_confirmation": status == "awaiting_confirmation",
            "last_error": error_code,
            "updated_at": _now_iso(state.get("timezone", "America/Bogota")),
        }
    )
    if task_list_id:
        payload["task_list_id"] = task_list_id
    if preview is not None:
        payload["preview"] = dict(preview)
    if result is not None:
        payload["result"] = dict(result)
    if synced_task_map is not None:
        payload["synced_task_map"] = dict(synced_task_map)

    rules["todo_sync"] = payload
    targets = list(rules.get("external_sync_targets") or [])
    if "microsoft_todo" not in targets:
        targets.append("microsoft_todo")
    rules["external_sync_targets"] = targets
    status_by_target = dict(rules.get("external_sync_status_by_target") or {})
    status_by_target["microsoft_todo"] = status
    rules["external_sync_status_by_target"] = status_by_target
    rules["external_sync_status"] = status
    rules["external_sync_requires_confirmation"] = status == "awaiting_confirmation"
    return {
        "study_plan": update_study_plan_state(
            normalized.model_copy(update={"rules": rules}),
        )
    }


def _closed_update(
    state: AgentState,
    *,
    current_count: int,
    last_text: str | None,
    message: str,
    study_plan_status: str,
    error_code: str | None = None,
    result: dict[str, object] | None = None,
) -> dict:
    return {
        "phase": "end",
        "awaiting_user_input": False,
        "user_message_count": current_count,
        "last_user_text": last_text,
        "messages": append_message(state.get("messages", []), "assistant", message),
        **_study_plan_todo_sync_state_update(
            state,
            status=study_plan_status,
            error_code=error_code,
            result=result,
        ),
        **_clear_interaction(state),
    }


def _preview_prompt(preview: MicrosoftTodoSyncPreviewResult) -> str:
    parts = []
    if preview.create_count:
        parts.append(f"crear {preview.create_count}")
    if preview.update_count:
        parts.append(f"actualizar {preview.update_count}")
    if preview.delete_count:
        parts.append(f"eliminar {preview.delete_count}")
    summary = ", ".join(parts)
    return (
        "Puedo sincronizar tus pendientes accionables con Microsoft To Do.\n"
        f"Cambios previstos: {summary} tarea(s).\n"
        "Solo usare sesiones de estudio perdidas u omitidas; no creare tareas para sesiones ya resueltas.\n"
        "Confirmas que sincronice Microsoft To Do? Responde si o no."
    )


def _preview_has_no_external_changes(preview: MicrosoftTodoSyncPreviewResult) -> bool:
    return preview.create_count == 0 and preview.update_count == 0 and preview.delete_count == 0


def _preview_failure_message(preview: MicrosoftTodoSyncPreviewResult) -> str:
    if preview.error_code in {"microsoft_connection_not_found", "microsoft_oauth_error"}:
        return (
            "Para sincronizar tus pendientes necesito que conectes Microsoft 365 primero. "
            "No hice cambios en To Do ni en tu plan local."
        )
    if preview.error_code == "missing_task_list_id":
        return (
            "No pude encontrar una lista de Microsoft To Do para tus pendientes. "
            "No hice cambios externos."
        )
    return (
        "No pude revisar que cambios haria en Microsoft To Do. "
        f"Detalle: {preview.error_code or preview.detail or 'microsoft_todo_preview_error'}."
    )


def _sync_failure_message(result: MicrosoftTodoSyncResult) -> str:
    if result.error_code in {"microsoft_connection_not_found", "microsoft_oauth_error"}:
        return (
            "No pude sincronizar Microsoft To Do porque Microsoft 365 no esta conectado. "
            "Tu plan local queda intacto."
        )
    if result.error_code == "missing_task_list_id":
        return "No sincronice porque no encontre una lista valida de Microsoft To Do."
    return (
        "No pude completar la sincronizacion con Microsoft To Do. "
        f"Detalle: {result.error_code or result.detail or 'microsoft_todo_sync_error'}."
    )


def _success_message(result: MicrosoftTodoSyncResult) -> str:
    return (
        "Listo, sincronice tus pendientes accionables con Microsoft To Do. "
        f"Tareas creadas o actualizadas: {result.upserted_count}; eliminadas: {result.deleted_count}."
    )


def _sync_status_for_error(error_code: str | None) -> str:
    if error_code in {"microsoft_connection_not_found", "microsoft_oauth_error"}:
        return "blocked_oauth"
    if error_code == "missing_task_list_id":
        return "blocked_task_list"
    if error_code == "missing_student_id":
        return "blocked_missing_student"
    return "failed"


def _confirmation_interaction(state: AgentState, payload: dict[str, object]) -> dict[str, object]:
    return update_interaction_state(
        state,
        active_intent="sync_study_todo",
        current_domain=_TODO_SYNC_DOMAIN,
        interaction_mode="confirmation",
        pending_action="confirm_study_todo_sync",
        pending_entity_type="study_actionable_tasks",
        pending_entity_payload=payload,
        missing_fields_json=[],
        confirmation_pending=True,
        last_confirmation_payload=payload,
        clarification_needed=False,
        current_step="awaiting_todo_sync_confirmation",
        current_section="todo_sync",
    )


def _clear_interaction(state: AgentState) -> dict[str, object]:
    return update_interaction_state(
        state,
        active_intent=None,
        current_domain=_TODO_SYNC_DOMAIN,
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


def _task_list_id_from_state(state: AgentState) -> str | None:
    study_plan = ensure_study_plan_state(state.get("study_plan", {}))
    todo_sync = dict(study_plan.rules.get("todo_sync") or {})
    raw_value = todo_sync.get("task_list_id")
    if raw_value:
        return str(raw_value)
    return None


def _payload_task_list_id(payload: dict[str, object]) -> str | None:
    raw_value = payload.get("task_list_id")
    if raw_value is None:
        return None
    normalized = str(raw_value).strip()
    return normalized or None


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


__all__ = ["sync_study_todo_turn"]
