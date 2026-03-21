"""Nodo para recolectar detalles de actividades extracurriculares."""

from __future__ import annotations

from agents.support.nodes.utils import (
    append_message,
    detect_new_input,
    normalize_text,
    parse_yes_no,
)
from agents.support.scheduling import merge_section_blocks, normalize_schedule_section
from agents.support.state import AgentState, ExtracurricularItem, PendingExtracurricularItem

from .prompt import (
    PROMPT_DETAILS,
    PROMPT_MORE,
)
from .parsing import (
    complete_pending_extracurricular_item,
    parse_extracurricular_items_with_context,
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
        answer = parse_yes_no(last_text) if has_new_input else None
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
        if answer is True or (has_new_input and last_text and answer is None):
            if answer is True:
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
            stage = "awaiting_details"
        else:
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
            "schedule": {
                **schedule_state,
                "blocks": schedule_blocks,
                "summary_text": None,
                "review_stage": "idle",
                "conflicts": [],
            },
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
        "schedule": {
            **schedule_state,
            "blocks": schedule_blocks,
            "summary_text": None,
            "review_stage": "idle",
            "conflicts": [],
        },
        "extras_collect_stage": "awaiting_more",
        "extras_pending_is_variable": None,
        "extras_pending_items": [],
        "phase": "extras",
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_text if has_new_input else state.get("last_user_text"),
        "awaiting_user_input": True,
        "messages": append_message(messages, "assistant", PROMPT_MORE),
    }


def _merge_extracurricular_items(
    existing: list[ExtracurricularItem] | list[dict],
    new_items: list[ExtracurricularItem],
) -> list[ExtracurricularItem]:
    merged: list[ExtracurricularItem] = []
    seen: set[tuple[str, tuple[str, ...], str, str, bool]] = set()
    for raw_item in list(existing) + list(new_items):
        item = raw_item if isinstance(raw_item, ExtracurricularItem) else ExtracurricularItem(**raw_item)
        key = (
            normalize_text(item.nombre),
            tuple(item.dias),
            str(item.hora_inicio or ""),
            str(item.hora_fin or ""),
            bool(item.es_variable),
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


def _coerce_pending_items(
    raw_items: list[PendingExtracurricularItem] | list[dict],
) -> list[PendingExtracurricularItem]:
    return [
        item if isinstance(item, PendingExtracurricularItem) else PendingExtracurricularItem(**item)
        for item in raw_items
    ]


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
            "schedule": {
                **schedule_state,
                "blocks": schedule_blocks,
                "summary_text": None,
                "review_stage": "idle",
                "conflicts": [],
            },
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
        "schedule": {
            **schedule_state,
            "blocks": schedule_blocks,
            "summary_text": None,
            "review_stage": "idle",
            "conflicts": [],
        },
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
    days = ", ".join(item.dias) if item.dias else ""
    hours = ""
    if item.hora_inicio and item.hora_fin:
        hours = f"{item.hora_inicio}-{item.hora_fin}"
    return " ".join(part for part in [item.nombre.strip(), days, hours] if part).strip()


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
    missing_text = ", ".join(item.missing_fields) if item.missing_fields else ""
    if missing_text == "hora de inicio y fin":
        return "Puedes responder solo con lo que falta. Ejemplo: de 7 am a 8 am."
    return "Si prefieres, envíala completa en formato: Actividad dia(s) de HH:MM a HH:MM."
