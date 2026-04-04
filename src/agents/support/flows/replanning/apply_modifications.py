"""Orquestador del flujo de replanificacion para aplicar modificaciones."""

from __future__ import annotations

from agents.support.nodes.utils import append_message, detect_new_input
from agents.support.state import AgentState

from ._delete_flow import apply_delete_change
from ._direct_changes import (
    apply_academic_change,
    apply_activity_additions,
    apply_extracurricular_change,
    apply_laboral_change,
)
from ._shared import ReplanTurnContext, build_prompt_update, build_validate_update
from ._update_flow import handle_activity_update


def apply_modifications(state: AgentState) -> dict:
    """Aplica cambios a horarios laborales, academicos y actividades."""

    messages = state.get("messages", [])
    has_new_input, last_text, current_count = detect_new_input(
        messages,
        state.get("user_message_count", 0),
        state.get("awaiting_user_input", False),
        state.get("last_user_text"),
    )
    last_user_text_value = last_text if has_new_input else state.get("last_user_text")
    replan = dict(state.get("replan", {}))
    change_request = dict(replan.get("change_request") or {})

    target = change_request.get("target")
    operation = str(change_request.get("operation") or "update").strip().lower()
    activity_name = str(change_request.get("activity_name") or "").strip()
    stage = str(change_request.get("stage") or "").strip()
    if has_new_input and stage:
        details = str(last_text or "").strip()
    else:
        details = (change_request.get("details") or "").strip() or (last_text if has_new_input else "")

    ctx = ReplanTurnContext(
        previous_user_message_count=state.get("user_message_count", 0),
        current_count=current_count,
        has_new_input=has_new_input,
        last_user_text_value=last_user_text_value,
    )

    if target == "delete":
        return apply_delete_change(state, details, replan, ctx)
    if target == "activity":
        return apply_activity_additions(state, details, replan, ctx)
    if operation == "update" and target in {"academico", "laboral", "extracurricular", "activity_lookup"}:
        return handle_activity_update(state, target, activity_name, details, replan, ctx)
    if target == "horario":
        return build_prompt_update(
            ctx,
            replan,
            "Aclara si deseas cambiar el horario academico o el laboral. Usa la tabla anterior como referencia.",
        )
    if target == "laboral":
        return apply_laboral_change(state, details, operation, replan, ctx)
    if target == "academico":
        return apply_academic_change(state, details, operation, replan, ctx)
    if target == "extracurricular":
        return apply_extracurricular_change(state, details, operation, activity_name, replan, ctx)

    return build_validate_update(
        ctx,
        awaiting_user_input=True,
        messages=append_message(
            messages,
            "assistant",
            "Por ahora solo puedo modificar horario o actividades extracurriculares.",
        ),
    )


__all__ = ["apply_modifications"]
