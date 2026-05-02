"""Subflujo para renovar un horario fijo que ya venció."""

from __future__ import annotations

from agents.support.dependencies import (
    get_outlook_fixed_schedule_sync_service,
    get_schedule_service,
)
from agents.support.nodes.utils import (
    append_message,
    normalize_text,
    parse_numbered_option,
    parse_yes_no,
)
from agents.support.runtime_state_helpers import update_conversation_state
from agents.support.scheduling.state_helpers import (
    ensure_schedule_flow_state,
    update_scheduling_state,
    update_schedule_flow_state,
)
from agents.support.state import AgentState
from services.scheduling import (
    format_schedule_end_date,
    is_schedule_expired,
    parse_schedule_end_date,
)
from services.scheduling.end_date_support import schedule_end_date_max_date


def requires_fixed_schedule_renewal(state: AgentState) -> bool:
    """Indica si el horario fijo actual ya venció y requiere decisión del estudiante."""

    profile = dict(state.get("student_profile", {}))
    lookup = get_schedule_service().get_current_schedule_profile(
        student_id=profile.get("persisted_student_id")
    )
    if not lookup.found or lookup.profile is None:
        return False

    timezone_name = str(
        lookup.profile.base_timezone
        or state.get("timezone")
        or "America/Bogota"
    )
    return is_schedule_expired(
        lookup.profile.schedule_end_date,
        timezone_name=timezone_name,
    )


def handle_fixed_schedule_renewal_turn(
    state: AgentState,
    *,
    has_new_input: bool,
    last_text: str | None,
    current_count: int,
) -> dict:
    """Gestiona la conversación de renovación del horario fijo expirado."""

    schedule_state = ensure_schedule_flow_state(state.get("schedule", {}))
    renewal_stage = str(schedule_state.renewal_stage or "idle")
    profile = dict(state.get("student_profile", {}))
    calendar_state = dict(state.get("calendar", {}))
    lookup = get_schedule_service().get_current_schedule_profile(
        student_id=profile.get("persisted_student_id")
    )

    if not lookup.found or lookup.profile is None:
        return {
            **update_scheduling_state(
                state,
                schedule=update_schedule_flow_state(
                    schedule_state,
                    renewal_stage="idle",
                ),
            ),
            **update_conversation_state(
                state,
                phase="end",
                user_message_count=(
                    current_count if has_new_input else state.get("user_message_count", 0)
                ),
                last_user_text=last_text if has_new_input else state.get("last_user_text"),
                awaiting_user_input=False,
            ),
        }

    persisted_profile = lookup.profile
    timezone_name = str(
        persisted_profile.base_timezone
        or state.get("timezone")
        or "America/Bogota"
    )

    if not is_schedule_expired(
        persisted_profile.schedule_end_date,
        timezone_name=timezone_name,
    ):
        return {
            **update_scheduling_state(
                state,
                schedule=update_schedule_flow_state(
                    schedule_state,
                    renewal_stage="idle",
                ),
            ),
            **update_conversation_state(
                state,
                phase="end",
                user_message_count=(
                    current_count if has_new_input else state.get("user_message_count", 0)
                ),
                last_user_text=last_text if has_new_input else state.get("last_user_text"),
                awaiting_user_input=False,
            ),
        }

    if renewal_stage == "idle":
        return _build_renewal_update(
            state,
            schedule_state=schedule_state,
            renewal_stage="awaiting_decision",
            phase="schedule_renewal",
            awaiting_user_input=True,
            current_count=(
                current_count if has_new_input else state.get("user_message_count", 0)
            ),
            last_text=last_text if has_new_input else state.get("last_user_text"),
            prompt=_build_expired_schedule_prompt(persisted_profile),
        )

    if renewal_stage == "awaiting_decision":
        decision = _parse_renewal_decision(last_text) if has_new_input else None
        if decision == "keep":
            return _build_renewal_update(
                state,
                schedule_state=schedule_state,
                renewal_stage="awaiting_end_date",
                phase="schedule_renewal",
                awaiting_user_input=True,
                current_count=current_count,
                last_text=last_text,
                prompt=_build_new_end_date_prompt(timezone_name),
            )
        if decision == "replace":
            return _build_renewal_update(
                state,
                schedule_state=schedule_state,
                renewal_stage="awaiting_rebuild_timing",
                phase="schedule_renewal",
                awaiting_user_input=True,
                current_count=current_count,
                last_text=last_text,
                prompt=_build_rebuild_timing_prompt(),
            )
        return _build_renewal_update(
            state,
            schedule_state=schedule_state,
            renewal_stage="awaiting_decision",
            phase="schedule_renewal",
            awaiting_user_input=True,
            current_count=current_count,
            last_text=last_text,
            prompt=_build_expired_schedule_prompt(persisted_profile),
        )

    if renewal_stage == "awaiting_end_date":
        parsed_end_date = parse_schedule_end_date(
            last_text,
            timezone_name=timezone_name,
        ) if has_new_input else None
        if parsed_end_date is None:
            return _build_renewal_update(
                state,
                schedule_state=schedule_state,
                renewal_stage="awaiting_end_date",
                phase="schedule_renewal",
                awaiting_user_input=True,
                current_count=current_count,
                last_text=last_text,
                prompt=_build_new_end_date_prompt(timezone_name),
            )

        update_result = get_schedule_service().update_schedule_end_date(
            schedule_profile_id=persisted_profile.id,
            schedule_end_date=parsed_end_date,
        )
        if not update_result.updated:
            return _build_renewal_update(
                state,
                schedule_state=schedule_state,
                renewal_stage="idle",
                phase="end",
                awaiting_user_input=False,
                current_count=current_count,
                last_text=last_text,
                prompt=(
                    "⚠️ Actualicé la conversación, pero no pude renovar la fecha "
                    "límite del horario.\n"
                    f"Detalle técnico: {update_result.detail or update_result.error_code or 'desconocido'}"
                ),
            )

        sync_result = get_outlook_fixed_schedule_sync_service().sync_schedule_profile(
            student_id=profile.get("persisted_student_id"),
            schedule_profile_id=persisted_profile.id,
            calendar_state=calendar_state,
            calendar_id=calendar_state.get("calendar_id"),
        )
        success_message = (
            "✅ Listo. Mantendré tu mismo horario fijo en Outlook "
            f"hasta el {format_schedule_end_date(parsed_end_date)}."
        )
        if not sync_result.synced:
            success_message = (
                "⚠️ Renové la fecha límite del horario en el sistema, "
                "pero no pude actualizar Outlook.\n"
                f"Detalle técnico: {sync_result.detail or sync_result.error_code or 'desconocido'}"
            )

        update_payload = _build_renewal_update(
            state,
            schedule_state=schedule_state,
            renewal_stage="idle",
            phase="end",
            awaiting_user_input=False,
            current_count=current_count,
            last_text=last_text,
            prompt=success_message,
            schedule_end_date=parsed_end_date.isoformat(),
            persisted_profile_id=persisted_profile.id,
        )
        if sync_result.synced:
            update_payload["calendar"] = {
                **calendar_state,
                "provider": "outlook",
                "authorized": True,
                "synced_event_map": dict(sync_result.synced_event_map),
            }
        return update_payload

    if renewal_stage == "awaiting_rebuild_timing":
        rebuild_timing = _parse_rebuild_timing(last_text) if has_new_input else None
        if rebuild_timing == "now":
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
                        "🛠️ Perfecto. Vamos a organizar un horario fijo nuevo desde cero.",
                    ),
                ),
            }
        if rebuild_timing == "later":
            return _build_renewal_update(
                state,
                schedule_state=schedule_state,
                renewal_stage="idle",
                phase="end",
                awaiting_user_input=False,
                current_count=current_count,
                last_text=last_text,
                prompt=(
                    "⏳ De acuerdo. Cuando quieras volver a organizar tu horario fijo, "
                    "me escribes y lo hacemos."
                ),
            )
        return _build_renewal_update(
            state,
            schedule_state=schedule_state,
            renewal_stage="awaiting_rebuild_timing",
            phase="schedule_renewal",
            awaiting_user_input=True,
            current_count=current_count,
            last_text=last_text,
            prompt=_build_rebuild_timing_prompt(),
        )

    return _build_renewal_update(
        state,
        schedule_state=schedule_state,
        renewal_stage="awaiting_decision",
        phase="schedule_renewal",
        awaiting_user_input=True,
        current_count=(
            current_count if has_new_input else state.get("user_message_count", 0)
        ),
        last_text=last_text if has_new_input else state.get("last_user_text"),
        prompt=_build_expired_schedule_prompt(persisted_profile),
    )


def _build_renewal_update(
    state: AgentState,
    *,
    schedule_state: object,
    renewal_stage: str,
    phase: str,
    awaiting_user_input: bool,
    current_count: int,
    last_text: str | None,
    prompt: str,
    schedule_end_date: str | None = None,
    persisted_profile_id: int | None = None,
) -> dict:
    schedule_changes: dict[str, object] = {
        "renewal_stage": renewal_stage,
    }
    if schedule_end_date is not None:
        schedule_changes["schedule_end_date"] = schedule_end_date
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


def _build_expired_schedule_prompt(profile) -> str:
    return (
        "⏰ Tu horario fijo llegó a su fecha límite en Outlook.\n"
        f"Fecha límite anterior: {format_schedule_end_date(profile.schedule_end_date)}\n\n"
        "¿Quieres seguir manteniendo estas actividades?\n"
        "(Escribe el número de la opción que quieres elegir)\n"
        "1. ✅ Sí, mantener el mismo horario\n"
        "2. ❌ No, prefiero cambiarlo"
    )


def _build_new_end_date_prompt(timezone_name: str = "America/Bogota") -> str:
    max_date = schedule_end_date_max_date(timezone_name)
    return (
        "📅 Perfecto. Voy a mantener tu mismo horario fijo.\n"
        "Envíame la nueva fecha límite para agendarlo en Outlook.\n"
        f"Debe ser una fecha futura y como máximo hasta el {format_schedule_end_date(max_date)} "
        f"(7 meses desde hoy).\n"
        "Escríbela en orden día-mes-año. Puedes usar espacios, / o -:\n"
        "  • DD MM AA  (ej: 30 06 26)\n"
        "  • DD/MM/AAAA  (ej: 30/06/2026)\n"
        "También acepto YYYY-MM-DD si lo prefieres."
    )


def _build_rebuild_timing_prompt() -> str:
    return (
        "🧭 Entendido. ¿Qué prefieres hacer ahora?\n"
        "(Escribe el número de la opción que quieres elegir)\n"
        "1. 🛠️ Organizar un horario fijo nuevo ahora\n"
        "2. ⏳ Dejarlo para luego"
    )


def _parse_renewal_decision(text: str | None) -> str | None:
    option = parse_numbered_option(text)
    if option == 1:
        return "keep"
    if option == 2:
        return "replace"
    normalized = normalize_text(text or "")
    if any(token in normalized for token in ("mantener", "mismo horario", "seguir")):
        return "keep"
    if any(token in normalized for token in ("cambiar", "nuevo horario")):
        return "replace"
    yes_no = parse_yes_no(text or "")
    if yes_no is True:
        return "keep"
    if yes_no is False:
        return "replace"
    return None


def _parse_rebuild_timing(text: str | None) -> str | None:
    option = parse_numbered_option(text)
    if option == 1:
        return "now"
    if option == 2:
        return "later"
    normalized = normalize_text(text or "")
    if any(token in normalized for token in ("ahora", "de una", "ya")):
        return "now"
    if any(token in normalized for token in ("luego", "despues", "después", "mas tarde", "más tarde")):
        return "later"
    return None


__all__ = [
    "handle_fixed_schedule_renewal_turn",
    "requires_fixed_schedule_renewal",
]
