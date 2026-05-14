"""Confirmación y edición guiada por bloque para secciones del horario."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from agents.support.nodes.utils import (
    append_message,
    normalize_text,
    parse_numbered_option,
    parse_yes_no,
)
from agents.support.runtime_state_helpers import update_conversation_state
from agents.support.scheduling import normalize_schedule_section
from agents.support.scheduling.conflicts import detect_schedule_conflicts
from agents.support.scheduling.pipeline import parse_extracurricular_section
from agents.support.scheduling.render import build_rendered_schedule_message_content
from agents.support.scheduling.state_helpers import (
    ensure_schedule_flow_state,
    update_scheduling_state,
    update_schedule_flow_state,
)
from agents.support.state import AgentState
from services.scheduling.block_operations import (
    current_section_blocks,
    replace_section_blocks,
)
from services.scheduling.constants import DAY_LABELS, DAY_ORDER, ScheduleBlockType
from services.scheduling.extracurricular_state import (
    build_extracurricular_items_from_blocks,
)
from services.scheduling.heuristic_schedule_parsing import extract_time_range
from services.scheduling.models import WeeklyScheduleBlock, ensure_weekly_block
from services.scheduling.raw_input_sync import sync_schedule_blocks_to_raw_inputs
from services.scheduling.validation import normalize_day, normalize_time

_SECTION_REVIEW_STAGES = {
    "section_awaiting_confirmation",
    "section_awaiting_item_selection",
    "section_awaiting_field_selection",
    "section_awaiting_field_value",
    "section_awaiting_item_confirmation",
    "section_awaiting_add_payload",
    "section_awaiting_replace_all_payload",
}
_SECTION_LABELS = {
    "academic": "horario académico",
    "work": "horario laboral",
    "extracurricular": "horario extracurricular",
}
_HEADER_EMOJIS = {
    "academic": "📚",
    "work": "💼",
    "extracurricular": "🎯",
}
_ITEM_LABELS = {
    "academic": "materia",
    "work": "bloque",
    "extracurricular": "actividad",
}
_TYPE_LABELS = {
    "academic": "académico",
    "work": "laboral",
    "extracurricular": "extracurricular",
}
_OPTION_HINT = "(Escribe el número de la opción que quieres elegir)"
_ITEM_HINT = "(Escribe el número del registro que quieres editar)"
_FIELD_HINT = "(Escribe el número del cambio que quieres hacer)"
_ADD_TYPE_LABELS = {
    "academic": "académicas",
    "work": "laborales",
    "extracurricular": "extracurriculares",
}
_DAY_OPTIONS: dict[int, str] = {
    1: "monday",
    2: "tuesday",
    3: "wednesday",
    4: "thursday",
    5: "friday",
    6: "saturday",
    7: "sunday",
}
_DAY_BY_NORMALIZED_LABEL = {
    normalize_text(label): day for day, label in DAY_LABELS.items()
}
_FIELD_OPTIONS = {
    1: "title",
    2: "day_of_week",
    3: "time_range",
}


@dataclass(frozen=True)
class SectionReviewCompletion:
    """Describe cómo debe continuar el flujo al confirmar una sección."""

    phase: str
    awaiting_user_input: bool
    prompt: str | None = None
    schedule_changes: dict[str, object] = field(default_factory=dict)
    scheduling_changes: dict[str, object] = field(default_factory=dict)
    after_change_phase: str | None = None
    after_change_awaiting_user_input: bool | None = None
    after_change_prompt: str | None = None


def has_active_section_review(state: AgentState | dict | None) -> bool:
    """Indica si hay una confirmación/edición por bloque en curso."""

    schedule_state = ensure_schedule_flow_state(
        state.get("schedule", {}) if hasattr(state, "get") else state
    )
    return str(schedule_state.review_stage or "") in _SECTION_REVIEW_STAGES


def start_section_review(
    state: AgentState,
    *,
    target: ScheduleBlockType,
    phase: str,
    current_count: int,
    last_text: str | None,
    initial_stage: str = "section_awaiting_confirmation",
) -> dict:
    """Abre la confirmación guiada de una sección ya capturada."""

    schedule_state = ensure_schedule_flow_state(state.get("schedule", {}))
    return _build_section_review_update(
        state,
        schedule=update_schedule_flow_state(
            schedule_state,
            review_stage=initial_stage,
            correction_target=target,
            editing_block_id=None,
            editing_block_ids=[],
            editing_field=None,
            pending_correction_text=None,
        ),
        phase=phase,
        current_count=current_count,
        last_text=last_text,
        awaiting_user_input=True,
        prompt=_build_entry_prompt(schedule_state.blocks, target, initial_stage),
        render_preview_blocks=schedule_state.blocks,
    )


def handle_section_review_turn(
    state: AgentState,
    *,
    has_new_input: bool,
    last_text: str | None,
    current_count: int,
    completion: SectionReviewCompletion,
) -> dict:
    """Procesa un turno de confirmación/edición guiada por bloque."""

    schedule_state = ensure_schedule_flow_state(state.get("schedule", {}))
    target = str(schedule_state.correction_target or "").strip()
    if target not in _SECTION_LABELS:
        return _build_section_review_update(
            state,
            schedule=update_schedule_flow_state(
                schedule_state,
                review_stage="idle",
                correction_target=None,
                editing_block_id=None,
                editing_field=None,
                pending_correction_text=None,
            ),
            phase=completion.phase,
            current_count=current_count if has_new_input else state.get("user_message_count", 0),
            last_text=last_text if has_new_input else state.get("last_user_text"),
            awaiting_user_input=completion.awaiting_user_input,
            prompt=completion.prompt,
            **completion.scheduling_changes,
        )

    if schedule_state.review_stage == "section_awaiting_confirmation":
        decision = _parse_two_option_choice(last_text) if has_new_input else None
        if decision == 1:
            return _complete_section_review(
                state,
                schedule_state=schedule_state,
                completion=completion,
                current_count=current_count,
                last_text=last_text,
            )
        if decision == 2:
            return _build_section_review_update(
                state,
                schedule=update_schedule_flow_state(
                    schedule_state,
                    review_stage="section_awaiting_item_selection",
                ),
                phase=state.get("phase", "schedules"),
                current_count=current_count if has_new_input else state.get("user_message_count", 0),
                last_text=last_text if has_new_input else state.get("last_user_text"),
                awaiting_user_input=True,
                prompt=_build_item_selection_prompt(schedule_state.blocks, target),  # type: ignore[arg-type]
                render_preview_blocks=schedule_state.blocks,
            )
        return _build_section_review_update(
            state,
            schedule=update_schedule_flow_state(schedule_state),
            phase=state.get("phase", "schedules"),
            current_count=current_count if has_new_input else state.get("user_message_count", 0),
            last_text=last_text if has_new_input else state.get("last_user_text"),
            awaiting_user_input=True,
            prompt=_build_invalid_choice_prompt(schedule_state.blocks, target),  # type: ignore[arg-type]
            render_preview_blocks=schedule_state.blocks,
        )

    if schedule_state.review_stage == "section_awaiting_item_selection":
        if has_new_input and _is_cancel_command(last_text):
            return _build_section_review_update(
                state,
                schedule=update_schedule_flow_state(
                    schedule_state,
                    review_stage="section_awaiting_confirmation",
                    editing_block_id=None,
                    editing_block_ids=[],
                    editing_field=None,
                    pending_correction_text=None,
                ),
                phase=state.get("phase", "schedules"),
                current_count=current_count,
                last_text=last_text,
                awaiting_user_input=True,
                prompt=_build_cancel_selection_prompt(schedule_state.blocks, target),  # type: ignore[arg-type]
                render_preview_blocks=schedule_state.blocks,
            )
        if has_new_input and _is_add_command(last_text):
            return _build_section_review_update(
                state,
                schedule=update_schedule_flow_state(
                    schedule_state,
                    review_stage="section_awaiting_add_payload",
                    editing_block_id=None,
                    editing_block_ids=[],
                    editing_field=None,
                    pending_correction_text=None,
                ),
                phase=state.get("phase", "schedules"),
                current_count=current_count,
                last_text=last_text,
                awaiting_user_input=True,
                prompt=_build_add_payload_prompt(target),  # type: ignore[arg-type]
            )
        selected_blocks = (
            _parse_selected_blocks(schedule_state.blocks, target, last_text)  # type: ignore[arg-type]
            if has_new_input
            else []
        )
        if selected_blocks:
            selected_ids = [block.block_id for block in selected_blocks]
            return _build_section_review_update(
                state,
                schedule=update_schedule_flow_state(
                    schedule_state,
                    review_stage="section_awaiting_field_selection",
                    editing_block_id=selected_ids[0],
                    editing_block_ids=selected_ids,
                    editing_field=None,
                ),
                phase=state.get("phase", "schedules"),
                current_count=current_count,
                last_text=last_text,
                awaiting_user_input=True,
                prompt=_build_field_selection_prompt_for_selection(target, selected_blocks),  # type: ignore[arg-type]
            )
        return _build_section_review_update(
            state,
            schedule=update_schedule_flow_state(schedule_state),
            phase=state.get("phase", "schedules"),
            current_count=current_count if has_new_input else state.get("user_message_count", 0),
            last_text=last_text if has_new_input else state.get("last_user_text"),
            awaiting_user_input=True,
            prompt=_build_invalid_item_prompt(schedule_state.blocks, target),  # type: ignore[arg-type]
            render_preview_blocks=schedule_state.blocks,
        )

    if schedule_state.review_stage == "section_awaiting_field_selection":
        selected_block_ids = _active_editing_block_ids(schedule_state)
        selected_blocks = _find_selected_blocks(schedule_state.blocks, selected_block_ids)
        is_multi_selection = len(selected_blocks) > 1
        choice = (
            _parse_field_choice(last_text, allow_replace_all=not is_multi_selection)
            if has_new_input
            else None
        )
        if choice == "delete":
            delete_result = _apply_blocks_delete(
                state,
                target=target,  # type: ignore[arg-type]
                block_ids=selected_block_ids,
            )
            if delete_result.error_prompt is not None:
                return _build_section_review_update(
                    state,
                    schedule=update_schedule_flow_state(schedule_state),
                    phase=state.get("phase", "schedules"),
                    current_count=current_count if has_new_input else state.get("user_message_count", 0),
                    last_text=last_text if has_new_input else state.get("last_user_text"),
                    awaiting_user_input=True,
                    prompt=delete_result.error_prompt,
                )
            if completion.after_change_phase is not None:
                return _complete_after_section_change(
                    state,
                    schedule=update_schedule_flow_state(
                        schedule_state,
                        blocks=delete_result.blocks,
                        conflicts=delete_result.conflicts,
                        conflicts_accepted=False,
                        summary_text=None,
                        review_stage="idle",
                        correction_target=None,
                        editing_block_id=None,
                        editing_block_ids=[],
                        editing_field=None,
                        pending_correction_text=None,
                    ),
                    completion=completion,
                    current_count=current_count if has_new_input else state.get("user_message_count", 0),
                    last_text=last_text if has_new_input else state.get("last_user_text"),
                    **delete_result.scheduling_changes,
                )
            return _build_section_review_update(
                state,
                schedule=update_schedule_flow_state(
                    schedule_state,
                    blocks=delete_result.blocks,
                    conflicts=delete_result.conflicts,
                    conflicts_accepted=False,
                    summary_text=None,
                    review_stage="section_awaiting_confirmation",
                    correction_target=target,
                    editing_block_id=None,
                    editing_block_ids=[],
                    editing_field=None,
                    pending_correction_text=None,
                ),
                phase=state.get("phase", "schedules"),
                current_count=current_count if has_new_input else state.get("user_message_count", 0),
                last_text=last_text if has_new_input else state.get("last_user_text"),
                awaiting_user_input=True,
                prompt=_build_delete_result_prompt(
                    target,  # type: ignore[arg-type]
                    delete_result.blocks,
                ),
                render_preview_blocks=delete_result.blocks,
                **delete_result.scheduling_changes,
            )
        if choice == "cancel":
            return _build_section_review_update(
                state,
                schedule=update_schedule_flow_state(
                    schedule_state,
                    review_stage="section_awaiting_confirmation",
                    editing_block_id=None,
                    editing_block_ids=[],
                    editing_field=None,
                ),
                phase=state.get("phase", "schedules"),
                current_count=current_count if has_new_input else state.get("user_message_count", 0),
                last_text=last_text if has_new_input else state.get("last_user_text"),
                awaiting_user_input=True,
                prompt=_build_section_confirmation_prompt(schedule_state.blocks, target),  # type: ignore[arg-type]
                render_preview_blocks=schedule_state.blocks,
            )
        if choice == "replace_all":
            selected_block = selected_blocks[0] if len(selected_blocks) == 1 else None
            if selected_block is None:
                return _build_section_review_update(
                    state,
                    schedule=update_schedule_flow_state(
                        schedule_state,
                        review_stage="section_awaiting_item_selection",
                        editing_block_id=None,
                        editing_block_ids=[],
                        editing_field=None,
                    ),
                    phase=state.get("phase", "schedules"),
                    current_count=current_count if has_new_input else state.get("user_message_count", 0),
                    last_text=last_text if has_new_input else state.get("last_user_text"),
                    awaiting_user_input=True,
                    prompt=_build_item_selection_prompt(schedule_state.blocks, target),  # type: ignore[arg-type]
                    render_preview_blocks=schedule_state.blocks,
                )
            return _build_section_review_update(
                state,
                schedule=update_schedule_flow_state(
                    schedule_state,
                    review_stage="section_awaiting_replace_all_payload",
                    editing_field=None,
                ),
                phase=state.get("phase", "schedules"),
                current_count=current_count if has_new_input else state.get("user_message_count", 0),
                last_text=last_text if has_new_input else state.get("last_user_text"),
                awaiting_user_input=True,
                prompt=_build_replace_all_payload_prompt(target, selected_block),  # type: ignore[arg-type]
            )
        if choice in {"title", "day_of_week", "time_range"}:
            if not selected_blocks:
                return _build_section_review_update(
                    state,
                    schedule=update_schedule_flow_state(
                        schedule_state,
                        review_stage="section_awaiting_item_selection",
                        editing_block_id=None,
                        editing_block_ids=[],
                        editing_field=None,
                    ),
                    phase=state.get("phase", "schedules"),
                    current_count=current_count if has_new_input else state.get("user_message_count", 0),
                    last_text=last_text if has_new_input else state.get("last_user_text"),
                    awaiting_user_input=True,
                    prompt=_build_item_selection_prompt(schedule_state.blocks, target),  # type: ignore[arg-type]
                    render_preview_blocks=schedule_state.blocks,
                )
            return _build_section_review_update(
                state,
                schedule=update_schedule_flow_state(
                    schedule_state,
                    review_stage="section_awaiting_field_value",
                    editing_field=choice,
                ),
                phase=state.get("phase", "schedules"),
                current_count=current_count,
                last_text=last_text,
                awaiting_user_input=True,
                prompt=_build_field_value_prompt_for_selection(target, selected_blocks, choice),  # type: ignore[arg-type]
            )
        return _build_section_review_update(
            state,
            schedule=update_schedule_flow_state(schedule_state),
            phase=state.get("phase", "schedules"),
            current_count=current_count if has_new_input else state.get("user_message_count", 0),
            last_text=last_text if has_new_input else state.get("last_user_text"),
            awaiting_user_input=True,
            prompt=_build_invalid_field_prompt_for_selection(target, selected_blocks),  # type: ignore[arg-type]
        )

    if schedule_state.review_stage == "section_awaiting_field_value":
        selected_block_ids = _active_editing_block_ids(schedule_state)
        selected_blocks = _find_selected_blocks(schedule_state.blocks, selected_block_ids)
        if not has_new_input or not str(last_text or "").strip():
            return _build_section_review_update(
                state,
                schedule=update_schedule_flow_state(schedule_state),
                phase=state.get("phase", "schedules"),
                current_count=state.get("user_message_count", 0),
                last_text=state.get("last_user_text"),
                awaiting_user_input=True,
                prompt=_build_field_value_prompt_for_selection(
                    target,  # type: ignore[arg-type]
                    selected_blocks,
                    str(schedule_state.editing_field or ""),
                ),
            )
        edit_result = _apply_blocks_edit(
            state,
            target=target,  # type: ignore[arg-type]
            block_ids=selected_block_ids,
            field_name=str(schedule_state.editing_field or ""),
            raw_value=str(last_text or ""),
        )
        if edit_result.error_prompt is not None:
            return _build_section_review_update(
                state,
                schedule=update_schedule_flow_state(schedule_state),
                phase=state.get("phase", "schedules"),
                current_count=current_count,
                last_text=last_text,
                awaiting_user_input=True,
                prompt=edit_result.error_prompt,
            )
        if completion.after_change_phase is not None:
            return _complete_after_section_change(
                state,
                schedule=update_schedule_flow_state(
                    schedule_state,
                    blocks=edit_result.blocks,
                    conflicts=edit_result.conflicts,
                    conflicts_accepted=False,
                    summary_text=None,
                    review_stage="idle",
                    correction_target=None,
                    editing_block_id=None,
                    editing_block_ids=[],
                    editing_field=None,
                    pending_correction_text=None,
                ),
                completion=completion,
                current_count=current_count,
                last_text=last_text,
                **edit_result.scheduling_changes,
            )
        return _build_section_review_update(
            state,
            schedule=update_schedule_flow_state(
                schedule_state,
                blocks=edit_result.blocks,
                conflicts=edit_result.conflicts,
                conflicts_accepted=False,
                summary_text=None,
                review_stage="section_awaiting_item_confirmation",
                correction_target=target,
                editing_block_id=(
                    edit_result.updated_blocks[0].block_id
                    if edit_result.updated_blocks
                    else edit_result.updated_block.block_id
                    if edit_result.updated_block is not None
                    else None
                ),
                editing_block_ids=[
                    block.block_id
                    for block in (
                        edit_result.updated_blocks
                        or ([edit_result.updated_block] if edit_result.updated_block is not None else [])
                    )
                ],
                editing_field=None,
                pending_correction_text=None,
            ),
            phase=state.get("phase", "schedules"),
            current_count=current_count,
            last_text=last_text,
            awaiting_user_input=True,
            prompt=_build_item_confirmation_prompt_for_selection(
                target,  # type: ignore[arg-type]
                edit_result.updated_blocks
                or ([edit_result.updated_block] if edit_result.updated_block is not None else []),
                edit_result.conflicts,
            ),
            render_preview_blocks=edit_result.blocks,
            **edit_result.scheduling_changes,
        )

    if schedule_state.review_stage == "section_awaiting_item_confirmation":
        decision = _parse_two_option_choice(last_text) if has_new_input else None
        if decision == 1:
            return _build_section_review_update(
                state,
                schedule=update_schedule_flow_state(
                    schedule_state,
                    review_stage="section_awaiting_confirmation",
                    editing_block_id=None,
                    editing_block_ids=[],
                    editing_field=None,
                ),
                phase=state.get("phase", "schedules"),
                current_count=current_count if has_new_input else state.get("user_message_count", 0),
                last_text=last_text if has_new_input else state.get("last_user_text"),
                awaiting_user_input=True,
                prompt=_build_section_confirmation_prompt(schedule_state.blocks, target),  # type: ignore[arg-type]
                render_preview_blocks=schedule_state.blocks,
            )
        if decision == 2:
            selected_blocks = _find_selected_blocks(
                schedule_state.blocks,
                _active_editing_block_ids(schedule_state),
            )
            return _build_section_review_update(
                state,
                schedule=update_schedule_flow_state(
                    schedule_state,
                    review_stage="section_awaiting_field_selection",
                ),
                phase=state.get("phase", "schedules"),
                current_count=current_count if has_new_input else state.get("user_message_count", 0),
                last_text=last_text if has_new_input else state.get("last_user_text"),
                awaiting_user_input=True,
                prompt=_build_field_selection_prompt_for_selection(target, selected_blocks),  # type: ignore[arg-type]
            )
        selected_blocks = _find_selected_blocks(
            schedule_state.blocks,
            _active_editing_block_ids(schedule_state),
        )
        return _build_section_review_update(
            state,
            schedule=update_schedule_flow_state(schedule_state),
            phase=state.get("phase", "schedules"),
            current_count=current_count if has_new_input else state.get("user_message_count", 0),
            last_text=last_text if has_new_input else state.get("last_user_text"),
            awaiting_user_input=True,
            prompt=_build_invalid_item_confirmation_prompt_for_selection(target, selected_blocks),  # type: ignore[arg-type]
        )

    if schedule_state.review_stage == "section_awaiting_replace_all_payload":
        selected_block = _find_selected_block(schedule_state.blocks, schedule_state.editing_block_id)
        if not has_new_input or not str(last_text or "").strip():
            return _build_section_review_update(
                state,
                schedule=update_schedule_flow_state(schedule_state),
                phase=state.get("phase", "schedules"),
                current_count=state.get("user_message_count", 0),
                last_text=state.get("last_user_text"),
                awaiting_user_input=True,
                prompt=_build_replace_all_payload_prompt(target, selected_block),  # type: ignore[arg-type]
            )
        replace_result = _apply_block_replace_all(
            state,
            target=target,  # type: ignore[arg-type]
            block_id=str(schedule_state.editing_block_id or ""),
            text=str(last_text or ""),
            timezone=str(state.get("timezone", "America/Bogota")),
        )
        if replace_result.error_prompt is not None:
            return _build_section_review_update(
                state,
                schedule=update_schedule_flow_state(schedule_state),
                phase=state.get("phase", "schedules"),
                current_count=current_count,
                last_text=last_text,
                awaiting_user_input=True,
                prompt=replace_result.error_prompt,
            )
        if completion.after_change_phase is not None:
            return _complete_after_section_change(
                state,
                schedule=update_schedule_flow_state(
                    schedule_state,
                    blocks=replace_result.blocks,
                    conflicts=replace_result.conflicts,
                    conflicts_accepted=False,
                    summary_text=None,
                    review_stage="idle",
                    correction_target=None,
                    editing_block_id=None,
                    editing_block_ids=[],
                    editing_field=None,
                    pending_correction_text=None,
                ),
                completion=completion,
                current_count=current_count,
                last_text=last_text,
                **replace_result.scheduling_changes,
            )
        return _build_section_review_update(
            state,
            schedule=update_schedule_flow_state(
                schedule_state,
                blocks=replace_result.blocks,
                conflicts=replace_result.conflicts,
                conflicts_accepted=False,
                summary_text=None,
                review_stage="section_awaiting_item_confirmation",
                correction_target=target,
                editing_block_id=replace_result.updated_block.block_id if replace_result.updated_block else None,
                editing_block_ids=[
                    replace_result.updated_block.block_id
                ] if replace_result.updated_block else [],
                editing_field=None,
                pending_correction_text=None,
            ),
            phase=state.get("phase", "schedules"),
            current_count=current_count,
            last_text=last_text,
            awaiting_user_input=True,
            prompt=_build_item_confirmation_prompt_for_selection(
                target,  # type: ignore[arg-type]
                [replace_result.updated_block] if replace_result.updated_block else [],
                replace_result.conflicts,
            ),
            render_preview_blocks=replace_result.blocks,
            **replace_result.scheduling_changes,
        )

    if schedule_state.review_stage == "section_awaiting_add_payload":
        if not has_new_input or not str(last_text or "").strip():
            return _build_section_review_update(
                state,
                schedule=update_schedule_flow_state(schedule_state),
                phase=state.get("phase", "schedules"),
                current_count=state.get("user_message_count", 0),
                last_text=state.get("last_user_text"),
                awaiting_user_input=True,
                prompt=_build_add_payload_prompt(target),  # type: ignore[arg-type]
            )
        add_result = _apply_block_add(
            state,
            target=target,  # type: ignore[arg-type]
            text=str(last_text or ""),
            timezone=str(state.get("timezone", "America/Bogota")),
        )
        if add_result.error_prompt is not None:
            return _build_section_review_update(
                state,
                schedule=update_schedule_flow_state(schedule_state),
                phase=state.get("phase", "schedules"),
                current_count=current_count,
                last_text=last_text,
                awaiting_user_input=True,
                prompt=add_result.error_prompt,
            )
        added_label = "registro" if add_result.added_count == 1 else "registros"
        updated_schedule = update_schedule_flow_state(
            schedule_state,
            blocks=add_result.blocks,
            conflicts=add_result.conflicts,
            conflicts_accepted=False,
            summary_text=None,
            review_stage="section_awaiting_confirmation",
            correction_target=target,
            editing_block_id=None,
            editing_block_ids=[],
            editing_field=None,
            pending_correction_text=None,
        )
        return _build_section_review_update(
            state,
            schedule=updated_schedule,
            phase=state.get("phase", "schedules"),
            current_count=current_count,
            last_text=last_text,
            awaiting_user_input=True,
            prompt=(
                f"✅ Listo, agregué {add_result.added_count} {added_label} nuevo(s).\n\n"
                f"{_build_section_confirmation_prompt(add_result.blocks, target)}"  # type: ignore[arg-type]
            ),
            render_preview_blocks=add_result.blocks,
            **add_result.scheduling_changes,
        )

    return start_section_review(
        state,
        target=target,  # type: ignore[arg-type]
        phase=state.get("phase", "schedules"),
        current_count=current_count if has_new_input else state.get("user_message_count", 0),
        last_text=last_text if has_new_input else state.get("last_user_text"),
    )


@dataclass(frozen=True)
class _BlockEditResult:
    blocks: list[WeeklyScheduleBlock]
    conflicts: list
    updated_block: WeeklyScheduleBlock | None
    scheduling_changes: dict[str, object]
    error_prompt: str | None = None
    updated_blocks: list[WeeklyScheduleBlock] = field(default_factory=list)


@dataclass(frozen=True)
class _BlockDeleteResult:
    blocks: list[WeeklyScheduleBlock]
    conflicts: list
    scheduling_changes: dict[str, object]
    error_prompt: str | None = None


@dataclass(frozen=True)
class _BlockAddResult:
    blocks: list[WeeklyScheduleBlock]
    conflicts: list
    added_count: int
    scheduling_changes: dict[str, object]
    error_prompt: str | None = None


def _apply_block_edit(
    state: AgentState,
    *,
    target: ScheduleBlockType,
    block_id: str,
    field_name: str,
    raw_value: str,
) -> _BlockEditResult:
    return _apply_blocks_edit(
        state,
        target=target,
        block_ids=[block_id],
        field_name=field_name,
        raw_value=raw_value,
    )


def _apply_blocks_edit(
    state: AgentState,
    *,
    target: ScheduleBlockType,
    block_ids: list[str],
    field_name: str,
    raw_value: str,
) -> _BlockEditResult:
    schedule_state = ensure_schedule_flow_state(state.get("schedule", {}))
    all_blocks = [ensure_weekly_block(block) for block in schedule_state.blocks]
    target_blocks = current_section_blocks(all_blocks, target)
    selected_blocks = _find_selected_blocks(target_blocks, block_ids)
    if not selected_blocks:
        return _BlockEditResult(
            blocks=all_blocks,
            conflicts=list(schedule_state.conflicts),
            updated_block=target_blocks[0] if target_blocks else None,
            scheduling_changes={},
            error_prompt=_build_item_selection_prompt(all_blocks, target),
        )
    selected_block = selected_blocks[0]

    value_result = _parse_field_value(
        raw_value,
        selected_block,
        field_name=field_name,
    )
    if value_result.error_prompt is not None:
        return _BlockEditResult(
            blocks=all_blocks,
            conflicts=list(schedule_state.conflicts),
            updated_block=selected_block,
            updated_blocks=selected_blocks,
            scheduling_changes={},
            error_prompt=value_result.error_prompt,
        )

    updated_values = dict(value_result.updates)
    selected_ids = {block.block_id for block in selected_blocks}
    updated_blocks_by_id: dict[str, WeeklyScheduleBlock] = {}
    for block in selected_blocks:
        preview_block = block.model_copy(update=updated_values)
        updated_blocks_by_id[block.block_id] = block.model_copy(
            update={
                **updated_values,
                "source_text": _build_source_text(
                    target,
                    preview_block,
                ),
                "has_conflict": False,
                "conflict_accepted": False,
                "user_confirmed": False,
            }
        )
    updated_target_blocks = [
        updated_blocks_by_id[block.block_id] if block.block_id in selected_ids else block
        for block in target_blocks
    ]
    updated_schedule_blocks = replace_section_blocks(all_blocks, target, updated_target_blocks)
    updated_schedule_blocks, conflicts = detect_schedule_conflicts(updated_schedule_blocks)
    refreshed_blocks = _find_selected_blocks(
        updated_schedule_blocks,
        [block.block_id for block in selected_blocks],
    )
    scheduling_changes: dict[str, object] = {}

    if target in {"academic", "work"}:
        target_section_blocks = current_section_blocks(updated_schedule_blocks, target)
        raw_inputs = sync_schedule_blocks_to_raw_inputs(
            state.get("raw_inputs", {}),
            target,
            target_section_blocks,
        )
        scheduling_changes["raw_inputs"] = raw_inputs.model_dump(mode="python")
    else:
        extracurricular_blocks = current_section_blocks(
            updated_schedule_blocks,
            "extracurricular",
        )
        extracurricular_items = build_extracurricular_items_from_blocks(extracurricular_blocks)
        scheduling_changes["extracurricular"] = extracurricular_items

    return _BlockEditResult(
        blocks=updated_schedule_blocks,
        conflicts=conflicts,
        updated_block=refreshed_blocks[0] if refreshed_blocks else selected_block,
        updated_blocks=refreshed_blocks or list(updated_blocks_by_id.values()),
        scheduling_changes=scheduling_changes,
    )


def _apply_block_delete(
    state: AgentState,
    *,
    target: ScheduleBlockType,
    block_id: str,
) -> _BlockDeleteResult:
    return _apply_blocks_delete(
        state,
        target=target,
        block_ids=[block_id],
    )


def _apply_blocks_delete(
    state: AgentState,
    *,
    target: ScheduleBlockType,
    block_ids: list[str],
) -> _BlockDeleteResult:
    schedule_state = ensure_schedule_flow_state(state.get("schedule", {}))
    all_blocks = [ensure_weekly_block(block) for block in schedule_state.blocks]
    target_blocks = current_section_blocks(all_blocks, target)
    selected_blocks = _find_selected_blocks(target_blocks, block_ids)
    if not selected_blocks:
        return _BlockDeleteResult(
            blocks=all_blocks,
            conflicts=list(schedule_state.conflicts),
            scheduling_changes={},
            error_prompt=_build_item_selection_prompt(all_blocks, target),
        )

    selected_ids = {block.block_id for block in selected_blocks}
    updated_target_blocks = [
        block for block in target_blocks if block.block_id not in selected_ids
    ]
    updated_schedule_blocks = replace_section_blocks(all_blocks, target, updated_target_blocks)
    updated_schedule_blocks, conflicts = detect_schedule_conflicts(updated_schedule_blocks)
    scheduling_changes: dict[str, object] = {}

    if target in {"academic", "work"}:
        raw_inputs = sync_schedule_blocks_to_raw_inputs(
            state.get("raw_inputs", {}),
            target,
            updated_target_blocks,
        )
        scheduling_changes["raw_inputs"] = raw_inputs.model_dump(mode="python")
    else:
        extracurricular_items = build_extracurricular_items_from_blocks(updated_target_blocks)
        scheduling_changes["extracurricular"] = extracurricular_items

    return _BlockDeleteResult(
        blocks=updated_schedule_blocks,
        conflicts=conflicts,
        scheduling_changes=scheduling_changes,
    )


@dataclass(frozen=True)
class _FieldValueResult:
    updates: dict[str, str]
    error_prompt: str | None = None


def _parse_field_value(
    raw_value: str,
    selected_block: WeeklyScheduleBlock,
    *,
    field_name: str,
) -> _FieldValueResult:
    clean_value = str(raw_value or "").strip()
    if field_name == "title":
        if not clean_value:
            return _FieldValueResult(
                updates={},
                error_prompt="⚠️ El nombre no puede estar vacío.\nEscríbeme el nuevo nombre, por favor.",
            )
        return _FieldValueResult(updates={"title": clean_value})

    if field_name == "day_of_week":
        option = parse_numbered_option(clean_value)
        if option in _DAY_OPTIONS:
            return _FieldValueResult(updates={"day_of_week": _DAY_OPTIONS[option]})
        try:
            normalized_day = normalize_day(clean_value)
        except ValueError:
            return _FieldValueResult(
                updates={},
                error_prompt=_build_day_prompt_error(),
            )
        english_day = _DAY_BY_NORMALIZED_LABEL.get(normalize_text(normalized_day))
        if english_day is None:
            return _FieldValueResult(
                updates={},
                error_prompt=_build_day_prompt_error(),
            )
        return _FieldValueResult(updates={"day_of_week": english_day})

    if field_name == "time_range":
        try:
            start_time, end_time = extract_time_range(clean_value)
        except ValueError:
            return _FieldValueResult(
                updates={},
                error_prompt=(
                    "⚠️ No pude interpretar ese horario.\n"
                    "Envíamelo como 8:00 am a 10:00 am, 2:30 pm a 4:00 pm o 14:30 a 16:00."
                ),
            )

        if start_time >= end_time:
            return _FieldValueResult(
                updates={},
                error_prompt=(
                    "⚠️ La hora de inicio debe quedar antes de la hora de fin.\n"
                    f"Bloque actual: {_format_block_line(1, selected_block)}"
                ),
            )
        return _FieldValueResult(
            updates={
                "start_time": start_time,
                "end_time": end_time,
            }
        )

    if field_name in {"start_time", "end_time"}:
        try:
            normalized_time = normalize_time(clean_value)
        except ValueError:
            label = "inicio" if field_name == "start_time" else "fin"
            return _FieldValueResult(
                updates={},
                error_prompt=(
                    f"⚠️ No pude interpretar la hora de {label}.\n"
                    "Escríbela como 8:00 am, 2:30 pm o 14:30."
                ),
            )

        new_start = normalized_time if field_name == "start_time" else selected_block.start_time
        new_end = normalized_time if field_name == "end_time" else selected_block.end_time
        if new_start >= new_end:
            return _FieldValueResult(
                updates={},
                error_prompt=(
                    "⚠️ La hora de inicio debe quedar antes de la hora de fin.\n"
                    f"Bloque actual: {_format_block_line(1, selected_block)}"
                ),
            )
        return _FieldValueResult(updates={field_name: normalized_time})

    return _FieldValueResult(
        updates={},
        error_prompt="⚠️ Ese campo no es editable en este paso.",
    )


def _complete_section_review(
    state: AgentState,
    *,
    schedule_state: object,
    completion: SectionReviewCompletion,
    current_count: int,
    last_text: str | None,
) -> dict:
    return _build_section_review_update(
        state,
        schedule=update_schedule_flow_state(
            schedule_state,
            review_stage="idle",
            correction_target=None,
            editing_block_id=None,
            editing_field=None,
            pending_correction_text=None,
        )
        | completion.schedule_changes,
        phase=completion.phase,
        current_count=current_count,
        last_text=last_text,
        awaiting_user_input=completion.awaiting_user_input,
        prompt=completion.prompt,
        **completion.scheduling_changes,
    )


def _complete_after_section_change(
    state: AgentState,
    *,
    schedule: dict[str, object],
    completion: SectionReviewCompletion,
    current_count: int,
    last_text: str | None,
    **scheduling_changes: object,
) -> dict:
    return _build_section_review_update(
        state,
        schedule=schedule,
        phase=str(completion.after_change_phase or completion.phase),
        current_count=current_count,
        last_text=last_text,
        awaiting_user_input=bool(completion.after_change_awaiting_user_input),
        prompt=completion.after_change_prompt,
        **scheduling_changes,
    )


def _build_section_review_update(
    state: AgentState,
    *,
    schedule: dict[str, object],
    phase: str,
    current_count: int,
    last_text: str | None,
    awaiting_user_input: bool,
    prompt: str | list[dict[str, object]] | None = None,
    render_preview_blocks: list[WeeklyScheduleBlock] | list[dict] | None = None,
    **scheduling_changes: object,
) -> dict:
    conversation_changes: dict[str, object] = {
        "phase": phase,
        "user_message_count": current_count,
        "last_user_text": last_text,
        "awaiting_user_input": awaiting_user_input,
    }
    message_content = prompt
    if isinstance(prompt, str) and render_preview_blocks:
        normalized_blocks = [ensure_weekly_block(block) for block in render_preview_blocks]
        message_content, _ = build_rendered_schedule_message_content(
            prompt,
            normalized_blocks,
            timezone_name=state.get("timezone", "America/Bogota"),
        )
    if message_content:
        conversation_changes["messages"] = append_message(
            state.get("messages", []),
            "assistant",
            message_content,
        )
    return {
        **update_scheduling_state(
            state,
            schedule=schedule,
            **scheduling_changes,
        ),
        **update_conversation_state(state, **conversation_changes),
    }


def _build_section_confirmation_prompt(
    blocks: list[WeeklyScheduleBlock] | list[dict],
    target: ScheduleBlockType,
) -> str:
    lines = [
        f"✅ Este es tu {_SECTION_LABELS[target]} actual:",
    ]
    lines.extend(_format_block_lines(blocks, target, numbered=False))
    lines.extend(
        [
            "",
            "¿Está bien así?",
            _OPTION_HINT,
            "1. Sí, está correcto",
            "2. No, quiero cambiar algo",
        ]
    )
    return "\n".join(lines)


def _build_entry_prompt(
    blocks: list[WeeklyScheduleBlock] | list[dict],
    target: ScheduleBlockType,
    stage: str,
) -> str:
    if stage == "section_awaiting_item_selection":
        return _build_item_selection_prompt(blocks, target)
    return _build_section_confirmation_prompt(blocks, target)


def _build_invalid_choice_prompt(
    blocks: list[WeeklyScheduleBlock] | list[dict],
    target: ScheduleBlockType,
) -> str:
    return (
        "⚠️ Elige una opción válida.\n\n"
        f"{_build_section_confirmation_prompt(blocks, target)}"
    )


def _build_item_selection_prompt(
    blocks: list[WeeklyScheduleBlock] | list[dict],
    target: ScheduleBlockType,
) -> str:
    item_label = _ITEM_LABELS[target]
    lines = [
        f"✏️ Este es tu {_SECTION_LABELS[target]} actual:",
        _ITEM_HINT,
    ]
    lines.extend(_format_block_lines(blocks, target))
    lines.extend(
        [
            "",
            f"Elige el número de la {item_label if item_label != 'bloque' else 'actividad o bloque'} que quieres editar.",
            "Para editar varias con el mismo cambio, escribe los números separados por coma o espacio. Ej: 1,2,3 o 1 2 3.",
            f"Escribe 'Añadir' si deseas agregar más actividades {_ADD_TYPE_LABELS[target]} o escribe 'Cancelar' si no quieres modificar nada.",
        ]
    )
    return "\n".join(lines)


def _build_cancel_selection_prompt(
    blocks: list[WeeklyScheduleBlock] | list[dict],
    target: ScheduleBlockType,
) -> str:
    return (
        "De acuerdo, no hice cambios.\n\n"
        f"{_build_section_confirmation_prompt(blocks, target)}"
    )


def _build_invalid_item_prompt(
    blocks: list[WeeklyScheduleBlock] | list[dict],
    target: ScheduleBlockType,
) -> str:
    return (
        "⚠️ Ese número no corresponde a un registro de la lista.\n\n"
        f"{_build_item_selection_prompt(blocks, target)}"
    )


def _build_field_selection_prompt(
    target: ScheduleBlockType,
    block: WeeklyScheduleBlock | None,
) -> str:
    return _build_field_selection_prompt_for_selection(
        target,
        [block] if block is not None else [],
    )


def _build_field_selection_prompt_for_selection(
    target: ScheduleBlockType,
    blocks: list[WeeklyScheduleBlock],
) -> str:
    item_label = _ITEM_LABELS[target]
    lines = []
    if len(blocks) == 1:
        block = blocks[0]
        lines.append(f"{_HEADER_EMOJIS[target]} Vas a editar este {item_label}:")
        lines.append(_format_block_line(1, block))
        lines.append("")
    elif len(blocks) > 1:
        lines.append(f"{_HEADER_EMOJIS[target]} Vas a editar estos {len(blocks)} registros:")
        lines.extend(_format_selected_block_lines(blocks))
        lines.append("")
    lines.extend(
        [
            "🛠️ ¿Qué quieres cambiar?",
            _FIELD_HINT,
            "1. Nombre",
            "2. Día",
            "3. Horario",
            f"4. Eliminar {_field_delete_label(item_label, len(blocks))}",
            "5. Cancelar selección",
        ]
    )
    if len(blocks) <= 1:
        lines.append("6. Reemplazar todos los datos")
    return "\n".join(lines)


def _build_invalid_field_prompt(
    target: ScheduleBlockType,
    block: WeeklyScheduleBlock | None,
) -> str:
    return _build_invalid_field_prompt_for_selection(
        target,
        [block] if block is not None else [],
    )


def _build_invalid_field_prompt_for_selection(
    target: ScheduleBlockType,
    blocks: list[WeeklyScheduleBlock],
) -> str:
    return (
        "⚠️ Elige una opción válida.\n\n"
        f"{_build_field_selection_prompt_for_selection(target, blocks)}"
    )


def _build_field_value_prompt(
    target: ScheduleBlockType,
    block: WeeklyScheduleBlock | None,
    field_name: str,
) -> str:
    return _build_field_value_prompt_for_selection(
        target,
        [block] if block is not None else [],
        field_name,
    )


def _build_field_value_prompt_for_selection(
    target: ScheduleBlockType,
    blocks: list[WeeklyScheduleBlock],
    field_name: str,
) -> str:
    item_label = _ITEM_LABELS[target]
    current_line = _format_current_selection_lines(blocks)
    plural = len(blocks) > 1
    if field_name == "title":
        return (
            f"✏️ Escribe el nuevo nombre para {'estos registros' if plural else 'la ' + (item_label if item_label != 'bloque' else 'actividad o bloque')}.\n"
            f"{current_line}"
        )
    if field_name == "day_of_week":
        lines = [
            f"📅 Elige el nuevo día para {'estos registros' if plural else 'este registro'}:",
            "1. Lunes",
            "2. Martes",
            "3. Miércoles",
            "4. Jueves",
            "5. Viernes",
            "6. Sábado",
            "7. Domingo",
        ]
        if current_line:
            lines.extend(["", current_line])
        return "\n".join(lines)
    if field_name in {"start_time", "end_time"}:
        label = "inicio" if field_name == "start_time" else "fin"
        return (
            f"⏰ Escribe la nueva hora de {label} para {'estos registros' if plural else 'este registro'}.\n"
            "Ejemplos válidos: 8:00 am, 2:30 pm o 14:30.\n"
            f"{current_line}"
        )
    return (
        f"⏰ Escribe el nuevo horario completo para {'estos registros' if plural else 'este registro'}.\n"
        "Envíame la hora de inicio y la hora de fin en un solo mensaje.\n"
        "Ejemplos válidos: 8:00 am a 10:00 am, 2:30 pm a 4:00 pm o 14:30 a 16:00.\n"
        f"{current_line}"
    )


def _build_item_confirmation_prompt(
    target: ScheduleBlockType,
    block: WeeklyScheduleBlock,
    conflicts: list,
) -> str:
    return _build_item_confirmation_prompt_for_selection(target, [block], conflicts)


def _build_item_confirmation_prompt_for_selection(
    target: ScheduleBlockType,
    blocks: list[WeeklyScheduleBlock],
    conflicts: list,
) -> str:
    if not blocks:
        return "⚠️ No encontré el registro actualizado. Volvamos a elegir uno."
    lines = [
        "✅ Así quedó actualizado:" if len(blocks) == 1 else "✅ Así quedaron actualizados estos registros:",
    ]
    lines.extend(_format_selected_block_lines(blocks))
    conflict_warning = _build_related_conflict_warning(
        [block.block_id for block in blocks],
        conflicts,
    )
    if conflict_warning:
        lines.extend(["", conflict_warning])
    lines.extend(
        [
            "",
            _OPTION_HINT,
            "¿Ahora sí quedó bien?",
            "1. Sí, seguimos",
            "2. No, quiero cambiar algo más",
        ]
    )
    return "\n".join(lines)


def _build_delete_result_prompt(
    target: ScheduleBlockType,
    blocks: list[WeeklyScheduleBlock] | list[dict],
) -> str:
    return (
        f"🗑️ Listo, ya eliminé ese registro.\n\n"
        f"{_build_section_confirmation_prompt(blocks, target)}"
    )


def _build_invalid_item_confirmation_prompt(
    target: ScheduleBlockType,
    block: WeeklyScheduleBlock | None,
) -> str:
    return _build_invalid_item_confirmation_prompt_for_selection(
        target,
        [block] if block is not None else [],
    )


def _build_invalid_item_confirmation_prompt_for_selection(
    target: ScheduleBlockType,
    blocks: list[WeeklyScheduleBlock],
) -> str:
    if not blocks:
        return "⚠️ Elige una opción válida.\n1. Sí, seguimos\n2. No, quiero cambiar algo más"
    return (
        "⚠️ Elige una opción válida.\n\n"
        f"{_build_item_confirmation_prompt_for_selection(target, blocks, [])}"
    )


def _build_related_conflict_warning(block_ids: str | list[str], conflicts: list) -> str:
    selected_ids = {block_ids} if isinstance(block_ids, str) else set(block_ids)
    related = [
        conflict
        for conflict in conflicts
        if getattr(conflict, "left_block_id", None) in selected_ids
        or getattr(conflict, "right_block_id", None) in selected_ids
    ]
    if not related:
        return ""

    lines = ["⚠️ Ojo, este cambio genera un cruce:"]
    for conflict in related:
        left_selected = getattr(conflict, "left_block_id", None) in selected_ids
        right_selected = getattr(conflict, "right_block_id", None) in selected_ids
        other_title = conflict.right_title if left_selected else conflict.left_title
        other_type = conflict.right_type if left_selected else conflict.left_type
        if left_selected and right_selected:
            other_title = conflict.right_title
            other_type = conflict.right_type
        lines.append(
            f"- {DAY_LABELS[conflict.day_of_week]}: se cruza con {other_title} "
            f"({_TYPE_LABELS.get(other_type, other_type)}) entre "
            f"{_format_time_human(conflict.overlap_start)} y {_format_time_human(conflict.overlap_end)}."
        )
    lines.append("Si quieres, puedes volver a ajustar esta selección antes de continuar.")
    return "\n".join(lines)


def _format_block_lines(
    blocks: list[WeeklyScheduleBlock] | list[dict],
    target: ScheduleBlockType,
    *,
    numbered: bool = True,
) -> list[str]:
    section_blocks = current_section_blocks(blocks, target)
    if not section_blocks:
        return [
            "1. Aún no tengo registros en esta sección."
            if numbered
            else "- Aún no tengo registros en esta sección."
        ]
    ordered = sorted(
        section_blocks,
        key=lambda item: (DAY_ORDER.index(item.day_of_week), item.start_time, item.title.lower()),
    )
    if numbered:
        return [_format_block_line(index, block) for index, block in enumerate(ordered, start=1)]
    return [_format_bullet_block_line(block) for block in ordered]


def _format_block_line(index: int, block: WeeklyScheduleBlock | None) -> str:
    if block is None:
        return f"{index}. Registro no disponible."
    return (
        f"{index}. {block.title} — {DAY_LABELS[block.day_of_week]} "
        f"de {_format_time_human(block.start_time)} a {_format_time_human(block.end_time)}"
    )


def _format_selected_block_lines(blocks: list[WeeklyScheduleBlock]) -> list[str]:
    return [_format_block_line(index, block) for index, block in enumerate(blocks, start=1)]


def _format_current_selection_lines(blocks: list[WeeklyScheduleBlock]) -> str:
    if not blocks:
        return "Actual: registro no disponible."
    label = "Actual" if len(blocks) == 1 else "Actuales"
    return "\n".join([f"{label}:"] + _format_selected_block_lines(blocks))


def _field_delete_label(item_label: str, count: int) -> str:
    if count > 1:
        return "estos registros"
    return item_label if item_label != "bloque" else "registro"


def _format_bullet_block_line(block: WeeklyScheduleBlock | None) -> str:
    if block is None:
        return "- Registro no disponible."
    return (
        f"- {block.title} — {DAY_LABELS[block.day_of_week]} "
        f"de {_format_time_human(block.start_time)} a {_format_time_human(block.end_time)}"
    )


def _format_time_human(value: str) -> str:
    hour = int(value[:2])
    minute = value[3:]
    meridiem = "a.m." if hour < 12 else "p.m."
    human_hour = hour % 12 or 12
    return f"{human_hour}:{minute} {meridiem}"


def _parse_two_option_choice(text: str | None) -> int | None:
    option = parse_numbered_option(text)
    if option in {1, 2}:
        return option
    answer = parse_yes_no(text or "")
    if answer is True:
        return 1
    if answer is False:
        return 2
    normalized = normalize_text(text or "")
    if any(token in normalized for token in ("seguir", "continuar", "continuemos")):
        return 1
    if any(token in normalized for token in ("cambiar", "editar", "corregir")):
        return 2
    return None


def _parse_selected_block(
    blocks: list[WeeklyScheduleBlock] | list[dict],
    target: ScheduleBlockType,
    text: str | None,
) -> WeeklyScheduleBlock | None:
    selected = _parse_selected_blocks(blocks, target, text)
    if len(selected) != 1:
        return None
    return selected[0]


def _parse_selected_blocks(
    blocks: list[WeeklyScheduleBlock] | list[dict],
    target: ScheduleBlockType,
    text: str | None,
) -> list[WeeklyScheduleBlock]:
    section_blocks = sorted(
        current_section_blocks(blocks, target),
        key=lambda item: (DAY_ORDER.index(item.day_of_week), item.start_time, item.title.lower()),
    )
    options = _parse_selection_numbers(text)
    if not options:
        return []
    if any(option < 1 or option > len(section_blocks) for option in options):
        return []
    selected: list[WeeklyScheduleBlock] = []
    seen: set[int] = set()
    for option in options:
        if option in seen:
            continue
        seen.add(option)
        selected.append(section_blocks[option - 1])
    return selected


def _parse_selection_numbers(text: str | None) -> list[int]:
    raw = str(text or "").strip()
    if not raw:
        return []
    first_line = raw.splitlines()[0].strip()
    normalized = normalize_text(first_line)
    if not re.search(r"\d", normalized):
        return []

    allowed_words = (
        "la",
        "las",
        "opcion",
        "opciones",
        "registro",
        "registros",
        "actividad",
        "actividades",
        "materia",
        "materias",
        "bloque",
        "bloques",
        "numero",
        "numeros",
        "y",
        "e",
    )
    residue = re.sub(r"\b(?:" + "|".join(allowed_words) + r")\b", " ", normalized)
    residue = re.sub(r"\d+", " ", residue)
    residue = re.sub(r"[\s,.;:()]+", " ", residue).strip()
    if residue:
        return []
    return [int(match.group(0)) for match in re.finditer(r"\d+", normalized)]


def _parse_field_choice(text: str | None, *, allow_replace_all: bool = True) -> str | None:
    option = parse_numbered_option(text)
    if option in _FIELD_OPTIONS:
        return _FIELD_OPTIONS[option]
    if option == 4:
        return "delete"
    if option == 5:
        return "cancel"
    if option == 6 and allow_replace_all:
        return "replace_all"

    normalized = normalize_text(text or "")
    if any(token in normalized for token in ("nombre",)):
        return "title"
    if any(token in normalized for token in ("dia", "día")):
        return "day_of_week"
    if any(token in normalized for token in ("horario", "hora", "inicio", "fin")):
        return "time_range"
    if any(token in normalized for token in ("eliminar", "borrar")):
        return "delete"
    if any(token in normalized for token in ("cancelar", "volver")):
        return "cancel"
    if allow_replace_all and any(token in normalized for token in ("reemplazar", "todos", "cambiar todo")):
        return "replace_all"
    return None


def _find_selected_block(
    blocks: list[WeeklyScheduleBlock] | list[dict],
    block_id: str | None,
) -> WeeklyScheduleBlock | None:
    if not block_id:
        return None
    for raw_block in blocks:
        block = ensure_weekly_block(raw_block)
        if block.block_id == block_id:
            return block
    return None


def _find_selected_blocks(
    blocks: list[WeeklyScheduleBlock] | list[dict],
    block_ids: list[str],
) -> list[WeeklyScheduleBlock]:
    if not block_ids:
        return []
    normalized_blocks = [ensure_weekly_block(block) for block in blocks]
    by_id = {block.block_id: block for block in normalized_blocks}
    selected: list[WeeklyScheduleBlock] = []
    seen: set[str] = set()
    for raw_id in block_ids:
        block_id = str(raw_id or "").strip()
        if not block_id or block_id in seen:
            continue
        block = by_id.get(block_id)
        if block is None:
            continue
        seen.add(block_id)
        selected.append(block)
    return selected


def _active_editing_block_ids(schedule_state: object) -> list[str]:
    raw_ids = getattr(schedule_state, "editing_block_ids", []) or []
    ids = [str(block_id) for block_id in raw_ids if str(block_id or "").strip()]
    if ids:
        return ids
    single_id = str(getattr(schedule_state, "editing_block_id", "") or "").strip()
    return [single_id] if single_id else []


def _is_add_command(text: str | None) -> bool:
    normalized = normalize_text(text or "")
    return any(token in normalized for token in ("anadir", "añadir", "agregar", "nuevo", "nueva", "add"))


def _is_cancel_command(text: str | None) -> bool:
    normalized = normalize_text(text or "")
    return any(
        token in normalized
        for token in (
            "cancelar",
            "volver",
            "no quiero modificar",
            "no modificar nada",
            "no quiero cambiar",
            "me equivoque",
        )
    )


def _build_add_payload_prompt(target: ScheduleBlockType) -> str:
    if target == "work":
        return (
            "💼 Escríbeme el nuevo bloque laboral que quieres agregar.\n"
            "Incluye días y horas exactas.\n"
            "Ejemplo: miércoles de 7:00 a 18:00"
        )
    if target == "extracurricular":
        return (
            "🎯 Escríbeme la nueva actividad extracurricular que quieres agregar.\n"
            "Incluye el nombre, día y horario.\n"
            "Ejemplo: Gym — lunes de 7:00 a 8:00"
        )
    return (
        "📚 Escríbeme la nueva materia o clase que quieres agregar.\n"
        "Incluye el nombre, día y horario.\n"
        "Ejemplo: Cálculo — martes de 8:00 a 10:00"
    )


def _apply_block_add(
    state: AgentState,
    *,
    target: ScheduleBlockType,
    text: str,
    timezone: str,
) -> _BlockAddResult:
    schedule_state = ensure_schedule_flow_state(state.get("schedule", {}))
    all_blocks = [ensure_weekly_block(block) for block in schedule_state.blocks]
    existing_section = current_section_blocks(all_blocks, target)

    if target == "extracurricular":
        section_result = parse_extracurricular_section(
            text,
            timezone=timezone,
            expected_is_variable=False,
        )
        if not section_result.blocks:
            return _BlockAddResult(
                blocks=all_blocks,
                conflicts=list(schedule_state.conflicts),
                added_count=0,
                scheduling_changes={},
                error_prompt=(
                    "⚠️ No pude interpretar la actividad. Intenta de nuevo.\n\n"
                    f"{_build_add_payload_prompt(target)}"
                ),
            )
        new_section = existing_section + list(section_result.blocks)
        updated_all = replace_section_blocks(all_blocks, target, new_section)
        updated_all, conflicts = detect_schedule_conflicts(updated_all)
        items = build_extracurricular_items_from_blocks(current_section_blocks(updated_all, target))
        return _BlockAddResult(
            blocks=updated_all,
            conflicts=conflicts,
            added_count=len(section_result.blocks),
            scheduling_changes={"extracurricular": items},
        )

    result = normalize_schedule_section(text, target, timezone=timezone)
    if not result.blocks:
        return _BlockAddResult(
            blocks=all_blocks,
            conflicts=list(schedule_state.conflicts),
            added_count=0,
            scheduling_changes={},
            error_prompt=(
                "⚠️ No pude interpretar el horario. Intenta de nuevo.\n\n"
                f"{_build_add_payload_prompt(target)}"
            ),
        )
    new_section = existing_section + list(result.blocks)
    updated_all = replace_section_blocks(all_blocks, target, new_section)
    updated_all, conflicts = detect_schedule_conflicts(updated_all)
    raw_inputs = sync_schedule_blocks_to_raw_inputs(
        state.get("raw_inputs", {}),
        target,
        current_section_blocks(updated_all, target),
    )
    return _BlockAddResult(
        blocks=updated_all,
        conflicts=conflicts,
        added_count=len(result.blocks),
        scheduling_changes={"raw_inputs": raw_inputs.model_dump(mode="python")},
    )


def _build_replace_all_payload_prompt(
    target: ScheduleBlockType,
    block: WeeklyScheduleBlock | None,
) -> str:
    current_line = f"\nActual: {_format_block_line(1, block)}" if block is not None else ""
    if target == "work":
        return (
            f"✏️ Escríbeme los nuevos datos completos de este bloque laboral.\n"
            "Incluye días y horas en un solo mensaje."
            f"{current_line}\n"
            "Ejemplo: miércoles de 8:00 a 17:00"
        )
    if target == "extracurricular":
        return (
            f"✏️ Escríbeme los nuevos datos completos de esta actividad.\n"
            "Incluye nombre, día y horario en un solo mensaje."
            f"{current_line}\n"
            "Ejemplo: Fútbol — sábado de 9:00 a 11:00"
        )
    return (
        f"✏️ Escríbeme los nuevos datos completos de esta materia.\n"
        "Incluye nombre, día y horario en un solo mensaje."
        f"{current_line}\n"
        "Ejemplo: Cálculo — jueves de 2:00 a 4:00"
    )


def _apply_block_replace_all(
    state: AgentState,
    *,
    target: ScheduleBlockType,
    block_id: str,
    text: str,
    timezone: str,
) -> _BlockEditResult:
    schedule_state = ensure_schedule_flow_state(state.get("schedule", {}))
    all_blocks = [ensure_weekly_block(block) for block in schedule_state.blocks]
    target_blocks = current_section_blocks(all_blocks, target)
    selected_block = _find_selected_block(target_blocks, block_id)

    if selected_block is None:
        return _BlockEditResult(
            blocks=all_blocks,
            conflicts=list(schedule_state.conflicts),
            updated_block=target_blocks[0] if target_blocks else None,
            scheduling_changes={},
            error_prompt=_build_item_selection_prompt(all_blocks, target),
        )

    if target == "extracurricular":
        section_result = parse_extracurricular_section(text, timezone=timezone, expected_is_variable=False)
        new_blocks = list(section_result.blocks)
    else:
        result = normalize_schedule_section(text, target, timezone=timezone)
        new_blocks = list(result.blocks)

    if not new_blocks:
        return _BlockEditResult(
            blocks=all_blocks,
            conflicts=list(schedule_state.conflicts),
            updated_block=selected_block,
            scheduling_changes={},
            error_prompt=(
                "⚠️ No pude interpretar los nuevos datos. Intenta de nuevo.\n\n"
                f"{_build_replace_all_payload_prompt(target, selected_block)}"
            ),
        )

    src = new_blocks[0]
    replacement = selected_block.model_copy(
        update={
            "title": src.title,
            "day_of_week": src.day_of_week,
            "start_time": src.start_time,
            "end_time": src.end_time,
            "source_text": _build_source_text(target, src),
            "has_conflict": False,
            "conflict_accepted": False,
            "user_confirmed": False,
        }
    )
    updated_target_blocks = [
        replacement if block.block_id == selected_block.block_id else block
        for block in target_blocks
    ]
    updated_all = replace_section_blocks(all_blocks, target, updated_target_blocks)
    updated_all, conflicts = detect_schedule_conflicts(updated_all)
    refreshed = _find_selected_block(updated_all, replacement.block_id)
    scheduling_changes: dict[str, object] = {}

    if target in {"academic", "work"}:
        raw_inputs = sync_schedule_blocks_to_raw_inputs(
            state.get("raw_inputs", {}),
            target,
            current_section_blocks(updated_all, target),
        )
        scheduling_changes["raw_inputs"] = raw_inputs.model_dump(mode="python")
    else:
        items = build_extracurricular_items_from_blocks(current_section_blocks(updated_all, target))
        scheduling_changes["extracurricular"] = items

    return _BlockEditResult(
        blocks=updated_all,
        conflicts=conflicts,
        updated_block=refreshed or replacement,
        scheduling_changes=scheduling_changes,
    )


def _build_day_prompt_error() -> str:
    return (
        "⚠️ No pude interpretar el día.\n"
        "Elige una opción entre 1 y 7 o escríbelo como Lunes, Martes, Miércoles..."
    )


def _build_source_text(
    target: ScheduleBlockType,
    block: WeeklyScheduleBlock,
) -> str:
    day = DAY_LABELS[block.day_of_week]
    if target == "work" and normalize_text(block.title) == "trabajo":
        return f"{day} {block.start_time}-{block.end_time}"
    return f"{day} {block.start_time}-{block.end_time} {block.title}".strip()
