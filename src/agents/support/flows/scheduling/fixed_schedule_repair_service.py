"""Subflujo para reparar drift manual del horario fijo en Outlook."""

from __future__ import annotations

from typing import Any

from agents.support.dependencies import (
    get_outlook_fixed_schedule_repair_service,
    get_schedule_service,
)
from agents.support.nodes.utils import (
    append_message,
    normalize_text,
    parse_numbered_option,
)
from agents.support.runtime_state_helpers import update_conversation_state
from agents.support.scheduling.state_helpers import (
    ensure_schedule_flow_state,
    update_schedule_flow_state,
    update_scheduling_state,
)
from agents.support.state import AgentState

_REPAIR_STATUSES = {"drifted", "missing"}


def requires_fixed_schedule_repair(state: AgentState) -> bool:
    """Indica si hay drift/missing pendiente de decisión conversacional."""

    schedule_state = ensure_schedule_flow_state(state.get("schedule", {}))
    if schedule_state.repair_stage == "awaiting_decision":
        return True

    lookup = _lookup_repair_context(state)
    if lookup is None:
        return False
    _, blocks = lookup
    return any(_is_repairable(block) for block in blocks)


def handle_fixed_schedule_repair_turn(
    state: AgentState,
    *,
    has_new_input: bool,
    last_text: str | None,
    current_count: int,
) -> dict:
    """Gestiona la decisión del estudiante ante drift manual en Outlook."""

    schedule_state = ensure_schedule_flow_state(state.get("schedule", {}))
    repair_stage = str(schedule_state.repair_stage or "idle")
    lookup = _lookup_repair_context(state)

    if lookup is None:
        return _build_repair_update(
            state,
            schedule_state=schedule_state,
            repair_stage="idle",
            phase="end",
            awaiting_user_input=False,
            current_count=current_count if has_new_input else state.get("user_message_count", 0),
            last_text=last_text if has_new_input else state.get("last_user_text"),
            prompt="No encontré cambios pendientes de reparación en tu horario fijo de Outlook.",
        )

    persisted_profile, blocks = lookup
    repairable_blocks = [block for block in blocks if _is_repairable(block)]
    if not repairable_blocks and repair_stage != "awaiting_decision":
        return _build_repair_update(
            state,
            schedule_state=schedule_state,
            repair_stage="idle",
            phase="end",
            awaiting_user_input=False,
            current_count=current_count if has_new_input else state.get("user_message_count", 0),
            last_text=last_text if has_new_input else state.get("last_user_text"),
            prompt="No encontré cambios pendientes de reparación en tu horario fijo de Outlook.",
        )

    if repair_stage == "idle":
        return _build_repair_update(
            state,
            schedule_state=schedule_state,
            repair_stage="awaiting_decision",
            phase="schedule_repair",
            awaiting_user_input=True,
            current_count=current_count if has_new_input else state.get("user_message_count", 0),
            last_text=last_text if has_new_input else state.get("last_user_text"),
            prompt=_build_repair_prompt(repairable_blocks),
            persisted_profile_id=persisted_profile.id,
        )

    if repair_stage == "awaiting_decision":
        decision = _parse_repair_decision(last_text) if has_new_input else None
        if decision == "restore":
            return _restore_outlook_from_internal_schedule(
                state,
                schedule_state=schedule_state,
                persisted_profile=persisted_profile,
                current_count=current_count,
                last_text=last_text,
            )
        if decision == "replace":
            return _restart_schedule_capture(
                state,
                schedule_state=schedule_state,
                current_count=current_count,
                last_text=last_text,
            )
        if decision == "later":
            return _build_repair_update(
                state,
                schedule_state=schedule_state,
                repair_stage="idle",
                phase="end",
                awaiting_user_input=False,
                current_count=current_count,
                last_text=last_text,
                prompt=(
                    "⏳ De acuerdo. No tocaré Outlook por ahora. "
                    "Cuando quieras, puedo volver a revisar y reparar tu horario fijo."
                ),
            )
        return _build_repair_update(
            state,
            schedule_state=schedule_state,
            repair_stage="awaiting_decision",
            phase="schedule_repair",
            awaiting_user_input=True,
            current_count=current_count,
            last_text=last_text,
            prompt=_build_repair_prompt(repairable_blocks),
            persisted_profile_id=persisted_profile.id,
        )

    return _build_repair_update(
        state,
        schedule_state=schedule_state,
        repair_stage="awaiting_decision",
        phase="schedule_repair",
        awaiting_user_input=True,
        current_count=current_count if has_new_input else state.get("user_message_count", 0),
        last_text=last_text if has_new_input else state.get("last_user_text"),
        prompt=_build_repair_prompt(repairable_blocks),
        persisted_profile_id=persisted_profile.id,
    )


def _restore_outlook_from_internal_schedule(
    state: AgentState,
    *,
    schedule_state: object,
    persisted_profile: Any,
    current_count: int,
    last_text: str | None,
) -> dict:
    profile = dict(state.get("student_profile", {}))
    calendar_state = dict(state.get("calendar", {}))
    result = get_outlook_fixed_schedule_repair_service().repair_schedule_profile(
        student_id=profile.get("persisted_student_id"),
        schedule_profile_id=persisted_profile.id,
        calendar_state=calendar_state,
        calendar_id=calendar_state.get("calendar_id"),
        reconcile_first=True,
    )
    if not result.repaired:
        return _build_repair_update(
            state,
            schedule_state=schedule_state,
            repair_stage="idle",
            phase="end",
            awaiting_user_input=False,
            current_count=current_count,
            last_text=last_text,
            prompt=(
                "⚠️ Intenté reparar Outlook, pero no pude completar la sincronización.\n"
                f"Detalle técnico: {result.detail or result.error_code or 'desconocido'}"
            ),
        )

    message = (
        "✅ Listo. Restauré Outlook usando tu horario fijo oficial del asistente.\n"
        f"Bloques reparados: {result.repairable_count}. "
        f"Restaurados: {result.restored_count}. "
        f"Recreados: {result.recreated_count}."
    )
    return {
        **update_scheduling_state(
            state,
            schedule=update_schedule_flow_state(
                schedule_state,
                repair_stage="idle",
                persisted_profile_id=persisted_profile.id,
            ),
        ),
        **update_conversation_state(
            state,
            phase="end",
            user_message_count=current_count,
            last_user_text=last_text,
            awaiting_user_input=False,
            messages=append_message(state.get("messages", []), "assistant", message),
        ),
        "calendar": {
            **calendar_state,
            "provider": "outlook",
            "authorized": True,
            "synced_event_map": dict(result.synced_event_map),
        },
    }


def _restart_schedule_capture(
    state: AgentState,
    *,
    schedule_state: object,
    current_count: int,
    last_text: str | None,
) -> dict:
    return {
        **update_scheduling_state(
            state,
            raw_inputs={},
            extras_collect_stage=None,
            extras_pending_is_variable=None,
            extras_pending_items=[],
            academic_pending_items=[],
            work_pending_items=[],
            extracurricular=[],
            events=[],
            schedule_preview={},
            schedule=update_schedule_flow_state(
                schedule_state,
                blocks=[],
                conflicts=[],
                summary_text=None,
                review_stage="idle",
                capture_target=None,
                capture_stage="idle",
                correction_target=None,
                editing_block_id=None,
                editing_field=None,
                pending_correction_text=None,
                conflicts_accepted=False,
                schedule_end_date=None,
                persisted_profile_id=None,
                persistence_error=None,
                renewal_stage="idle",
                repair_stage="idle",
            ),
        ),
        **update_conversation_state(
            state,
            phase="schedules",
            user_message_count=current_count,
            last_user_text=last_text,
            awaiting_user_input=False,
            messages=append_message(
                state.get("messages", []),
                "assistant",
                (
                    "🛠️ Perfecto. Si el cambio en Outlook era intencional, "
                    "vamos a organizar un horario fijo nuevo desde cero."
                ),
            ),
        ),
    }


def _lookup_repair_context(
    state: AgentState,
) -> tuple[Any, list[Any]] | None:
    profile = dict(state.get("student_profile", {}))
    service = get_schedule_service()
    lookup = service.list_current_schedule_blocks(
        student_id=profile.get("persisted_student_id")
    )
    if not lookup.found or lookup.profile is None or lookup.blocks is None:
        return None
    return lookup.profile, list(lookup.blocks)


def _build_repair_update(
    state: AgentState,
    *,
    schedule_state: object,
    repair_stage: str,
    phase: str,
    awaiting_user_input: bool,
    current_count: int,
    last_text: str | None,
    prompt: str,
    persisted_profile_id: int | None = None,
) -> dict:
    schedule_changes: dict[str, object] = {
        "repair_stage": repair_stage,
    }
    if persisted_profile_id is not None:
        schedule_changes["persisted_profile_id"] = persisted_profile_id
    return {
        **update_scheduling_state(
            state,
            schedule=update_schedule_flow_state(
                schedule_state,
                **schedule_changes,
            ),
        ),
        **update_conversation_state(
            state,
            phase=phase,  # type: ignore[arg-type]
            user_message_count=current_count,
            last_user_text=last_text,
            awaiting_user_input=awaiting_user_input,
            messages=append_message(state.get("messages", []), "assistant", prompt),
        ),
    }


def _build_repair_prompt(blocks: list[Any]) -> str:
    drifted_count = sum(1 for block in blocks if _block_sync_status(block) == "drifted")
    missing_count = sum(1 for block in blocks if _block_sync_status(block) == "missing")
    return (
        "🛠️ Detecté cambios manuales en tu horario fijo de Outlook.\n"
        f"Eventos editados: {drifted_count}. Eventos eliminados: {missing_count}.\n\n"
        "Tu horario oficial sigue guardado en el asistente. ¿Qué quieres hacer?\n"
        "(Escribe el número de la opción que quieres elegir)\n"
        "1. Restaurar Outlook con el horario oficial del asistente\n"
        "2. Conservar el cambio de Outlook y organizar un horario fijo nuevo\n"
        "3. Revisarlo después"
    )


def _parse_repair_decision(text: str | None) -> str | None:
    option = parse_numbered_option(text)
    if option == 1:
        return "restore"
    if option == 2:
        return "replace"
    if option == 3:
        return "later"

    normalized = normalize_text(text or "")
    if any(token in normalized for token in ("restaurar", "reparar", "corregir outlook")):
        return "restore"
    if any(token in normalized for token in ("nuevo horario", "organizar", "cambiar horario")):
        return "replace"
    if any(token in normalized for token in ("luego", "despues", "después", "mas tarde", "más tarde")):
        return "later"
    return None


def _is_repairable(block: Any) -> bool:
    return _block_sync_status(block) in _REPAIR_STATUSES


def _block_sync_status(block: Any) -> str:
    if isinstance(block, dict):
        return str(block.get("external_sync_status") or "").strip()
    return str(getattr(block, "external_sync_status", "") or "").strip()


__all__ = [
    "handle_fixed_schedule_repair_turn",
    "requires_fixed_schedule_repair",
]
