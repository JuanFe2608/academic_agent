"""Servicio de aplicación para captura conversacional de prioridades."""

from __future__ import annotations

from agents.support.nodes.utils import append_message, detect_new_input
from agents.support.priorities.config import load_priorities_config
from agents.support.priorities.formatter import (
    build_priorities_invalid_prompt,
    build_priorities_processing_message,
    build_priorities_prompt,
)
from agents.support.priorities.parser import parse_subject_catalog
from agents.support.scheduling.state_helpers import ensure_schedule_flow_state
from agents.support.state import AgentState
from services.priorities import (
    resolve_prioritized_subjects,
    subject_items_to_update,
    update_priorities_state,
)


def handle_priorities_turn(state: AgentState) -> dict:
    """Coordina el subflujo de captura manual o confirmación de materias."""

    messages = state.get("messages", [])
    has_new_input, last_text, current_count = detect_new_input(
        messages,
        state.get("user_message_count", 0),
        state.get("awaiting_user_input", False),
        state.get("last_user_text"),
    )
    config = load_priorities_config()
    schedule_state = ensure_schedule_flow_state(state.get("schedule", {}))
    study_profile = dict(state.get("study_profile", {}))
    priorities = resolve_prioritized_subjects(
        schedule_blocks=list(schedule_state.blocks),
        subjects=list(state.get("subjects", [])),
        primary_technique_id=_primary_technique_id(study_profile),
    )
    current_subjects = subject_items_to_update(priorities.subject_items)

    if not has_new_input:
        return {
            "subjects": current_subjects,
            "priorities": update_priorities_state(
                state.get("priorities", {}),
                status="collecting",
                prompt_version=config.prompt_version,
                source=priorities.source,
                last_error=None,
            ),
            "phase": "priorities",
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                build_priorities_prompt(priorities.subject_items, source=priorities.source),
            ),
        }

    command = _normalize_command(last_text)
    if command == "omitir":
        return {
            "subjects": current_subjects,
            "priorities": update_priorities_state(
                state.get("priorities", {}),
                status="skipped",
                prompt_version=config.prompt_version,
                source=priorities.source,
                last_error=None,
            ),
            "phase": "end",
            "user_message_count": current_count,
            "last_user_text": last_text,
            "awaiting_user_input": False,
            "messages": append_message(
                messages,
                "assistant",
                "Perfecto. Dejamos el ajuste fino de prioridades para la siguiente iteración.",
            ),
        }

    if command == "usar_horario":
        return {
            "subjects": current_subjects,
            "priorities": update_priorities_state(
                state.get("priorities", {}),
                status="completed",
                prompt_version=config.prompt_version,
                source=priorities.source,
                last_error=None,
            ),
            "phase": "study_plan",
            "user_message_count": current_count,
            "last_user_text": last_text,
            "awaiting_user_input": False,
            "messages": append_message(
                messages,
                "assistant",
                build_priorities_processing_message(priorities.subject_items),
            ),
        }

    parsed = parse_subject_catalog(last_text or "")
    if not parsed.is_valid:
        return {
            "subjects": current_subjects,
            "priorities": update_priorities_state(
                state.get("priorities", {}),
                status="collecting",
                prompt_version=config.prompt_version,
                source=priorities.source,
                last_error=parsed.error,
            ),
            "phase": "priorities",
            "user_message_count": current_count,
            "last_user_text": last_text,
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                build_priorities_invalid_prompt(
                    parsed.error or "No pude procesar tus materias.",
                    priorities.subject_items,
                    source=priorities.source,
                ),
            ),
        }

    normalized_manual = resolve_prioritized_subjects(
        schedule_blocks=list(schedule_state.blocks),
        subjects=parsed.subjects,
        primary_technique_id=_primary_technique_id(study_profile),
    )
    return {
        "subjects": subject_items_to_update(normalized_manual.subject_items),
        "priorities": update_priorities_state(
            state.get("priorities", {}),
            status="completed",
            prompt_version=config.prompt_version,
            source="manual",
            last_error=None,
        ),
        "phase": "study_plan",
        "user_message_count": current_count,
        "last_user_text": last_text,
        "awaiting_user_input": False,
        "messages": append_message(
            messages,
            "assistant",
            build_priorities_processing_message(normalized_manual.subject_items),
        ),
    }


def _primary_technique_id(study_profile: dict) -> str | None:
    techniques = list(study_profile.get("top_techniques") or [])
    return str(techniques[0]) if techniques else None


def _normalize_command(text: str | None) -> str:
    normalized = " ".join(str(text or "").strip().lower().split())
    if normalized in {
        "usar horario",
        "usar el horario",
        "usar materias detectadas",
        "usar lo detectado",
    }:
        return "usar_horario"
    if normalized in {"omitir", "mas tarde", "más tarde", "despues", "después", "skip"}:
        return "omitir"
    return normalized
