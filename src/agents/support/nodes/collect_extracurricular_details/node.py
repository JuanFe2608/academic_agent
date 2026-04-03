"""Nodo para recolectar detalles de actividades extracurriculares."""

from __future__ import annotations

import re

from agents.support.nodes.utils import (
    append_message,
    contains_normalized_phrase,
    detect_new_input,
    has_time_range,
    normalize_text,
    parse_yes_no,
)
from agents.support.scheduling import merge_section_blocks, normalize_schedule_section
from agents.support.scheduling.extracurricular_support import (
    build_extracurricular_item_source_text as shared_build_extracurricular_item_source_text,
    build_extracurricular_reply_hint as shared_build_extracurricular_reply_hint,
    coerce_extracurricular_pending_items as shared_coerce_extracurricular_pending_items,
    merge_extracurricular_items as shared_merge_extracurricular_items,
)
from agents.support.scheduling.state_helpers import reset_schedule_review_state
from agents.support.state import AgentState, ExtracurricularItem, PendingExtracurricularItem

from .prompt import (
    PROMPT_DETAILS,
    PROMPT_MORE,
)
from .parsing import (
    complete_pending_extracurricular_item,
    parse_extracurricular_items_with_context,
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

    if stage == "awaiting_more":
        normalized_reply = normalize_text(last_text or "") if has_new_input else ""
        answer = parse_yes_no(last_text) if has_new_input else None
        if normalized_reply in _CONTINUE_TOKENS or any(
            contains_normalized_phrase(normalized_reply, token) for token in _CONTINUE_TOKENS
        ):
            return {
                "extras_collect_stage": "done",
                "extras_pending_is_variable": None,
                "extras_pending_items": [],
                "phase": "draft",
                "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
                "last_user_text": last_text if has_new_input else state.get("last_user_text"),
                "awaiting_user_input": False,
                "messages": append_message(
                    messages,
                    "assistant",
                    "Listo. Voy a preparar el resumen de tu horario.",
                ),
            }

        if has_new_input and _looks_like_extracurricular_content(last_text):
            stage = "awaiting_details"
        else:
            if answer is False:
                return {
                    "extras_collect_stage": "done",
                    "extras_pending_is_variable": None,
                    "extras_pending_items": [],
                    "phase": "draft",
                    "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
                    "last_user_text": last_text if has_new_input else state.get("last_user_text"),
                    "awaiting_user_input": False,
                    "messages": append_message(
                        messages,
                        "assistant",
                        "Listo. Voy a preparar el resumen de tu horario.",
                    ),
                }

            if answer is True or any(
                contains_normalized_phrase(normalized_reply, token)
                for token in ("agregar", "mas", "más", "otro", "otra")
            ):
                return {
                    "extras_collect_stage": "awaiting_details",
                    "extras_pending_is_variable": None,
                    "extras_pending_items": [],
                    "phase": "extras",
                    "user_message_count": current_count,
                    "last_user_text": last_text,
                    "awaiting_user_input": True,
                    "messages": append_message(messages, "assistant", PROMPT_DETAILS),
                }

            return {
                "extras_collect_stage": "awaiting_more",
                "phase": "extras",
                "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
                "last_user_text": last_text if has_new_input else state.get("last_user_text"),
                "awaiting_user_input": True,
                "messages": append_message(messages, "assistant", PROMPT_MORE),
            }

    if stage in (None, "awaiting_type"):
        return {
            "extras_collect_stage": "awaiting_details",
            "extras_pending_is_variable": pending_is_variable,
            "extras_pending_items": pending_items,
            "phase": "extras",
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                _build_pending_prompt(pending_items) if pending_items else PROMPT_DETAILS,
            ),
        }

    if not has_new_input or not last_text:
        return {
            "extras_collect_stage": "awaiting_details",
            "extras_pending_is_variable": pending_is_variable,
            "extras_pending_items": pending_items,
            "phase": "extras",
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                _build_pending_prompt(pending_items) if pending_items else PROMPT_DETAILS,
            ),
        }

    timezone = state.get("timezone", "America/Bogota")
    if pending_items:
        completion = _complete_pending_item_reply(
            state=state,
            response_text=last_text,
            pending_items=pending_items,
            pending_is_variable=pending_is_variable,
            current_count=current_count,
        )
        if completion is not None:
            return completion

    result = normalize_schedule_section(
        last_text,
        "extracurricular",
        timezone=timezone,
    )
    items, _missing, parsed_pending_items = parse_extracurricular_items_with_context(
        last_text,
        expected_is_variable=pending_is_variable,
    )
    extracurricular = _merge_extracurricular_items(state.get("extracurricular", []), items)
    schedule_state = dict(state.get("schedule", {}))
    schedule_blocks = merge_section_blocks(
        list(schedule_state.get("blocks", [])),
        result.blocks,
    )
    if result.needs_clarification:
        prompt = _build_clarification_prompt(
            result.clarifications,
            items,
            parsed_pending_items,
        )
        return {
            "extracurricular": extracurricular,
            "schedule": reset_schedule_review_state(schedule_state, schedule_blocks),
            "extras_collect_stage": "awaiting_details",
            "extras_pending_is_variable": pending_is_variable,
            "extras_pending_items": parsed_pending_items,
            "phase": "extras",
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_text if has_new_input else state.get("last_user_text"),
            "awaiting_user_input": True,
            "messages": append_message(messages, "assistant", prompt),
        }

    return {
        "extracurricular": extracurricular,
        "schedule": reset_schedule_review_state(schedule_state, schedule_blocks),
        "extras_collect_stage": "awaiting_more",
        "extras_pending_is_variable": None,
        "extras_pending_items": [],
        "phase": "extras",
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_text if has_new_input else state.get("last_user_text"),
        "awaiting_user_input": True,
        "messages": append_message(messages, "assistant", PROMPT_MORE),
    }


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
    schedule_blocks = merge_section_blocks(
        list(schedule_state.get("blocks", [])),
        completion_result.blocks,
    )
    remaining_pending = pending_items[1:]

    if remaining_pending:
        return {
            "extracurricular": merged_items,
            "schedule": reset_schedule_review_state(schedule_state, schedule_blocks),
            "extras_collect_stage": "awaiting_details",
            "extras_pending_is_variable": pending_is_variable,
            "extras_pending_items": remaining_pending,
            "phase": "extras",
            "user_message_count": current_count,
            "last_user_text": response_text,
            "awaiting_user_input": True,
            "messages": append_message(
                messages,
                "assistant",
                _build_pending_prompt(remaining_pending),
            ),
        }

    return {
        "extracurricular": merged_items,
        "schedule": reset_schedule_review_state(schedule_state, schedule_blocks),
        "extras_collect_stage": "awaiting_more",
        "extras_pending_is_variable": None,
        "extras_pending_items": [],
        "phase": "extras",
        "user_message_count": current_count,
        "last_user_text": response_text,
        "awaiting_user_input": True,
        "messages": append_message(messages, "assistant", PROMPT_MORE),
    }


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
    include_registered: bool = True,
) -> str:
    if not pending_items:
        return PROMPT_DETAILS

    current = pending_items[0]
    missing_text = ", ".join(current.missing_fields) if current.missing_fields else "datos del horario"
    name = current.nombre.strip() or "esa actividad"
    example = (
        "Puedes responder solo con lo que falta. Ejemplo: de 7 am a 8 am."
        if missing_text == "hora de inicio y fin"
        else "Si prefieres, envíala completa en formato: Actividad dia(s) de HH:MM a HH:MM."
    )
    prefix = "Me falta completar " if include_registered else ""
    return f"{prefix}{name}: {missing_text}.\n{example}"


def _build_pending_reply_hint(item: PendingExtracurricularItem) -> str:
    return shared_build_extracurricular_reply_hint(item)
