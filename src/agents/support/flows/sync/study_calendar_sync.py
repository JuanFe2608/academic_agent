"""Flujo confirmable para sincronizar sesiones de estudio con Outlook."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from agents.support.dependencies import (
    get_outlook_calendar_sync_service,
    get_outlook_study_calendar_reconciliation_service,
    get_study_plan_materialization_service,
)
from agents.support.nodes.utils import append_message, detect_new_input, parse_yes_no
from agents.support.state import AgentState
from bootstrap.errors import RepositoryConfigurationError
from services.conversation.state_helpers import ensure_interaction_state, update_interaction_state
from services.planning import ensure_study_plan_state, update_study_plan_state
from services.sync import OutlookCalendarSyncPreviewResult, OutlookCalendarSyncResult

_CALENDAR_SYNC_DOMAIN = "calendar_sync"
_MANUAL_DRIFT_OPERATION = "resolve_study_calendar_manual_changes"


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
    reconciliation = _reconcile_study_calendar_before_sync(
        state,
        student_id=student_id,
        study_plan_profile_id=study_plan.persisted_profile_id,
    )
    if reconciliation is not None:
        if not reconciliation.get("reconciled"):
            return _closed_update(
                state,
                current_count=current_count if has_new_input else state.get("user_message_count", 0),
                last_text=last_text if has_new_input else state.get("last_user_text"),
                message=str(reconciliation.get("message") or "No pude revisar Outlook antes de sincronizar."),
                study_plan_status="manual_reconciliation_failed",
                error_code=str(reconciliation.get("error_code") or "manual_reconciliation_failed"),
                materialization_update=materialization_update,
            )
        if reconciliation.get("manual_changes"):
            confirmation_payload = {
                "domain": _CALENDAR_SYNC_DOMAIN,
                "operation": _MANUAL_DRIFT_OPERATION,
                "study_plan_profile_id": study_plan.persisted_profile_id,
                "findings": list(reconciliation.get("findings") or []),
            }
            return {
                "phase": "running",
                "awaiting_user_input": True,
                "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
                "last_user_text": last_text if has_new_input else state.get("last_user_text"),
                "messages": append_message(messages, "assistant", _manual_study_calendar_change_prompt(reconciliation)),
                **_study_plan_sync_state_update(
                    state,
                    status="awaiting_manual_outlook_decision",
                    preview={
                        "drifted_count": int(reconciliation.get("drifted_count") or 0),
                        "missing_count": int(reconciliation.get("missing_count") or 0),
                    },
                    materialization_update=materialization_update,
                ),
                **_confirmation_interaction(state, confirmation_payload),
            }

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
    payload = dict(state.interaction_state.last_confirmation_payload or {})
    if payload.get("operation") == _MANUAL_DRIFT_OPERATION:
        return _handle_manual_drift_decision(
            state,
            last_text=last_text,
            current_count=current_count,
            payload=payload,
        )

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


def _handle_manual_drift_decision(
    state: AgentState,
    *,
    last_text: str,
    current_count: int,
    payload: dict[str, object],
) -> dict:
    messages = state.get("messages", [])
    decision = _parse_manual_drift_decision(last_text)
    if decision is None:
        prompt = (
            "Responde con una opción:\n"
            "1. Conservar el cambio de Outlook\n"
            "2. Restaurar el plan del asistente en Outlook\n"
            "3. Cancelar"
        )
        return {
            "phase": "running",
            "awaiting_user_input": True,
            "user_message_count": current_count,
            "last_user_text": last_text,
            "messages": append_message(messages, "assistant", prompt),
            **_confirmation_interaction(state, payload),
        }

    if decision == "keep":
        return {
            "phase": "end",
            "awaiting_user_input": False,
            "user_message_count": current_count,
            "last_user_text": last_text,
            "messages": append_message(
                messages,
                "assistant",
                (
                    "De acuerdo. Conservaré el cambio manual en Outlook y no lo sobrescribiré ahora. "
                    "Tu plan oficial del asistente queda igual."
                ),
            ),
            **_study_plan_sync_state_update(
                state,
                status="manual_outlook_change_kept",
                result={
                    "decision": "keep",
                    "manual_change_count": len(list(payload.get("findings") or [])),
                },
            ),
            **_clear_interaction(state),
        }

    if decision == "cancel":
        return {
            "phase": "end",
            "awaiting_user_input": False,
            "user_message_count": current_count,
            "last_user_text": last_text,
            "messages": append_message(messages, "assistant", "Listo, no hice cambios en Outlook."),
            **_study_plan_sync_state_update(state, status="manual_outlook_decision_cancelled"),
            **_clear_interaction(state),
        }

    student_id = _student_id(state)
    _mark_missing_study_calendar_links_deleted(
        state,
        student_id=student_id,
        findings=list(payload.get("findings") or []),
    )
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
        "messages": append_message(
            messages,
            "assistant",
            (
                "Listo. Restauré Outlook usando el plan oficial del asistente. "
                f"Eventos creados o actualizados: {result.upserted_count}; eliminados: {result.deleted_count}."
            ),
        ),
        **_study_plan_sync_state_update(
            state,
            status="synced",
            result={
                "decision": "restore",
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


def _reconcile_study_calendar_before_sync(
    state: AgentState,
    *,
    student_id: int,
    study_plan_profile_id: int,
) -> dict[str, object] | None:
    try:
        service = get_outlook_study_calendar_reconciliation_service()
        result = service.reconcile_student_calendar(
            student_id=student_id,
            calendar_id=dict(state.get("calendar", {})).get("calendar_id"),
            study_plan_profile_id=study_plan_profile_id,
        )
    except RepositoryConfigurationError:
        return None
    except Exception as exc:
        return {
            "reconciled": False,
            "error_code": "outlook_study_calendar_reconciliation_error",
            "message": f"No pude revisar cambios manuales en Outlook. Detalle: {exc}",
        }

    if not result.reconciled:
        if result.error_code in {"microsoft_connection_not_found", "microsoft_oauth_error"}:
            return None
        return {
            "reconciled": False,
            "error_code": result.error_code or "outlook_study_calendar_reconciliation_failed",
            "message": (
                "No pude revisar cambios manuales en Outlook antes de sincronizar. "
                f"Detalle: {result.detail or result.error_code or 'desconocido'}."
            ),
        }

    manual_findings = [
        finding
        for finding in result.findings
        if finding.status in {"drifted", "missing"}
    ]
    if not manual_findings:
        return {"reconciled": True, "manual_changes": False}
    return {
        "reconciled": True,
        "manual_changes": True,
        "drifted_count": result.drifted_count,
        "missing_count": result.missing_count,
        "findings": [
            {
                "source_instance_key": finding.source_instance_key,
                "external_event_id": finding.external_event_id,
                "status": finding.status,
                "title": finding.title,
                "drift_fields": list(finding.drift_fields),
                "detail": finding.detail,
                "web_link": finding.web_link,
            }
            for finding in manual_findings
        ],
    }


def _manual_study_calendar_change_prompt(reconciliation: dict[str, object]) -> str:
    drifted_count = int(reconciliation.get("drifted_count") or 0)
    missing_count = int(reconciliation.get("missing_count") or 0)
    finding = next(iter(list(reconciliation.get("findings") or [])), {})
    title = str(finding.get("title") or "esta sesión").strip()
    noun = "esta sesión" if drifted_count + missing_count == 1 else "estas sesiones"
    return (
        f"Detecté que editaste {noun} en Outlook: {title}.\n"
        f"Sesiones editadas: {drifted_count}. Sesiones eliminadas: {missing_count}.\n\n"
        "¿Quieres conservar ese cambio o restaurar el plan del asistente?\n"
        "(Escribe el número de la opción que quieres elegir)\n"
        "1. Conservar el cambio de Outlook\n"
        "2. Restaurar el plan del asistente en Outlook\n"
        "3. Cancelar"
    )


def _parse_manual_drift_decision(text: str | None) -> str | None:
    normalized = _normalize_decision_text(text)
    if normalized.startswith("1") or any(token in normalized for token in ("conservar", "mantener", "dejar outlook")):
        return "keep"
    if normalized.startswith("2") or any(token in normalized for token in ("restaurar", "sobrescribir", "plan del asistente")):
        return "restore"
    if normalized.startswith("3") or any(token in normalized for token in ("cancelar", "no hacer", "despues", "después")):
        return "cancel"
    return None


def _normalize_decision_text(text: str | None) -> str:
    import unicodedata

    raw = str(text or "").strip().lower()
    return (
        unicodedata.normalize("NFKD", raw)
        .encode("ascii", "ignore")
        .decode("ascii")
    )


def _mark_missing_study_calendar_links_deleted(
    state: AgentState,
    *,
    student_id: int | None,
    findings: list[object],
) -> None:
    missing_keys: list[str] = []
    for finding in findings:
        if not isinstance(finding, dict):
            continue
        if finding.get("status") != "missing":
            continue
        key = str(finding.get("source_instance_key") or "").strip()
        if key:
            missing_keys.append(key)
    if not missing_keys:
        return
    try:
        get_outlook_study_calendar_reconciliation_service().mark_missing_links_deleted(
            student_id=student_id,
            source_instance_keys=missing_keys,
        )
    except Exception:
        return


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
