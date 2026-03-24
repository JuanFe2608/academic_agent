"""Nodo para solicitar y ampliar el horario fijo por secciones."""

from __future__ import annotations

import re

from agents.support.scheduling import merge_section_blocks, replace_section_blocks
from agents.support.scheduling.contextual_parser import (
    build_schedule_pending_prompt,
    complete_pending_schedule_item,
    serialize_blocks_for_schedule_type,
)
from agents.support.nodes.utils import (
    append_message,
    contains_normalized_phrase,
    detect_new_input,
    has_time_range,
    normalize_text,
)
from agents.support.state import AgentState, PendingScheduleItem, RawInputs

from .prompt import (
    PROMPT_ACADEMICO,
    PROMPT_LABORAL,
    PROMPT_MORE_ACADEMIC,
    PROMPT_MORE_WORK,
    PROMPT_NINGUNA,
    PROMPT_OCCUPATION,
)

_CONTINUE_TOKENS = {
    "seguimos",
    "seguir",
    "siguiente",
    "continuemos",
    "continuar",
    "listo",
    "ya termine",
    "ya terminé",
    "terminado",
    "eso es todo",
    "nada mas",
    "nada más",
}
_DAY_HINT_PATTERN = re.compile(
    r"\b(lunes|martes|miercoles|miércoles|jueves|viernes|sabado|sábado|domingo|lun|mar|mie|jue|vie|sab|dom)\b",
    re.IGNORECASE,
)


def request_schedules(state: AgentState) -> dict:
    """Gestiona la captura incremental de horario académico y laboral."""

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
    schedule_input_text = last_text
    occupation_reply_consumed = False

    if not occupation and has_new_input and last_text:
        parsed_occupation, extracted_schedule_text = _extract_occupation_reply(last_text)
        if parsed_occupation:
            occupation = parsed_occupation
            profile["occupation"] = parsed_occupation
            schedule_input_text = extracted_schedule_text
            occupation_reply_consumed = not bool(extracted_schedule_text)

    if not occupation:
        return _build_schedule_update(
            state,
            profile=profile,
            raw_inputs=raw_inputs,
            schedule_state=schedule_state,
            academic_pending_items=academic_pending_items,
            work_pending_items=work_pending_items,
            phase="schedules",
            awaiting_user_input=True,
            current_count=current_count if has_new_input else state.get("user_message_count", 0),
            last_text=last_text if has_new_input else state.get("last_user_text"),
            prompt=PROMPT_OCCUPATION,
        )

    if occupation == "ninguna":
        return _build_schedule_update(
            state,
            profile=profile,
            raw_inputs=raw_inputs,
            schedule_state=schedule_state,
            academic_pending_items=academic_pending_items,
            work_pending_items=work_pending_items,
            phase="end",
            awaiting_user_input=False,
            current_count=current_count if has_new_input else state.get("user_message_count", 0),
            last_text=last_text if has_new_input else state.get("last_user_text"),
            prompt=PROMPT_NINGUNA,
        )

    capture_target = _resolve_capture_target(
        state,
        occupation=occupation,
        raw_inputs=raw_inputs,
        schedule_state=schedule_state,
        academic_pending_items=academic_pending_items,
        work_pending_items=work_pending_items,
    )
    capture_stage = str(schedule_state.get("capture_stage") or "idle")

    if occupation_reply_consumed:
        return _prompt_for_section_input(
            state,
            profile=profile,
            occupation=occupation,
            target=capture_target,
            raw_inputs=raw_inputs,
            schedule_state=schedule_state,
            academic_pending_items=academic_pending_items,
            work_pending_items=work_pending_items,
            current_count=current_count,
            last_text=last_text,
        )

    if capture_target is None:
        return _build_schedule_update(
            state,
            profile=profile,
            raw_inputs=raw_inputs,
            schedule_state={**schedule_state, "capture_target": None, "capture_stage": "idle"},
            academic_pending_items=academic_pending_items,
            work_pending_items=work_pending_items,
            phase="extras",
            awaiting_user_input=False,
            current_count=current_count if has_new_input else state.get("user_message_count", 0),
            last_text=last_text if has_new_input else state.get("last_user_text"),
        )

    if has_new_input and schedule_input_text and (academic_pending_items or work_pending_items):
        pending_update = _consume_pending_schedule_reply(
            state,
            raw_inputs=raw_inputs,
            schedule_state={**schedule_state, "capture_target": capture_target},
            academic_pending_items=academic_pending_items,
            work_pending_items=work_pending_items,
            response_text=schedule_input_text,
            current_count=current_count,
        )
        if pending_update is not None:
            pending_update["student_profile"] = profile
            return pending_update

    if capture_stage == "awaiting_more":
        if has_new_input and schedule_input_text:
            decision = _parse_more_decision(schedule_input_text)
            if decision == "continue":
                return _advance_after_section(
                    state,
                    occupation=occupation,
                    current_target=capture_target,
                    raw_inputs=raw_inputs,
                    schedule_state=schedule_state,
                    academic_pending_items=academic_pending_items,
                    work_pending_items=work_pending_items,
                    current_count=current_count,
                    last_text=last_text,
                )
            if decision == "more" and not _looks_like_schedule_content(schedule_input_text):
                return _prompt_for_section_input(
                    state,
                    profile=profile,
                    occupation=occupation,
                    target=capture_target,
                    raw_inputs=raw_inputs,
                    schedule_state=schedule_state,
                    academic_pending_items=academic_pending_items,
                    work_pending_items=work_pending_items,
                    current_count=current_count,
                    last_text=last_text,
                )
            if decision in {"more", None} and _looks_like_schedule_content(schedule_input_text):
                raw_inputs = _append_schedule_text(raw_inputs, capture_target, schedule_input_text)
                return _build_schedule_update(
                    state,
                    profile=profile,
                    raw_inputs=raw_inputs,
                    schedule_state={
                        **schedule_state,
                        "capture_target": capture_target,
                        "capture_stage": "awaiting_input",
                    },
                    academic_pending_items=academic_pending_items,
                    work_pending_items=work_pending_items,
                    phase="schedules",
                    awaiting_user_input=False,
                    current_count=current_count,
                    last_text=last_text,
                )
        return _build_schedule_update(
            state,
            profile=profile,
            raw_inputs=raw_inputs,
            schedule_state={
                **schedule_state,
                "capture_target": capture_target,
                "capture_stage": "awaiting_more",
            },
            academic_pending_items=academic_pending_items,
            work_pending_items=work_pending_items,
            phase="schedules",
            awaiting_user_input=True,
            current_count=current_count if has_new_input else state.get("user_message_count", 0),
            last_text=last_text if has_new_input else state.get("last_user_text"),
            prompt=_prompt_for_more(capture_target),
        )

    if has_new_input and schedule_input_text:
        raw_inputs = _append_schedule_text(raw_inputs, capture_target, schedule_input_text)
        return _build_schedule_update(
            state,
            profile=profile,
            raw_inputs=raw_inputs,
            schedule_state={
                **schedule_state,
                "capture_target": capture_target,
                "capture_stage": "awaiting_input",
            },
            academic_pending_items=academic_pending_items,
            work_pending_items=work_pending_items,
            phase="schedules",
            awaiting_user_input=False,
            current_count=current_count,
            last_text=last_text,
        )

    return _prompt_for_section_input(
        state,
        profile=profile,
        occupation=occupation,
        target=capture_target,
        raw_inputs=raw_inputs,
        schedule_state=schedule_state,
        academic_pending_items=academic_pending_items,
        work_pending_items=work_pending_items,
        current_count=state.get("user_message_count", 0),
        last_text=state.get("last_user_text"),
    )


def _prompt_for_section_input(
    state: AgentState,
    *,
    profile: dict,
    occupation: str,
    target: str,
    raw_inputs: RawInputs,
    schedule_state: dict,
    academic_pending_items: list[PendingScheduleItem],
    work_pending_items: list[PendingScheduleItem],
    current_count: int,
    last_text: str | None,
) -> dict:
    return _build_schedule_update(
        state,
        profile=profile,
        raw_inputs=raw_inputs,
        schedule_state={
            **schedule_state,
            "capture_target": target,
            "capture_stage": "awaiting_input",
        },
        academic_pending_items=academic_pending_items,
        work_pending_items=work_pending_items,
        phase="schedules",
        awaiting_user_input=True,
        current_count=current_count,
        last_text=last_text,
        prompt=_prompt_for_target(target, occupation),
    )


def _advance_after_section(
    state: AgentState,
    *,
    occupation: str,
    current_target: str,
    raw_inputs: RawInputs,
    schedule_state: dict,
    academic_pending_items: list[PendingScheduleItem],
    work_pending_items: list[PendingScheduleItem],
    current_count: int,
    last_text: str,
) -> dict:
    next_target = _next_section_target(current_target, occupation)
    if next_target is None:
        return _build_schedule_update(
            state,
            profile=dict(state.get("student_profile", {})),
            raw_inputs=raw_inputs,
            schedule_state={
                **schedule_state,
                "capture_target": None,
                "capture_stage": "idle",
            },
            academic_pending_items=academic_pending_items,
            work_pending_items=work_pending_items,
            phase="extras",
            awaiting_user_input=False,
            current_count=current_count,
            last_text=last_text,
        )

    return _build_schedule_update(
        state,
        profile=dict(state.get("student_profile", {})),
        raw_inputs=raw_inputs,
        schedule_state={
            **schedule_state,
            "capture_target": next_target,
            "capture_stage": "awaiting_input",
        },
        academic_pending_items=academic_pending_items,
        work_pending_items=work_pending_items,
        phase="schedules",
        awaiting_user_input=True,
        current_count=current_count,
        last_text=last_text,
        prompt=_prompt_for_target(next_target, occupation),
    )


def _append_schedule_text(raw_inputs: RawInputs, target: str, text: str) -> RawInputs:
    updated = dict(raw_inputs)
    clean_text = str(text or "").strip()
    if not clean_text:
        return updated
    field = "horario_academico_text" if target == "academic" else "horario_laboral_text"
    existing = str(updated.get(field) or "").strip()
    updated[field] = "\n".join(part for part in [existing, clean_text] if part)
    return updated


def _resolve_capture_target(
    state: AgentState,
    *,
    occupation: str,
    raw_inputs: RawInputs,
    schedule_state: dict,
    academic_pending_items: list[PendingScheduleItem],
    work_pending_items: list[PendingScheduleItem],
) -> str | None:
    current_target = str(schedule_state.get("capture_target") or "").strip()
    if current_target in {"academic", "work"}:
        return current_target

    blocks = list(schedule_state.get("blocks", []))
    has_academic = bool(raw_inputs.get("horario_academico_text")) or _has_block_type(blocks, "academic")
    has_work = bool(raw_inputs.get("horario_laboral_text")) or _has_block_type(blocks, "work")

    if academic_pending_items:
        return "academic"
    if work_pending_items:
        return "work"
    if not has_academic:
        return "academic"
    if occupation == "ambos" and not has_work:
        return "work"
    return None


def _prompt_for_target(target: str, occupation: str) -> str:
    if target == "work":
        return PROMPT_LABORAL
    return PROMPT_ACADEMICO if occupation in {"solo_estudio", "ambos"} else PROMPT_ACADEMICO


def _prompt_for_more(target: str) -> str:
    return PROMPT_MORE_WORK if target == "work" else PROMPT_MORE_ACADEMIC


def _next_section_target(current_target: str, occupation: str) -> str | None:
    if current_target == "academic" and occupation == "ambos":
        return "work"
    return None


def _parse_occupation(text: str) -> str | None:
    normalized = normalize_text(text)
    normalized = re.sub(r"\s+", " ", normalized).strip(" .:-")

    if _matches_occupation_choice(normalized, "1", {"solo estudio", "solo estudiar"}):
        return "solo_estudio"
    if _matches_occupation_choice(
        normalized,
        "2",
        {"ambos", "estudio y trabajo", "trabajo y estudio"},
    ):
        return "ambos"
    if _matches_occupation_choice(
        normalized,
        "3",
        {"ninguna", "ninguna de las anteriores"},
    ):
        return "ninguna"
    return None


def _extract_occupation_reply(text: str) -> tuple[str | None, str | None]:
    raw_text = str(text or "").strip()
    if not raw_text:
        return None, None

    direct_match = _parse_occupation(raw_text)
    if direct_match is not None:
        return direct_match, None

    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    if not lines:
        return None, None

    first_line_match = _parse_occupation(lines[0])
    if first_line_match is None:
        return None, None

    remainder = "\n".join(lines[1:]).strip()
    return first_line_match, remainder or None


def _matches_occupation_choice(normalized: str, option_number: str, labels: set[str]) -> bool:
    if normalized in labels:
        return True
    if normalized == option_number:
        return True

    option_match = re.fullmatch(
        rf"(?:la\s+)?(?:opcion\s+)?{option_number}(?:\s+(?P<label>.+))?",
        normalized,
    )
    if option_match is None:
        return False

    label = str(option_match.group("label") or "").strip(" .:-")
    return not label or label in labels


def _parse_more_decision(text: str | None) -> str | None:
    normalized = normalize_text(text or "")
    if not normalized:
        return None
    if normalized in _CONTINUE_TOKENS or any(
        contains_normalized_phrase(normalized, token) for token in _CONTINUE_TOKENS
    ):
        return "continue"
    if any(
        contains_normalized_phrase(normalized, token)
        for token in ("si", "sí", "claro", "agregar", "mas", "más", "otro", "otra")
    ):
        return "more"
    return None


def _looks_like_schedule_content(text: str | None) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    return has_time_range(raw) or bool(_DAY_HINT_PATTERN.search(raw))


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
            "schedule": {
                **schedule_state,
                "capture_target": target,
                "capture_stage": "awaiting_input",
            },
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
            "schedule": {
                **schedule_state,
                "blocks": updated_blocks,
                "capture_target": next_target,
                "capture_stage": "awaiting_input",
            },
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
        "schedule": {
            **schedule_state,
            "blocks": updated_blocks,
            "capture_target": target,
            "capture_stage": "awaiting_more",
        },
        "academic_pending_items": academic_pending_items,
        "work_pending_items": work_pending_items,
        "phase": "schedules",
        "user_message_count": current_count,
        "last_user_text": response_text,
        "awaiting_user_input": True,
        "messages": append_message(
            state.get("messages", []),
            "assistant",
            _prompt_for_more(target),
        ),
    }


def _build_schedule_update(
    state: AgentState,
    *,
    profile: dict,
    raw_inputs: RawInputs,
    schedule_state: dict,
    academic_pending_items: list[PendingScheduleItem],
    work_pending_items: list[PendingScheduleItem],
    phase: str,
    awaiting_user_input: bool,
    current_count: int,
    last_text: str | None,
    prompt: str | None = None,
) -> dict:
    update = {
        "student_profile": profile,
        "raw_inputs": raw_inputs,
        "schedule": schedule_state,
        "academic_pending_items": academic_pending_items,
        "work_pending_items": work_pending_items,
        "phase": phase,
        "user_message_count": current_count,
        "last_user_text": last_text,
        "awaiting_user_input": awaiting_user_input,
    }
    if prompt:
        update["messages"] = append_message(state.get("messages", []), "assistant", prompt)
    return update


def _next_pending_items(
    academic_pending_items: list[PendingScheduleItem],
    work_pending_items: list[PendingScheduleItem],
) -> tuple[str | None, list[PendingScheduleItem]]:
    if academic_pending_items:
        return "academic", academic_pending_items
    if work_pending_items:
        return "work", work_pending_items
    return None, []


def _has_block_type(blocks: list, block_type: str) -> bool:
    for block in blocks or []:
        current_type = block.get("block_type") if isinstance(block, dict) else getattr(block, "block_type", None)
        if str(current_type) == block_type:
            return True
    return False
