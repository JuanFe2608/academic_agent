"""Nodo para solicitar el horario semanal según la ocupación."""

from __future__ import annotations

from agents.support.scheduling import merge_section_blocks, replace_section_blocks
from agents.support.scheduling.contextual_parser import (
    build_schedule_pending_prompt,
    complete_pending_schedule_item,
    serialize_blocks_for_schedule_type,
)
from agents.support.nodes.utils import (
    append_message,
    detect_new_input,
    normalize_text,
)
from agents.support.state import AgentState, PendingScheduleItem, RawInputs

from .prompt import (
    PROMPT_ACADEMICO,
    PROMPT_AMBOS,
    PROMPT_LABORAL,
    PROMPT_NINGUNA,
    PROMPT_OCCUPATION,
)


def request_schedules(state: AgentState) -> dict:
    """Solicita horarios académicos y/o laborales según ocupación."""
    messages = state.get("messages", [])
    has_new_input, last_text, current_count = detect_new_input(
        messages,
        state.get("user_message_count", 0),
        state.get("awaiting_user_input", False),
        state.get("last_user_text"),
    )
    raw_inputs = dict(state.get("raw_inputs", {}))
    schedule_state = dict(state.get("schedule", {}))
    profile = dict(state.get("student_profile", {}))
    occupation = profile.get("occupation")
    academic_pending_items = _coerce_pending_items(state.get("academic_pending_items", []))
    work_pending_items = _coerce_pending_items(state.get("work_pending_items", []))

    if has_new_input and last_text and (academic_pending_items or work_pending_items):
        pending_update = _consume_pending_schedule_reply(
            state,
            raw_inputs=raw_inputs,
            schedule_state=schedule_state,
            academic_pending_items=academic_pending_items,
            work_pending_items=work_pending_items,
            response_text=last_text,
            current_count=current_count,
        )
        if pending_update is not None:
            pending_update["student_profile"] = profile
            return pending_update

    if has_new_input and last_text:
        if not occupation:
            occupation = _parse_occupation(last_text)
            if occupation:
                profile["occupation"] = occupation
        else:
            raw_inputs = _consume_schedule_text_by_stage(raw_inputs, last_text, occupation)

    if not occupation:
        return {
            "student_profile": profile,
            "raw_inputs": raw_inputs,
            "schedule": schedule_state,
            "academic_pending_items": academic_pending_items,
            "work_pending_items": work_pending_items,
            "phase": "schedules",
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_text if has_new_input else state.get("last_user_text"),
            "awaiting_user_input": True,
            "messages": append_message(messages, "assistant", PROMPT_OCCUPATION),
        }

    if occupation == "ninguna":
        return {
            "student_profile": profile,
            "raw_inputs": raw_inputs,
            "schedule": schedule_state,
            "academic_pending_items": academic_pending_items,
            "work_pending_items": work_pending_items,
            "phase": "end",
            "awaiting_user_input": False,
            "messages": append_message(messages, "assistant", PROMPT_NINGUNA),
        }

    missing = _missing_schedule_inputs(raw_inputs, occupation)
    if missing:
        return {
            "student_profile": profile,
            "raw_inputs": raw_inputs,
            "schedule": schedule_state,
            "academic_pending_items": academic_pending_items,
            "work_pending_items": work_pending_items,
            "phase": "schedules",
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_text if has_new_input else state.get("last_user_text"),
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                _build_prompt_for_missing(missing, occupation),
            ),
        }

    return {
        "student_profile": profile,
        "raw_inputs": raw_inputs,
        "schedule": schedule_state,
        "academic_pending_items": academic_pending_items,
        "work_pending_items": work_pending_items,
        "phase": "schedules",
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_text if has_new_input else state.get("last_user_text"),
        "awaiting_user_input": False,
        "messages": append_message(
            messages, "assistant", "Gracias. Voy a procesar tus horarios."
        ),
    }


def _consume_schedule_text_by_stage(raw_inputs: RawInputs, text: str, occupation: str | None) -> RawInputs:
    """Consume texto segun el paso pendiente del flujo de horarios."""
    updated = dict(raw_inputs)
    clean_text = str(text or "").strip()
    if not clean_text:
        return updated

    if occupation == "solo_estudio":
        if not updated.get("horario_academico_text"):
            updated["horario_academico_text"] = clean_text
        return updated

    if occupation == "ambos":
        if not updated.get("horario_academico_text"):
            updated["horario_academico_text"] = clean_text
            return updated
        if not updated.get("horario_laboral_text"):
            updated["horario_laboral_text"] = clean_text
        return updated

    return updated


def _missing_schedule_inputs(raw_inputs: RawInputs, occupation: str | None) -> list[str]:
    missing: list[str] = []
    if occupation == "solo_estudio":
        if not raw_inputs.get("horario_academico_text"):
            missing.append("horario_academico_text")
        return missing

    if occupation == "ambos":
        if not raw_inputs.get("horario_academico_text"):
            missing.append("horario_academico_text")
        elif not raw_inputs.get("horario_laboral_text"):
            missing.append("horario_laboral_text")
    return missing


def _build_prompt_for_missing(missing: list[str], occupation: str | None) -> str:
    if not missing:
        return "Comparte tus horarios en texto."
    first = missing[0]
    if first == "horario_academico_text":
        return PROMPT_AMBOS if occupation == "ambos" else PROMPT_ACADEMICO
    if first == "horario_laboral_text":
        return PROMPT_LABORAL

    if occupation == "solo_estudio":
        return PROMPT_ACADEMICO
    if occupation == "ambos":
        return PROMPT_AMBOS
    return "Comparte tus horarios."


def _parse_occupation(text: str) -> str | None:
    normalized = normalize_text(text)
    if normalized in {"1", "solo estudio", "solo estudiar"} or normalized.startswith("1"):
        return "solo_estudio"
    if normalized in {"2", "ambos", "estudio y trabajo"} or normalized.startswith("2"):
        return "ambos"
    if normalized in {"3", "ninguna"} or normalized.startswith("3"):
        return "ninguna"
    return None


def _coerce_pending_items(
    raw_items: list[PendingScheduleItem] | list[dict],
) -> list[PendingScheduleItem]:
    return [
        item if isinstance(item, PendingScheduleItem) else PendingScheduleItem(**item)
        for item in raw_items
    ]


def _consume_pending_schedule_reply(
    state: AgentState,
    *,
    raw_inputs: RawInputs,
    schedule_state: dict,
    academic_pending_items: list[PendingScheduleItem],
    work_pending_items: list[PendingScheduleItem],
    response_text: str,
    current_count: int,
) -> dict | None:
    target = "academic" if academic_pending_items else "work"
    pending_items = academic_pending_items if academic_pending_items else work_pending_items
    if not pending_items:
        return None

    completed_blocks, _clarifications, updated_pending = complete_pending_schedule_item(
        response_text,
        pending_items[0],
        timezone=state.get("timezone", "America/Bogota"),
    )
    if updated_pending is not None:
        refreshed_items = [updated_pending] + pending_items[1:]
        return {
            "raw_inputs": raw_inputs,
            "schedule": schedule_state,
            "academic_pending_items": refreshed_items if target == "academic" else academic_pending_items,
            "work_pending_items": refreshed_items if target == "work" else work_pending_items,
            "phase": "schedules",
            "user_message_count": current_count,
            "last_user_text": response_text,
            "awaiting_user_input": True,
            "messages": append_message(
                state.get("messages", []),
                "assistant",
                build_schedule_pending_prompt(target, refreshed_items),
            ),
        }

    existing_blocks = list(schedule_state.get("blocks", []))
    current_section_blocks = [
        block
        for block in existing_blocks
        if str(block.get("block_type") if isinstance(block, dict) else block.block_type) == target
    ]
    merged_target_blocks = merge_section_blocks(current_section_blocks, completed_blocks)
    updated_blocks = replace_section_blocks(existing_blocks, target, merged_target_blocks)

    updated_raw_inputs = dict(raw_inputs)
    if target == "academic":
        updated_raw_inputs["horario_academico_text"] = serialize_blocks_for_schedule_type(
            merged_target_blocks,
            "academic",
        )
        academic_pending_items = pending_items[1:]
    else:
        updated_raw_inputs["horario_laboral_text"] = serialize_blocks_for_schedule_type(
            merged_target_blocks,
            "work",
        )
        work_pending_items = pending_items[1:]

    next_target, next_items = _next_pending_items(academic_pending_items, work_pending_items)
    if next_target is not None and next_items:
        return {
            "raw_inputs": updated_raw_inputs,
            "schedule": {**schedule_state, "blocks": updated_blocks},
            "academic_pending_items": academic_pending_items,
            "work_pending_items": work_pending_items,
            "phase": "schedules",
            "user_message_count": current_count,
            "last_user_text": response_text,
            "awaiting_user_input": True,
            "messages": append_message(
                state.get("messages", []),
                "assistant",
                build_schedule_pending_prompt(next_target, next_items),
            ),
        }

    return {
        "raw_inputs": updated_raw_inputs,
        "schedule": {**schedule_state, "blocks": updated_blocks},
        "academic_pending_items": academic_pending_items,
        "work_pending_items": work_pending_items,
        "phase": "schedules",
        "user_message_count": current_count,
        "last_user_text": response_text,
        "awaiting_user_input": False,
        "messages": append_message(
            state.get("messages", []),
            "assistant",
            "Gracias. Voy a procesar tus horarios.",
        ),
    }


def _next_pending_items(
    academic_pending_items: list[PendingScheduleItem],
    work_pending_items: list[PendingScheduleItem],
) -> tuple[str | None, list[PendingScheduleItem]]:
    if academic_pending_items:
        return "academic", academic_pending_items
    if work_pending_items:
        return "work", work_pending_items
    return None, []
