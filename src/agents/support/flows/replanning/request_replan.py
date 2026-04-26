"""Flujo conversacional para replanificacion controlada."""

from __future__ import annotations

from agents.support.dependencies import get_study_replanning_service
from agents.support.flows.planning.persistence_support import persist_planning_snapshot_for_update
from agents.support.nodes.utils import append_message, detect_new_input, parse_yes_no
from agents.support.scheduling.state_helpers import ensure_schedule_flow_state
from agents.support.state import AgentState
from bootstrap.errors import RepositoryConfigurationError
from services.conversation.state_helpers import ensure_interaction_state, update_interaction_state
from services.planning import StudyReplanningService, is_replan_request_message

_REPLAN_DOMAIN = "replanning"


def handle_replan_turn(state: AgentState) -> dict:
    """Genera, confirma o aplica una propuesta de replanificacion."""

    messages = state.get("messages", [])
    has_new_input, last_text, current_count = detect_new_input(
        messages,
        state.get("user_message_count", 0),
        state.get("awaiting_user_input", False),
        state.get("last_user_text"),
    )
    replan = _as_dict(state.get("replan", {}))
    interaction = ensure_interaction_state(state)

    if _is_awaiting_replan_confirmation(interaction, replan):
        if not has_new_input:
            return {
                "phase": "running",
                "awaiting_user_input": True,
                "replan": replan,
            }
        return _handle_confirmation(
            state,
            replan=replan,
            last_text=last_text,
            current_count=current_count,
        )

    explicit_text = last_text if has_new_input and is_replan_request_message(last_text) else None
    if not _has_replan_candidate(replan) and not explicit_text:
        return {
            "phase": "end",
            "awaiting_user_input": False,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_text if has_new_input else state.get("last_user_text"),
        }

    return _build_proposal_update(
        state,
        replan=replan,
        explicit_text=explicit_text,
        last_text=last_text,
        current_count=current_count,
        has_new_input=has_new_input,
    )


def _build_proposal_update(
    state: AgentState,
    *,
    replan: dict[str, object],
    explicit_text: str | None,
    last_text: str,
    current_count: int,
    has_new_input: bool,
) -> dict:
    messages = state.get("messages", [])
    service = _replanning_service()
    schedule_state = ensure_schedule_flow_state(state.get("schedule", {}))
    result = service.propose_replan(
        student_id=_student_id(state),
        current_study_plan=state.get("study_plan", {}),
        schedule_blocks=list(schedule_state.blocks),
        subjects=list(state.get("subjects", [])),
        academic_activities=list(state.get("academic_activities", [])),
        study_profile=state.get("study_profile", {}),
        constraints=state.get("constraints", {}),
        timezone=state.get("timezone", "America/Bogota"),
        replan_state=replan,
        explicit_request_text=explicit_text,
    )
    if not result.proposed:
        updated_replan = _closed_replan_state(
            replan,
            status="no_changes" if result.no_changes else "failed",
            applied_payload={
                "reason_text": result.reason_text,
                "error_code": result.error_code,
                "detail": result.detail,
                "impact": result.impact_payload,
            },
        )
        return {
            "phase": "end",
            "awaiting_user_input": False,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_text if has_new_input else state.get("last_user_text"),
            "messages": append_message(messages, "assistant", result.prompt_text),
            "replan": updated_replan,
            **_clear_interaction(state),
        }

    updated_replan = dict(replan)
    updated_replan.update(
        {
            "status": "proposed",
            "trigger": result.request_payload.get("trigger"),
            "request": result.request_payload,
            "active_proposal": result.proposal_payload,
            "pending_prompt": result.prompt_text,
        }
    )
    return {
        "phase": "running",
        "awaiting_user_input": True,
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_text if has_new_input else state.get("last_user_text"),
        "messages": append_message(messages, "assistant", result.prompt_text),
        "replan": updated_replan,
        **_confirmation_interaction(state, updated_replan),
    }


def _handle_confirmation(
    state: AgentState,
    *,
    replan: dict[str, object],
    last_text: str,
    current_count: int,
) -> dict:
    messages = state.get("messages", [])
    decision = parse_yes_no(last_text)
    if decision is None:
        prompt = str(replan.get("pending_prompt") or "Responde si o no para aplicar la replanificacion.")
        return {
            "phase": "running",
            "awaiting_user_input": True,
            "user_message_count": current_count,
            "last_user_text": last_text,
            "messages": append_message(messages, "assistant", prompt),
            "replan": replan,
            **_confirmation_interaction(state, replan),
        }
    service = _replanning_service()
    if decision is False:
        service.reject_replan(_as_dict(replan.get("request", {})))
        updated_replan = _closed_replan_state(
            replan,
            status="rejected",
            applied_payload={"reason": "student_rejected"},
        )
        return {
            "phase": "end",
            "awaiting_user_input": False,
            "user_message_count": current_count,
            "last_user_text": last_text,
            "messages": append_message(messages, "assistant", "Listo, no aplique la replanificacion."),
            "replan": updated_replan,
            **_clear_interaction(state),
        }
    return _apply_confirmed_replan(
        state,
        replan=replan,
        service=service,
        last_text=last_text,
        current_count=current_count,
    )


def _apply_confirmed_replan(
    state: AgentState,
    *,
    replan: dict[str, object],
    service: StudyReplanningService,
    last_text: str,
    current_count: int,
) -> dict:
    messages = state.get("messages", [])
    proposal = _as_dict(replan.get("active_proposal", {}))
    study_plan = _as_dict(proposal.get("study_plan", {}))
    if not study_plan:
        updated_replan = _closed_replan_state(
            replan,
            status="failed",
            applied_payload={"error_code": "missing_active_proposal"},
        )
        return {
            "phase": "end",
            "awaiting_user_input": False,
            "user_message_count": current_count,
            "last_user_text": last_text,
            "messages": append_message(
                messages,
                "assistant",
                "No encontre una propuesta activa para aplicar. Mantengo el plan actual.",
            ),
            "replan": updated_replan,
            **_clear_interaction(state),
        }

    update = {
        "subjects": list(proposal.get("subjects") or state.get("subjects", [])),
        "study_plan": study_plan,
        "phase": "end",
        "awaiting_user_input": False,
    }
    persisted_update = persist_planning_snapshot_for_update(state, update)
    resulting_plan_id = _study_plan_profile_id(persisted_update.get("study_plan"))
    service.mark_applied(
        proposal_payload=proposal,
        resulting_study_plan_profile_id=resulting_plan_id,
    )
    applied_payload = {
        "summary_text": proposal.get("summary_text"),
        "impact": proposal.get("impact"),
        "previous_study_plan_profile_id": proposal.get("current_study_plan_profile_id"),
        "new_study_plan_profile_id": resulting_plan_id,
        "replan_request_id": proposal.get("replan_request_id"),
        "replan_proposal_id": proposal.get("replan_proposal_id"),
        "proposal_number": proposal.get("proposal_number"),
    }
    persisted_update.update(
        {
            "phase": "end",
            "awaiting_user_input": False,
            "user_message_count": current_count,
            "last_user_text": last_text,
            "messages": append_message(
                messages,
                "assistant",
                _applied_message(applied_payload, persisted_update),
            ),
            "replan": _closed_replan_state(
                replan,
                status="applied",
                applied_payload=applied_payload,
            ),
            **_clear_interaction(state),
        }
    )
    return persisted_update


def _applied_message(applied_payload: dict[str, object], update: dict[str, object]) -> str:
    old_id = applied_payload.get("previous_study_plan_profile_id")
    new_id = applied_payload.get("new_study_plan_profile_id")
    version_text = (
        f" Version anterior: {old_id}; nueva version: {new_id}."
        if old_id and new_id
        else " La propuesta quedo aplicada en el estado actual."
    )
    study_plan = _as_dict(update.get("study_plan", {}))
    materialized = study_plan.get("materialized_instance_count")
    reminders = _as_dict(update.get("reminders", {}))
    reminder_count = reminders.get("created_dispatch_count")
    operations: list[str] = []
    if materialized is not None:
        operations.append(f"instancias reconciliadas: {materialized}")
    if reminder_count is not None:
        operations.append(f"recordatorios nuevos: {reminder_count}")
    suffix = f" {'; '.join(operations)}." if operations else ""
    return f"Listo, aplique la replanificacion.{version_text}{suffix}"


def _has_replan_candidate(replan: dict[str, object]) -> bool:
    return bool(replan.get("trigger") or replan.get("change_request"))


def _is_awaiting_replan_confirmation(interaction, replan: dict[str, object]) -> bool:
    payload = _as_dict(interaction.last_confirmation_payload or {})
    return bool(
        interaction.confirmation_pending
        and payload.get("domain") == _REPLAN_DOMAIN
        and replan.get("active_proposal")
    )


def _confirmation_interaction(state: AgentState, replan: dict[str, object]) -> dict[str, object]:
    payload = {
        "domain": _REPLAN_DOMAIN,
        "operation": "apply_replan",
        "request": _as_dict(replan.get("request", {})),
        "proposal": _as_dict(replan.get("active_proposal", {})),
    }
    return update_interaction_state(
        state,
        active_intent="request_replan",
        active_subflow="replan",
        current_domain=_REPLAN_DOMAIN,
        interaction_mode="confirmation",
        pending_action="confirm_replan",
        pending_entity_type="study_plan",
        pending_entity_payload=payload,
        missing_fields_json=[],
        confirmation_pending=True,
        last_confirmation_payload=payload,
        clarification_needed=False,
        current_step="awaiting_replan_confirmation",
        current_section="replanning",
    )


def _clear_interaction(state: AgentState) -> dict[str, object]:
    return update_interaction_state(
        state,
        active_intent=None,
        active_subflow=None,
        current_domain=_REPLAN_DOMAIN,
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


def _closed_replan_state(
    replan: dict[str, object],
    *,
    status: str,
    applied_payload: dict[str, object],
) -> dict[str, object]:
    updated = dict(replan)
    updated.update(
        {
            "status": status,
            "trigger": None,
            "request": None,
            "change_request": None,
            "active_proposal": None,
            "applied_payload": applied_payload,
            "pending_prompt": None,
            "selected_index": None,
            "return_to_menu": None,
        }
    )
    return updated


def _replanning_service() -> StudyReplanningService:
    try:
        return get_study_replanning_service()
    except RepositoryConfigurationError:
        return StudyReplanningService(repository=None)


def _student_id(state: AgentState) -> int | None:
    profile = _as_dict(state.get("student_profile", {}))
    value = profile.get("persisted_student_id")
    try:
        return int(value) if value else None
    except (TypeError, ValueError):
        return None


def _study_plan_profile_id(value: object) -> int | None:
    data = _as_dict(value)
    try:
        raw_value = data.get("persisted_profile_id")
        return int(raw_value) if raw_value else None
    except (TypeError, ValueError):
        return None


def _as_dict(value: object) -> dict[str, object]:
    if hasattr(value, "model_dump"):
        return dict(value.model_dump(mode="python"))
    if isinstance(value, dict):
        return dict(value)
    return {}


__all__ = ["handle_replan_turn"]
