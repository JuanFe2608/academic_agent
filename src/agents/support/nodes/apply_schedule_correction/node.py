"""Nodo para recalcular solo la sección corregida del horario."""

from __future__ import annotations

from agents.support.nodes.collect_extracurricular_details.parsing import (
    complete_pending_extracurricular_item,
    parse_extracurricular_items,
)
from agents.support.nodes.utils import append_message, normalize_text
from agents.support.scheduling import merge_section_blocks, normalize_schedule_section, replace_section_blocks
from agents.support.scheduling.contextual_parser import (
    build_schedule_pending_prompt,
    complete_pending_schedule_item,
    serialize_blocks_for_schedule_type,
)
from agents.support.scheduling.pipeline import (
    parse_extracurricular_section,
    parse_fixed_schedule_section,
)
from agents.support.state import (
    AgentState,
    ExtracurricularItem,
    PendingExtracurricularItem,
    PendingScheduleItem,
)


def apply_schedule_correction(state: AgentState) -> dict:
    """Reemplaza una sola sección del horario sin reiniciar onboarding."""

    schedule_state = dict(state.get("schedule", {}))
    target = str(schedule_state.get("correction_target") or "").strip()
    text = str(schedule_state.get("pending_correction_text") or "").strip()
    timezone = state.get("timezone", "America/Bogota")
    blocks = list(schedule_state.get("blocks", []))
    pending_items = _coerce_pending_items(state.get("extras_pending_items", []))
    academic_pending_items = _coerce_schedule_pending_items(state.get("academic_pending_items", []))
    work_pending_items = _coerce_schedule_pending_items(state.get("work_pending_items", []))

    if target == "extracurricular" and normalize_text(text) in {
        "ninguna",
        "ninguna actividad",
        "no",
        "no tengo",
    }:
        updated_blocks = replace_section_blocks(blocks, "extracurricular", [])
        return {
            "schedule": {
                **schedule_state,
                "blocks": updated_blocks,
                "summary_text": None,
                "review_stage": "idle",
                "correction_target": None,
                "pending_correction_text": None,
                "conflicts": [],
                "conflicts_accepted": False,
            },
            "extracurricular": [],
            "extras_has_any": False,
            "extras_pending_items": [],
            "phase": "draft",
            "awaiting_user_input": False,
        }

    if target == "extracurricular" and pending_items:
        completed_item, missing = complete_pending_extracurricular_item(
            text,
            pending_items[0],
            expected_is_variable=False,
        )
        if not missing:
            merged_items = _merge_extracurricular_items(
                state.get("extracurricular", []),
                [completed_item],
            )
            completion_text = _build_items_source_text(merged_items)
            result = normalize_schedule_section(
                completion_text,
                "extracurricular",
                timezone=timezone,
            )
            updated_schedule_blocks = replace_section_blocks(
                blocks,
                "extracurricular",
                result.blocks,
            )
            return {
                "schedule": {
                    **schedule_state,
                    "blocks": updated_schedule_blocks,
                    "summary_text": None,
                    "review_stage": "idle",
                    "correction_target": None,
                    "pending_correction_text": None,
                    "conflicts": [],
                    "conflicts_accepted": False,
                },
                "extracurricular": merged_items,
                "extras_has_any": bool(merged_items),
                "extras_pending_items": [],
                "phase": "draft",
                "awaiting_user_input": False,
            }

    target_pending_items = academic_pending_items if target == "academic" else work_pending_items
    if target in {"academic", "work"} and target_pending_items:
        completed_blocks, _clarifications, updated_pending = complete_pending_schedule_item(
            text,
            target_pending_items[0],
            timezone=timezone,
        )
        if updated_pending is not None:
            refreshed_items = [updated_pending] + target_pending_items[1:]
            return {
                "schedule": {
                    **schedule_state,
                    "review_stage": "awaiting_correction_payload",
                },
                "academic_pending_items": refreshed_items if target == "academic" else academic_pending_items,
                "work_pending_items": refreshed_items if target == "work" else work_pending_items,
                "phase": "validate",
                "awaiting_user_input": True,
                "messages": append_message(
                    state.get("messages", []),
                    "assistant",
                    build_schedule_pending_prompt(target, refreshed_items),
                ),
            }

        current_section_blocks = [
            block
            for block in blocks
            if str(block.get("block_type") if isinstance(block, dict) else block.block_type) == target
        ]
        merged_target_blocks = merge_section_blocks(current_section_blocks, completed_blocks)
        updated_schedule_blocks = replace_section_blocks(
            blocks,
            target,
            merged_target_blocks,
        )
        raw_inputs = dict(state.get("raw_inputs", {}))
        if target == "academic":
            raw_inputs["horario_academico_text"] = serialize_blocks_for_schedule_type(
                merged_target_blocks,
                "academic",
            )
            academic_pending_items = target_pending_items[1:]
        else:
            raw_inputs["horario_laboral_text"] = serialize_blocks_for_schedule_type(
                merged_target_blocks,
                "work",
            )
            work_pending_items = target_pending_items[1:]

        remaining_target_items = academic_pending_items if target == "academic" else work_pending_items
        if remaining_target_items:
            return {
                "schedule": {
                    **schedule_state,
                    "blocks": updated_schedule_blocks,
                    "review_stage": "awaiting_correction_payload",
                    "pending_correction_text": None,
                },
                "raw_inputs": raw_inputs,
                "academic_pending_items": academic_pending_items,
                "work_pending_items": work_pending_items,
                "phase": "validate",
                "awaiting_user_input": True,
                "messages": append_message(
                    state.get("messages", []),
                    "assistant",
                    build_schedule_pending_prompt(target, remaining_target_items),
                ),
            }

        return {
            "schedule": {
                **schedule_state,
                "blocks": updated_schedule_blocks,
                "summary_text": None,
                "review_stage": "idle",
                "correction_target": None,
                "pending_correction_text": None,
                "conflicts": [],
                "conflicts_accepted": False,
            },
            "raw_inputs": raw_inputs,
            "academic_pending_items": academic_pending_items,
            "work_pending_items": work_pending_items,
            "phase": "draft",
            "extras_pending_items": [],
            "awaiting_user_input": False,
        }

    if target in {"academic", "work"}:
        section_result = parse_fixed_schedule_section(
            text,
            target,  # type: ignore[arg-type]
            timezone=timezone,
        )
        if section_result.pending_schedule_items:
            updated_schedule_blocks = replace_section_blocks(blocks, target, section_result.blocks)
            return {
                "schedule": {
                    **schedule_state,
                    "blocks": updated_schedule_blocks,
                    "review_stage": "awaiting_correction_payload",
                },
                "academic_pending_items": section_result.pending_schedule_items if target == "academic" else academic_pending_items,
                "work_pending_items": section_result.pending_schedule_items if target == "work" else work_pending_items,
                "phase": "validate",
                "awaiting_user_input": True,
                "messages": append_message(
                    state.get("messages", []),
                    "assistant",
                    build_schedule_pending_prompt(target, section_result.pending_schedule_items, section_result.clarifications),
                ),
            }

    result = normalize_schedule_section(text, target or "academic", timezone=timezone)
    if result.needs_clarification:
        if target == "extracurricular":
            section_result = parse_extracurricular_section(
                text,
                timezone=timezone,
                expected_is_variable=False,
            )
            return {
                "schedule": {
                    **schedule_state,
                    "review_stage": "awaiting_correction_payload",
                },
                "extracurricular": section_result.extracurricular_items,
                "extras_has_any": bool(section_result.extracurricular_items),
                "extras_pending_items": section_result.pending_extracurricular_items,
                "phase": "validate",
                "awaiting_user_input": True,
                "messages": append_message(
                    state.get("messages", []),
                    "assistant",
                    _build_extracurricular_correction_prompt(
                        section_result.clarifications or result.clarifications,
                        section_result.pending_extracurricular_items,
                    ),
                ),
            }
        if target in {"academic", "work"}:
            section_result = parse_fixed_schedule_section(
                text,
                target,  # type: ignore[arg-type]
                timezone=timezone,
            )
            if section_result.blocks and not section_result.pending_schedule_items:
                updated_schedule_blocks = replace_section_blocks(blocks, target, section_result.blocks)
                raw_inputs = dict(state.get("raw_inputs", {}))
                if target == "academic":
                    raw_inputs["horario_academico_text"] = serialize_blocks_for_schedule_type(
                        section_result.blocks,
                        "academic",
                    )
                else:
                    raw_inputs["horario_laboral_text"] = serialize_blocks_for_schedule_type(
                        section_result.blocks,
                        "work",
                    )
                return {
                    "schedule": {
                        **schedule_state,
                        "blocks": updated_schedule_blocks,
                        "summary_text": None,
                        "review_stage": "idle",
                        "correction_target": None,
                        "pending_correction_text": None,
                        "conflicts": [],
                        "conflicts_accepted": False,
                    },
                    "raw_inputs": raw_inputs,
                    "academic_pending_items": [],
                    "work_pending_items": [],
                    "phase": "draft",
                    "extras_pending_items": [],
                    "awaiting_user_input": False,
                }
            updated_schedule_blocks = replace_section_blocks(
                blocks,
                target,
                section_result.blocks,
            )
            return {
                "schedule": {
                    **schedule_state,
                    "blocks": updated_schedule_blocks,
                    "review_stage": "awaiting_correction_payload",
                },
                "academic_pending_items": section_result.pending_schedule_items if target == "academic" else academic_pending_items,
                "work_pending_items": section_result.pending_schedule_items if target == "work" else work_pending_items,
                "phase": "validate",
                "awaiting_user_input": True,
                "messages": append_message(
                    state.get("messages", []),
                    "assistant",
                    build_schedule_pending_prompt(
                        target,
                        section_result.pending_schedule_items,
                        section_result.clarifications or result.clarifications,
                    ),
                ),
            }
        return {
            "schedule": {
                **schedule_state,
                "review_stage": "awaiting_correction_payload",
            },
            "academic_pending_items": academic_pending_items,
            "work_pending_items": work_pending_items,
            "phase": "validate",
            "awaiting_user_input": True,
            "messages": append_message(
                state.get("messages", []),
                "assistant",
                "\n".join(result.clarifications),
            ),
        }

    updated_schedule_blocks = replace_section_blocks(
        blocks,
        target or "academic",
        result.blocks,
    )
    update: dict[str, object] = {
        "schedule": {
            **schedule_state,
            "blocks": updated_schedule_blocks,
            "summary_text": None,
            "review_stage": "idle",
            "correction_target": None,
            "pending_correction_text": None,
            "conflicts": [],
            "conflicts_accepted": False,
        },
        "phase": "draft",
        "academic_pending_items": [],
        "work_pending_items": [],
        "extras_pending_items": [],
        "awaiting_user_input": False,
    }
    if target == "academic":
        raw_inputs = dict(state.get("raw_inputs", {}))
        raw_inputs["horario_academico_text"] = text
        update["raw_inputs"] = raw_inputs
    elif target == "work":
        raw_inputs = dict(state.get("raw_inputs", {}))
        raw_inputs["horario_laboral_text"] = text
        update["raw_inputs"] = raw_inputs
    elif target == "extracurricular":
        items, _ = parse_extracurricular_items(text, expected_is_variable=False)
        update["extracurricular"] = items
        update["extras_has_any"] = bool(items)
    return update


def _coerce_pending_items(
    raw_items: list[PendingExtracurricularItem] | list[dict],
) -> list[PendingExtracurricularItem]:
    return [
        item if isinstance(item, PendingExtracurricularItem) else PendingExtracurricularItem(**item)
        for item in raw_items
    ]


def _coerce_schedule_pending_items(
    raw_items: list[PendingScheduleItem] | list[dict],
) -> list[PendingScheduleItem]:
    return [
        item if isinstance(item, PendingScheduleItem) else PendingScheduleItem(**item)
        for item in raw_items
    ]


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


def _build_items_source_text(items: list[ExtracurricularItem]) -> str:
    lines: list[str] = []
    for item in items:
        if not item.dias or not item.hora_inicio or not item.hora_fin:
            continue
        lines.append(
            " ".join(
                [
                    item.nombre.strip(),
                    ", ".join(item.dias),
                    f"{item.hora_inicio}-{item.hora_fin}",
                ]
            ).strip()
        )
    return "\n".join(lines)


def _build_extracurricular_correction_prompt(
    clarifications: list[str],
    pending_items: list[PendingExtracurricularItem],
) -> str:
    lines = [str(item).strip() for item in clarifications if str(item).strip()]
    if pending_items:
        current = pending_items[0]
        missing_text = ", ".join(current.missing_fields) if current.missing_fields else "datos del horario"
        if missing_text == "hora de inicio y fin":
            lines.append("Puedes responder solo con lo que falta. Ejemplo: de 7 am a 8 am.")
        else:
            lines.append("Si prefieres, envíala completa en formato: Actividad dia(s) de HH:MM a HH:MM.")
    return "\n".join(lines)
