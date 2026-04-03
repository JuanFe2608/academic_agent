"""Servicios compartidos para resolver pendientes del flujo de scheduling.

Este módulo agrupa la lógica de aplicación reutilizada por la captura inicial de
horarios y por la corrección posterior de secciones. No reemplaza los parsers ni
la normalización existente; actúa como capa de coordinación sobre esas piezas
para mantener el comportamiento actual del grafo.
"""

from __future__ import annotations

from agents.support.nodes.utils import append_message
from agents.support.scheduling import merge_section_blocks, replace_section_blocks
from agents.support.scheduling.contextual_parser import (
    build_schedule_pending_prompt,
    complete_pending_schedule_item,
)
from agents.support.state import (
    AgentState,
    PendingScheduleItem,
)

from .state_helpers import (
    ensure_schedule_flow_state,
    serialize_schedule_blocks_to_raw_inputs,
    update_schedule_flow_state,
)


def coerce_schedule_pending_items(
    raw_items: list[PendingScheduleItem] | list[dict],
) -> list[PendingScheduleItem]:
    """Convierte items pendientes académicos/laborales al tipo canónico."""

    return [
        item if isinstance(item, PendingScheduleItem) else PendingScheduleItem(**item)
        for item in raw_items
    ]


def has_block_type(blocks: list, block_type: str) -> bool:
    """Indica si una lista de bloques contiene un tipo específico."""

    for block in blocks or []:
        current_type = (
            block.get("block_type") if isinstance(block, dict) else getattr(block, "block_type", None)
        )
        if str(current_type) == block_type:
            return True
    return False


def resolve_capture_pending_reply(
    state: AgentState,
    *,
    raw_inputs: dict,
    schedule_state: object,
    academic_pending_items: list[PendingScheduleItem],
    work_pending_items: list[PendingScheduleItem],
    response_text: str,
    current_count: int,
    more_prompt: str | None = None,
) -> dict | None:
    """Completa el siguiente pendiente de captura y construye el update resultante."""

    schedule_flow_state = ensure_schedule_flow_state(schedule_state)
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
            "schedule": update_schedule_flow_state(
                schedule_flow_state,
                capture_target=target,
                capture_stage="awaiting_input",
            ),
            "academic_pending_items": (
                refreshed_items if target == "academic" else academic_pending_items
            ),
            "work_pending_items": (
                refreshed_items if target == "work" else work_pending_items
            ),
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

    existing_blocks = list(schedule_flow_state.blocks)
    current_section_blocks = [
        block
        for block in existing_blocks
        if str(block.get("block_type") if isinstance(block, dict) else block.block_type)
        == target
    ]
    merged_target_blocks = merge_section_blocks(current_section_blocks, completed_blocks)
    updated_blocks = replace_section_blocks(existing_blocks, target, merged_target_blocks)

    updated_raw_inputs = serialize_schedule_blocks_to_raw_inputs(
        raw_inputs,
        target,
        merged_target_blocks,
    )
    if target == "academic":
        academic_pending_items = pending_items[1:]
    else:
        work_pending_items = pending_items[1:]

    next_target, next_items = _next_pending_items(academic_pending_items, work_pending_items)
    if next_target is not None and next_items:
        return {
            "raw_inputs": updated_raw_inputs,
            "schedule": update_schedule_flow_state(
                schedule_flow_state,
                blocks=updated_blocks,
                capture_target=next_target,
                capture_stage="awaiting_input",
            ),
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
        "schedule": update_schedule_flow_state(
            schedule_flow_state,
            blocks=updated_blocks,
            capture_target=target,
            capture_stage="awaiting_more",
        ),
        "academic_pending_items": academic_pending_items,
        "work_pending_items": work_pending_items,
        "phase": "schedules",
        "user_message_count": current_count,
        "last_user_text": response_text,
        "awaiting_user_input": True,
        "messages": append_message(
            state.get("messages", []),
            "assistant",
            more_prompt or "",
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
