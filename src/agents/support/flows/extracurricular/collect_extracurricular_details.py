"""Nodo para recolectar detalles de actividades extracurriculares."""

from __future__ import annotations

import re

from agents.support.nodes.utils import (
    append_message,
    contains_normalized_phrase,
    detect_new_input,
    has_time_range,
    normalize_text,
    parse_numbered_option,
    parse_yes_no,
)
from agents.support.runtime_state_helpers import update_conversation_state
from agents.support.scheduling import normalize_schedule_section
from services.scheduling.extracurricular_state import (
    build_extracurricular_item_source_text as shared_build_extracurricular_item_source_text,
    coerce_extracurricular_pending_items as shared_coerce_extracurricular_pending_items,
    merge_extracurricular_items as shared_merge_extracurricular_items,
)
from services.scheduling.pending_extracurricular_support import (
    build_extracurricular_pending_prompt as shared_build_extracurricular_pending_prompt,
)
from services.scheduling.pending_slot_state import extracurricular_pending_interaction_update
from agents.support.scheduling.state_helpers import (
    ensure_schedule_flow_state,
    reset_schedule_review_state,
    update_scheduling_state,
)
from agents.support.state import AgentState
from schemas.scheduling import ExtracurricularItem, PendingExtracurricularItem
from services.scheduling.extracurricular_parsing import (
    complete_pending_extracurricular_item,
    parse_extracurricular_items_with_context,
)
from services.scheduling.section_mutations import append_section_blocks
from services.scheduling.block_operations import current_section_blocks
from agents.support.nodes.collect_extracurricular_details.prompt import (
    PROMPT_DETAILS,
    PROMPT_MORE,
)
from agents.support.flows.scheduling.section_confirmation_service import (
    SectionReviewCompletion,
    handle_section_review_turn,
    has_active_section_review,
    start_section_review,
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
    r"\b(lunes|martes|miercoles|miércoles|jueves|viernes|sabado|sábado|domingo|"
    r"lun|mar|mie|jue|vie|sab|dom|todos los dias|todos los días|cada dia|cada día)\b",
    re.IGNORECASE,
)
_MORE_EXTRAS_INLINE_PREFIXES = (
    re.compile(
        r"^\s*(?:1(?:[\).\:-]?\s*)?)?(?:(?:si|sí)\s*,?\s*)?quiero\s+agregar\s+m[aá]s\s+actividades(?:\s+extracurriculares)?[\s:,\-]+(?P<content>.+)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?:1(?:[\).\:-]?\s*)?)?agregar\s+m[aá]s\s+actividades(?:\s+extracurriculares)?[\s:,\-]+(?P<content>.+)$",
        re.IGNORECASE,
    ),
)


def _build_extras_update(
    state: AgentState,
    *,
    phase: str,
    awaiting_user_input: bool,
    current_count: int,
    last_text: str | None,
    prompt: str | None = None,
    **scheduling_changes: object,
) -> dict:
    conversation_changes: dict[str, object] = {
        "phase": phase,
        "user_message_count": current_count,
        "last_user_text": last_text,
        "awaiting_user_input": awaiting_user_input,
    }
    if prompt:
        conversation_changes["messages"] = append_message(
            state.get("messages", []),
            "assistant",
            prompt,
        )
    update = {
        **update_scheduling_state(state, **scheduling_changes),
        **update_conversation_state(state, **conversation_changes),
    }
    if "extras_pending_items" in scheduling_changes:
        update.update(
            extracurricular_pending_interaction_update(
                state,
                pending_items=scheduling_changes.get("extras_pending_items") or [],
            )
        )
    return update


def collect_extracurricular_details(state: AgentState) -> dict:
    """Recolecta actividades extracurriculares y avanza al draft."""
    messages = state.get("messages", [])
    has_new_input, last_text, current_count = detect_new_input(
        messages,
        state.get("user_message_count", 0),
        state.get("awaiting_user_input", False),
        state.get("last_user_text"),
    )
    stage = state.get("extras_collect_stage") or "awaiting_type"
    pending_is_variable = state.get("extras_pending_is_variable")
    pending_items = _coerce_pending_items(state.get("extras_pending_items", []))
    schedule_state = ensure_schedule_flow_state(state.get("schedule", {}))

    if has_active_section_review(state) and str(schedule_state.correction_target or "") == "extracurricular":
        return handle_section_review_turn(
            state,
            has_new_input=has_new_input,
            last_text=last_text,
            current_count=current_count,
            completion=SectionReviewCompletion(
                phase="draft",
                awaiting_user_input=False,
                prompt="Listo. Voy a preparar el resumen de tu horario.",
                schedule_changes={"capture_target": None, "capture_stage": "idle"},
                scheduling_changes={
                    "extras_collect_stage": "done",
                    "extras_pending_is_variable": None,
                    "extras_pending_items": [],
                },
            ),
        )

    if stage == "awaiting_more":
        normalized_reply = normalize_text(last_text or "") if has_new_input else ""
        numeric_choice = parse_numbered_option(last_text) if has_new_input else None
        answer = parse_yes_no(last_text) if has_new_input else None
        content_payload = (
            _extract_extracurricular_content_from_more_reply(last_text)
            if has_new_input
            else None
        )
        has_registered_blocks = bool(
            current_section_blocks(schedule_state.blocks, "extracurricular")
        )
        if normalized_reply in _CONTINUE_TOKENS or any(
            contains_normalized_phrase(normalized_reply, token) for token in _CONTINUE_TOKENS
        ):
            if not has_registered_blocks:
                return _build_extras_update(
                    state,
                    extras_collect_stage="done",
                    extras_pending_is_variable=None,
                    extras_pending_items=[],
                    phase="draft",
                    current_count=current_count if has_new_input else state.get("user_message_count", 0),
                    last_text=last_text if has_new_input else state.get("last_user_text"),
                    awaiting_user_input=False,
                    prompt="Listo. Voy a preparar el resumen de tu horario.",
                )
            return start_section_review(
                state,
                target="extracurricular",
                phase="extras",
                current_count=current_count if has_new_input else state.get("user_message_count", 0),
                last_text=last_text if has_new_input else state.get("last_user_text"),
            )

        if has_new_input and _looks_like_extracurricular_content(content_payload or last_text):
            stage = "awaiting_details"
        else:
            if answer is False or numeric_choice == 2:
                if not has_registered_blocks:
                    return _build_extras_update(
                        state,
                        extras_collect_stage="done",
                        extras_pending_is_variable=None,
                        extras_pending_items=[],
                        phase="draft",
                        current_count=current_count if has_new_input else state.get("user_message_count", 0),
                        last_text=last_text if has_new_input else state.get("last_user_text"),
                        awaiting_user_input=False,
                        prompt="Listo. Voy a preparar el resumen de tu horario.",
                    )
                return start_section_review(
                    state,
                    target="extracurricular",
                    phase="extras",
                    current_count=current_count if has_new_input else state.get("user_message_count", 0),
                    last_text=last_text if has_new_input else state.get("last_user_text"),
                )

            if numeric_choice == 1 or answer is True or any(
                contains_normalized_phrase(normalized_reply, token)
                for token in ("agregar", "mas", "más", "otro", "otra")
            ):
                return _build_extras_update(
                    state,
                    extras_collect_stage="awaiting_details",
                    extras_pending_is_variable=None,
                    extras_pending_items=[],
                    phase="extras",
                    current_count=current_count,
                    last_text=last_text,
                    awaiting_user_input=True,
                    prompt=PROMPT_DETAILS,
                )

            return _build_extras_update(
                state,
                extras_collect_stage="awaiting_more",
                phase="extras",
                current_count=current_count if has_new_input else state.get("user_message_count", 0),
                last_text=last_text if has_new_input else state.get("last_user_text"),
                awaiting_user_input=True,
                prompt=PROMPT_MORE,
            )

    if stage in (None, "awaiting_type"):
        return _build_extras_update(
            state,
            extras_collect_stage="awaiting_details",
            extras_pending_is_variable=pending_is_variable,
            extras_pending_items=pending_items,
            phase="extras",
            current_count=state.get("user_message_count", 0),
            last_text=state.get("last_user_text"),
            awaiting_user_input=True,
            prompt=_build_pending_prompt(pending_items) if pending_items else PROMPT_DETAILS,
        )

    if not has_new_input or not last_text:
        return _build_extras_update(
            state,
            extras_collect_stage="awaiting_details",
            extras_pending_is_variable=pending_is_variable,
            extras_pending_items=pending_items,
            phase="extras",
            current_count=state.get("user_message_count", 0),
            last_text=state.get("last_user_text"),
            awaiting_user_input=True,
            prompt=_build_pending_prompt(pending_items) if pending_items else PROMPT_DETAILS,
        )

    timezone = state.get("timezone", "America/Bogota")
    effective_text = _extract_extracurricular_content_from_more_reply(last_text)
    if pending_items:
        completion = _complete_pending_item_reply(
            state=state,
            response_text=effective_text or last_text,
            pending_items=pending_items,
            pending_is_variable=pending_is_variable,
            current_count=current_count,
        )
        if completion is not None:
            return completion

    result = normalize_schedule_section(
        effective_text or last_text,
        "extracurricular",
        timezone=timezone,
    )
    items, _missing, parsed_pending_items = parse_extracurricular_items_with_context(
        effective_text or last_text,
        expected_is_variable=pending_is_variable,
    )
    extracurricular = _merge_extracurricular_items(state.get("extracurricular", []), items)
    schedule_state = dict(state.get("schedule", {}))
    schedule_blocks = append_section_blocks(
        list(schedule_state.get("blocks", [])),
        result.blocks,
    )
    if result.needs_clarification:
        prompt = _build_clarification_prompt(
            result.clarifications,
            items,
            parsed_pending_items,
        )
        return _build_extras_update(
            state,
            extracurricular=extracurricular,
            schedule=reset_schedule_review_state(schedule_state, schedule_blocks),
            extras_collect_stage="awaiting_details",
            extras_pending_is_variable=pending_is_variable,
            extras_pending_items=parsed_pending_items,
            phase="extras",
            current_count=current_count if has_new_input else state.get("user_message_count", 0),
            last_text=last_text if has_new_input else state.get("last_user_text"),
            awaiting_user_input=True,
            prompt=prompt,
        )

    return _build_extras_update(
        state,
        extracurricular=extracurricular,
        schedule=reset_schedule_review_state(schedule_state, schedule_blocks),
        extras_collect_stage="awaiting_more",
        extras_pending_is_variable=None,
        extras_pending_items=[],
        phase="extras",
        current_count=current_count if has_new_input else state.get("user_message_count", 0),
        last_text=last_text if has_new_input else state.get("last_user_text"),
        awaiting_user_input=True,
        prompt=PROMPT_MORE,
    )


def _looks_like_extracurricular_content(text: str | None) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    normalized = normalize_text(raw)
    return bool(
        has_time_range(raw)
        or _DAY_HINT_PATTERN.search(raw)
        or "todos los dias" in normalized
        or "todos los días" in raw.lower()
    )


def _extract_extracurricular_content_from_more_reply(text: str | None) -> str | None:
    raw = str(text or "").strip()
    if not raw:
        return raw

    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if len(lines) > 1:
        first_line = normalize_text(lines[0])
        if first_line.startswith("1") or any(
            contains_normalized_phrase(first_line, token)
            for token in (
                "quiero agregar más actividades",
                "quiero agregar mas actividades",
                "agregar más actividades",
                "agregar mas actividades",
            )
        ):
            remainder = "\n".join(lines[1:]).strip()
            if remainder:
                return remainder

    for pattern in _MORE_EXTRAS_INLINE_PREFIXES:
        match = pattern.match(raw)
        if match is None:
            continue
        candidate = str(match.group("content") or "").strip()
        if candidate:
            return candidate

    return raw


def _merge_extracurricular_items(
    existing: list[ExtracurricularItem] | list[dict],
    new_items: list[ExtracurricularItem],
) -> list[ExtracurricularItem]:
    return shared_merge_extracurricular_items(existing, new_items)


def _coerce_pending_items(
    raw_items: list[PendingExtracurricularItem] | list[dict],
) -> list[PendingExtracurricularItem]:
    return shared_coerce_extracurricular_pending_items(raw_items)


def _complete_pending_item_reply(
    state: AgentState,
    response_text: str,
    pending_items: list[PendingExtracurricularItem],
    pending_is_variable: bool | None,
    current_count: int,
) -> dict | None:
    if not pending_items:
        return None

    completed_item, missing = complete_pending_extracurricular_item(
        response_text,
        pending_items[0],
        expected_is_variable=pending_is_variable,
    )
    if missing:
        return None

    schedule_state = dict(state.get("schedule", {}))
    messages = state.get("messages", [])
    merged_items = _merge_extracurricular_items(
        state.get("extracurricular", []),
        [completed_item],
    )
    completion_text = _build_item_source_text(completed_item)
    completion_result = normalize_schedule_section(
        completion_text,
        "extracurricular",
        timezone=state.get("timezone", "America/Bogota"),
    )
    schedule_blocks = append_section_blocks(
        list(schedule_state.get("blocks", [])),
        completion_result.blocks,
    )
    remaining_pending = pending_items[1:]

    if remaining_pending:
        return _build_extras_update(
            state,
            extracurricular=merged_items,
            schedule=reset_schedule_review_state(schedule_state, schedule_blocks),
            extras_collect_stage="awaiting_details",
            extras_pending_is_variable=pending_is_variable,
            extras_pending_items=remaining_pending,
            phase="extras",
            current_count=current_count,
            last_text=response_text,
            awaiting_user_input=True,
            prompt=_build_pending_prompt(remaining_pending),
        )

    return _build_extras_update(
        state,
        extracurricular=merged_items,
        schedule=reset_schedule_review_state(schedule_state, schedule_blocks),
        extras_collect_stage="awaiting_more",
        extras_pending_is_variable=None,
        extras_pending_items=[],
        phase="extras",
        current_count=current_count,
        last_text=response_text,
        awaiting_user_input=True,
        prompt=PROMPT_MORE,
    )


def _build_item_source_text(item: ExtracurricularItem) -> str:
    return shared_build_extracurricular_item_source_text(item)


def _build_clarification_prompt(
    clarifications: list[str],
    parsed_items: list[ExtracurricularItem],
    pending_items: list[PendingExtracurricularItem],
) -> str:
    lines: list[str] = []
    names = [item.nombre.strip() for item in parsed_items if item.nombre.strip()]
    unique_names = list(dict.fromkeys(names))
    if unique_names:
        lines.append("Ya registré: " + ", ".join(unique_names) + ".")
    lines.extend(str(item).strip() for item in clarifications if str(item).strip())
    if pending_items:
        lines.append(_build_pending_reply_hint(pending_items[0]))
    else:
        lines.append(
            "Envíame solo lo que falta con este formato: Actividad dia(s) de HH:MM a HH:MM."
        )
    return "\n".join(lines) if lines else PROMPT_DETAILS


def _build_pending_prompt(
    pending_items: list[PendingExtracurricularItem],
) -> str:
    if not pending_items:
        return PROMPT_DETAILS
    return shared_build_extracurricular_pending_prompt(pending_items)


def _build_pending_reply_hint(item: PendingExtracurricularItem) -> str:
    return shared_build_extracurricular_pending_prompt([item])
