"""Subflujo conversacional para consultar y modificar horario fijo."""

from __future__ import annotations

from datetime import date

from agents.support.dependencies import (
    get_outlook_fixed_schedule_sync_service,
    get_schedule_service,
)
from agents.support.nodes.utils import append_message, detect_new_input, parse_yes_no
from agents.support.runtime_state_helpers import update_conversation_state
from agents.support.scheduling.conflicts import detect_schedule_conflicts
from agents.support.scheduling.formatter import build_schedule_summary
from agents.support.scheduling.state_helpers import (
    ensure_schedule_flow_state,
    update_schedule_flow_state,
    update_scheduling_state,
)
from agents.support.state import AgentState
from services.conversation.state_helpers import update_interaction_state
from services.scheduling.block_operations import current_section_blocks
from services.scheduling.constants import ScheduleBlockType
from services.scheduling.extracurricular_state import build_extracurricular_items_from_blocks
from services.scheduling.fixed_schedule_management import (
    FixedScheduleOperation,
    build_fixed_schedule_add_preview,
    build_fixed_schedule_summary,
    build_fixed_schedule_update_preview,
    delete_fixed_schedule_blocks,
    format_fixed_schedule_block_options,
    format_fixed_schedule_blocks,
    infer_fixed_schedule_target,
    match_fixed_schedule_blocks,
    parse_fixed_schedule_operation,
    replace_fixed_schedule_blocks,
    select_fixed_schedule_block,
)
from services.scheduling.models import WeeklyScheduleBlock, ensure_weekly_block
from services.scheduling.raw_input_sync import sync_schedule_blocks_to_raw_inputs

_FLOW_DOMAIN = "fixed_schedule_management"
_CONFIRMATION_STAGE = "awaiting_fixed_schedule_confirmation"
_BLOCK_TYPE_QUESTION = (
    "¿El bloque que quieres agregar es:\n"
    "1. Académico (clase, materia, asignatura)\n"
    "2. Laboral (trabajo)\n"
    "3. Extracurricular (deporte, actividad personal)"
)


# ---------------------------------------------------------------------------
# Helpers de renderizado visual
# ---------------------------------------------------------------------------


def _try_render_schedule_content(
    blocks: list[WeeklyScheduleBlock],
    text: str,
    timezone: str = "America/Bogota",
) -> str | list:
    """Renderiza imagen del horario con texto como caption; cae a texto si falla."""
    if not blocks:
        return text
    try:
        from agents.support.scheduling.render import build_rendered_schedule_message_content
        content, _ = build_rendered_schedule_message_content(text, blocks, timezone_name=timezone)
        return content
    except Exception:
        return text


def handle_fixed_schedule_management_turn(state: AgentState) -> dict:
    """Gestiona ver, editar y eliminar horario fijo ya registrado."""

    messages = state.get("messages", [])
    has_new_input, last_text, current_count = detect_new_input(
        messages,
        state.get("user_message_count", 0),
        state.get("awaiting_user_input", False),
        state.get("last_user_text"),
    )
    if not has_new_input:
        replan_raw = dict(state.get("replan", {}))
        change_request = _current_change_request(replan_raw)
        if str(change_request.get("stage") or "").strip():
            return {"phase": "fixed_schedule_management", "awaiting_user_input": True}
        # Initial entry (no active stage) — show the options menu
        return _prompt_update(
            state,
            phase="fixed_schedule_management",
            current_count=current_count,
            last_text=last_text,
            awaiting_user_input=True,
            prompt=(
                "Puedo mostrarte, modificar o eliminar bloques de tu horario fijo. "
                "¿Qué necesitas? Por ejemplo: 'ver mi horario', 'cambiar Cálculo al viernes 10:00-12:00' "
                "o 'eliminar Trabajo del lunes'."
            ),
        )

    blocks, schedule_patch = _current_fixed_schedule_blocks(state)
    replan = dict(state.get("replan", {}))
    change_request = _current_change_request(replan)
    stage = str(change_request.get("stage") or "").strip()

    if stage == "awaiting_fixed_schedule_add_details":
        return _handle_add_details_turn(
            state,
            blocks,
            schedule_patch,
            replan,
            change_request,
            str(last_text or ""),
            current_count,
        )
    if stage == "awaiting_fixed_schedule_block_type":
        return _handle_block_type_turn(
            state,
            blocks,
            schedule_patch,
            replan,
            change_request,
            str(last_text or ""),
            current_count,
        )
    if stage == "awaiting_fixed_schedule_identifier":
        return _handle_identifier_turn(
            state,
            blocks,
            schedule_patch,
            replan,
            change_request,
            str(last_text or ""),
            current_count,
        )
    if stage == "awaiting_fixed_schedule_update_details":
        return _handle_update_details_turn(
            state,
            blocks,
            schedule_patch,
            replan,
            change_request,
            str(last_text or ""),
            current_count,
        )
    if stage == _CONFIRMATION_STAGE:
        return _handle_confirmation_turn(
            state,
            blocks,
            schedule_patch,
            replan,
            change_request,
            str(last_text or ""),
            current_count,
        )

    operation = parse_fixed_schedule_operation(last_text)
    if operation.intent == "view_fixed_schedule":
        return _view_schedule_update(
            state,
            blocks,
            schedule_patch,
            operation,
            str(last_text or ""),
            current_count,
        )
    if operation.intent == "update_fixed_schedule":
        return _start_update_operation(
            state,
            blocks,
            schedule_patch,
            operation,
            str(last_text or ""),
            current_count,
        )
    if operation.intent == "delete_fixed_schedule_item":
        return _start_delete_operation(
            state,
            blocks,
            schedule_patch,
            operation,
            str(last_text or ""),
            current_count,
        )
    if operation.intent == "add_fixed_schedule_item":
        return _start_add_operation(
            state,
            blocks,
            schedule_patch,
            operation,
            str(last_text or ""),
            current_count,
        )

    return _prompt_update(
        state,
        phase="end",
        current_count=current_count,
        last_text=str(last_text or ""),
        awaiting_user_input=False,
        prompt=(
            "Puedo mostrar, cambiar o eliminar bloques de tu horario fijo. "
            "Por ejemplo: 'ver mi horario', 'cambiar Cálculo a viernes 10:00-12:00' "
            "o 'eliminar Trabajo del lunes'."
        ),
        replan=_clear_change_request(replan),
        interaction={
            "active_intent": "manage_fixed_schedule",
            "current_domain": "schedule_management",
            "router_confidence": 0.72,
        },
        **schedule_patch,
    )


def _handle_identifier_turn(
    state: AgentState,
    blocks: list[WeeklyScheduleBlock],
    schedule_patch: dict[str, object],
    replan: dict,
    change_request: dict,
    text: str,
    current_count: int,
) -> dict:
    candidate_ids = [str(item) for item in change_request.get("candidate_block_ids") or []]
    candidates = [block for block in blocks if block.block_id in set(candidate_ids)]
    selected = select_fixed_schedule_block(candidates, text)
    if selected is None:
        return _prompt_update(
            state,
            phase="fixed_schedule_management",
            current_count=current_count,
            last_text=text,
            awaiting_user_input=True,
            prompt=(
                "No pude identificar cuál bloque quieres usar. Elige el número exacto:\n"
                f"{format_fixed_schedule_block_options(candidates)}"
            ),
            replan=_store_change_request(replan, change_request),
            interaction=_pending_interaction(
                state,
                active_intent=str(change_request.get("intent") or "manage_fixed_schedule"),
                pending_action=str(change_request.get("operation") or ""),
                current_step="awaiting_identifier",
            ),
            **schedule_patch,
        )

    operation = str(change_request.get("operation") or "")
    change_request["selected_block_ids"] = [selected.block_id]
    change_request["candidate_block_ids"] = None
    if operation == "delete":
        return _queue_delete_confirmation(
            state,
            blocks,
            schedule_patch,
            replan,
            change_request,
            [selected],
            text,
            current_count,
        )
    update_text = str(change_request.get("update_text") or "").strip()
    if not update_text:
        change_request["stage"] = "awaiting_fixed_schedule_update_details"
        return _prompt_update(
            state,
            phase="fixed_schedule_management",
            current_count=current_count,
            last_text=text,
            awaiting_user_input=True,
            prompt=(
                "Indica el nuevo día y horario para este bloque:\n"
                f"{format_fixed_schedule_blocks([selected])}"
            ),
            replan=_store_change_request(replan, change_request),
            interaction=_pending_interaction(
                state,
                active_intent="update_fixed_schedule",
                pending_action="provide_fixed_schedule_update_details",
                current_step="awaiting_update_details",
            ),
            **schedule_patch,
        )
    return _queue_update_confirmation(
        state,
        blocks,
        schedule_patch,
        replan,
        change_request,
        selected,
        update_text,
        text,
        current_count,
    )


def _handle_update_details_turn(
    state: AgentState,
    blocks: list[WeeklyScheduleBlock],
    schedule_patch: dict[str, object],
    replan: dict,
    change_request: dict,
    text: str,
    current_count: int,
) -> dict:
    selected = _selected_block(blocks, change_request)
    if selected is None:
        change_request["stage"] = "awaiting_fixed_schedule_identifier"
        change_request["candidate_block_ids"] = [block.block_id for block in blocks]
        return _prompt_update(
            state,
            phase="fixed_schedule_management",
            current_count=current_count,
            last_text=text,
            awaiting_user_input=True,
            prompt=(
                "No encontré el bloque seleccionado. Elige el número del bloque a modificar:\n"
                f"{format_fixed_schedule_block_options(blocks)}"
            ),
            replan=_store_change_request(replan, change_request),
            interaction=_pending_interaction(
                state,
                active_intent="update_fixed_schedule",
                pending_action="select_fixed_schedule_item",
                current_step="awaiting_identifier",
            ),
            **schedule_patch,
        )
    return _queue_update_confirmation(
        state,
        blocks,
        schedule_patch,
        replan,
        change_request,
        selected,
        text,
        text,
        current_count,
    )


def _handle_confirmation_turn(
    state: AgentState,
    blocks: list[WeeklyScheduleBlock],
    schedule_patch: dict[str, object],
    replan: dict,
    change_request: dict,
    text: str,
    current_count: int,
) -> dict:
    answer = parse_yes_no(text)
    if answer is None:
        return _prompt_update(
            state,
            phase="fixed_schedule_management",
            current_count=current_count,
            last_text=text,
            awaiting_user_input=True,
            prompt=str(replan.get("pending_prompt") or "Responde sí o no para confirmar el cambio."),
            replan=_store_change_request(replan, change_request),
            interaction=_confirmation_interaction(state, dict(change_request.get("confirmation_payload") or {})),
            **schedule_patch,
        )
    if answer is False:
        return _prompt_update(
            state,
            phase="end",
            current_count=current_count,
            last_text=text,
            awaiting_user_input=False,
            prompt="De acuerdo. No hice cambios en tu horario fijo.",
            replan=_clear_change_request(replan),
            interaction=_clear_interaction(state),
            **schedule_patch,
        )

    operation = str(change_request.get("operation") or "")
    selected_ids = [str(item) for item in change_request.get("selected_block_ids") or []]
    if operation == "delete":
        updated_blocks = delete_fixed_schedule_blocks(blocks, selected_ids)
    elif operation == "add":
        new_blocks = [
            ensure_weekly_block(block)
            for block in change_request.get("new_blocks") or []
        ]
        updated_blocks = list(blocks) + new_blocks
    else:
        replacement_blocks = [
            ensure_weekly_block(block)
            for block in change_request.get("replacement_blocks") or []
        ]
        updated_blocks = replace_fixed_schedule_blocks(blocks, selected_ids, replacement_blocks)
    success_labels = {"delete": "eliminado", "add": "agregado"}
    return _persist_confirmed_schedule_change(
        state,
        updated_blocks,
        replan,
        text,
        current_count,
        success_label=success_labels.get(operation, "actualizado"),
    )


def _view_schedule_update(
    state: AgentState,
    blocks: list[WeeklyScheduleBlock],
    schedule_patch: dict[str, object],
    operation: FixedScheduleOperation,
    text: str,
    current_count: int,
) -> dict:
    summary = build_fixed_schedule_summary(blocks, target=operation.target)
    timezone = str(state.get("timezone", "America/Bogota"))
    visible_blocks = [b for b in blocks if not operation.target or b.block_type == operation.target]
    prompt_content = _try_render_schedule_content(visible_blocks, summary, timezone)
    return _prompt_update(
        state,
        phase="end",
        current_count=current_count,
        last_text=text,
        awaiting_user_input=False,
        prompt=prompt_content,
        replan=_clear_change_request(dict(state.get("replan", {}))),
        interaction={
            "active_intent": "view_fixed_schedule",
            "current_domain": "schedule_management",
            "confirmation_pending": False,
            "last_confirmation_payload": None,
            "pending_action": None,
            "pending_entity_type": None,
            "pending_entity_payload": {},
            "current_step": None,
        },
        **schedule_patch,
    )


def _start_update_operation(
    state: AgentState,
    blocks: list[WeeklyScheduleBlock],
    schedule_patch: dict[str, object],
    operation: FixedScheduleOperation,
    text: str,
    current_count: int,
) -> dict:
    if not blocks:
        return _no_schedule_update(state, schedule_patch, text, current_count)
    if not operation.reference_text:
        change_request = _base_change_request(operation, stage="awaiting_fixed_schedule_identifier")
        change_request["candidate_block_ids"] = [block.block_id for block in _target_blocks(blocks, operation.target)]
        _update_text = (
            "¿Qué bloque de tu horario fijo quieres modificar?\n"
            f"{format_fixed_schedule_block_options(blocks, target=operation.target)}"
        )
        return _prompt_update(
            state,
            phase="fixed_schedule_management",
            current_count=current_count,
            last_text=text,
            awaiting_user_input=True,
            prompt=_try_render_schedule_content(
                _target_blocks(blocks, operation.target) or blocks,
                _update_text,
                str(state.get("timezone", "America/Bogota")),
            ),
            replan=_store_change_request(dict(state.get("replan", {})), change_request),
            interaction=_pending_interaction(
                state,
                active_intent="update_fixed_schedule",
                pending_action="select_fixed_schedule_item",
                current_step="awaiting_identifier",
            ),
            **schedule_patch,
        )

    result = match_fixed_schedule_blocks(blocks, operation.reference_text, target=operation.target)
    if not result.matches:
        return _not_found_update(
            state,
            schedule_patch,
            text,
            current_count,
            "update_fixed_schedule",
            operation.target,
            result.available_blocks,
        )
    change_request = _base_change_request(operation, stage="")
    if len(result.matches) > 1 and not operation.apply_to_all:
        change_request["stage"] = "awaiting_fixed_schedule_identifier"
        change_request["candidate_block_ids"] = [block.block_id for block in result.matches]
        change_request["update_text"] = operation.update_text
        return _prompt_update(
            state,
            phase="fixed_schedule_management",
            current_count=current_count,
            last_text=text,
            awaiting_user_input=True,
            prompt=(
                "Encontré varios bloques parecidos. Elige el número exacto:\n"
                f"{format_fixed_schedule_block_options(result.matches)}"
            ),
            replan=_store_change_request(dict(state.get("replan", {})), change_request),
            interaction=_pending_interaction(
                state,
                active_intent="update_fixed_schedule",
                pending_action="select_fixed_schedule_item",
                current_step="awaiting_identifier",
            ),
            **schedule_patch,
        )

    selected = result.matches[0]
    change_request["selected_block_ids"] = [selected.block_id]
    if not operation.update_text:
        change_request["stage"] = "awaiting_fixed_schedule_update_details"
        return _prompt_update(
            state,
            phase="fixed_schedule_management",
            current_count=current_count,
            last_text=text,
            awaiting_user_input=True,
            prompt=(
                "Indica el nuevo día y horario para este bloque:\n"
                f"{format_fixed_schedule_blocks([selected])}"
            ),
            replan=_store_change_request(dict(state.get("replan", {})), change_request),
            interaction=_pending_interaction(
                state,
                active_intent="update_fixed_schedule",
                pending_action="provide_fixed_schedule_update_details",
                current_step="awaiting_update_details",
            ),
            **schedule_patch,
        )
    return _queue_update_confirmation(
        state,
        blocks,
        schedule_patch,
        dict(state.get("replan", {})),
        change_request,
        selected,
        operation.update_text,
        text,
        current_count,
    )


def _start_delete_operation(
    state: AgentState,
    blocks: list[WeeklyScheduleBlock],
    schedule_patch: dict[str, object],
    operation: FixedScheduleOperation,
    text: str,
    current_count: int,
) -> dict:
    if not blocks:
        return _no_schedule_update(state, schedule_patch, text, current_count)
    if not operation.reference_text:
        change_request = _base_change_request(operation, stage="awaiting_fixed_schedule_identifier")
        change_request["candidate_block_ids"] = [block.block_id for block in _target_blocks(blocks, operation.target)]
        _delete_text = (
            "¿Qué bloque de tu horario fijo quieres eliminar?\n"
            f"{format_fixed_schedule_block_options(blocks, target=operation.target)}"
        )
        return _prompt_update(
            state,
            phase="fixed_schedule_management",
            current_count=current_count,
            last_text=text,
            awaiting_user_input=True,
            prompt=_try_render_schedule_content(
                _target_blocks(blocks, operation.target) or blocks,
                _delete_text,
                str(state.get("timezone", "America/Bogota")),
            ),
            replan=_store_change_request(dict(state.get("replan", {})), change_request),
            interaction=_pending_interaction(
                state,
                active_intent="delete_fixed_schedule_item",
                pending_action="select_fixed_schedule_item",
                current_step="awaiting_identifier",
            ),
            **schedule_patch,
        )

    result = match_fixed_schedule_blocks(blocks, operation.reference_text, target=operation.target)
    if not result.matches:
        return _not_found_update(
            state,
            schedule_patch,
            text,
            current_count,
            "delete_fixed_schedule_item",
            operation.target,
            result.available_blocks,
        )
    change_request = _base_change_request(operation, stage="")
    if len(result.matches) > 1 and not operation.apply_to_all:
        change_request["stage"] = "awaiting_fixed_schedule_identifier"
        change_request["candidate_block_ids"] = [block.block_id for block in result.matches]
        return _prompt_update(
            state,
            phase="fixed_schedule_management",
            current_count=current_count,
            last_text=text,
            awaiting_user_input=True,
            prompt=(
                "Encontré varios bloques parecidos. Elige el número exacto:\n"
                f"{format_fixed_schedule_block_options(result.matches)}"
            ),
            replan=_store_change_request(dict(state.get("replan", {})), change_request),
            interaction=_pending_interaction(
                state,
                active_intent="delete_fixed_schedule_item",
                pending_action="select_fixed_schedule_item",
                current_step="awaiting_identifier",
            ),
            **schedule_patch,
        )
    selected = result.matches if operation.apply_to_all else [result.matches[0]]
    return _queue_delete_confirmation(
        state,
        blocks,
        schedule_patch,
        dict(state.get("replan", {})),
        change_request,
        selected,
        text,
        current_count,
    )


def _start_add_operation(
    state: AgentState,
    blocks: list[WeeklyScheduleBlock],
    schedule_patch: dict[str, object],
    operation: FixedScheduleOperation,
    text: str,
    current_count: int,
) -> dict:
    add_text = operation.reference_text or text

    if operation.target:
        block_type: ScheduleBlockType = operation.target
    else:
        inferred = infer_fixed_schedule_target(add_text)
        if inferred:
            block_type = inferred
        else:
            change_request = _base_change_request(operation, stage="awaiting_fixed_schedule_block_type")
            change_request["add_text"] = add_text
            return _prompt_update(
                state,
                phase="fixed_schedule_management",
                current_count=current_count,
                last_text=text,
                awaiting_user_input=True,
                prompt=_BLOCK_TYPE_QUESTION,
                replan=_store_change_request(dict(state.get("replan", {})), change_request),
                interaction=_pending_interaction(
                    state,
                    active_intent="add_fixed_schedule_item",
                    pending_action="provide_fixed_schedule_block_type",
                    current_step="awaiting_block_type",
                ),
                **schedule_patch,
            )

    timezone = str(state.get("timezone", "America/Bogota"))
    preview = build_fixed_schedule_add_preview(add_text, block_type, timezone=timezone)
    if preview.prompt:
        change_request = _base_change_request(operation, stage="awaiting_fixed_schedule_add_details")
        change_request["add_text"] = add_text
        return _prompt_update(
            state,
            phase="fixed_schedule_management",
            current_count=current_count,
            last_text=text,
            awaiting_user_input=True,
            prompt=str(preview.prompt),
            replan=_store_change_request(dict(state.get("replan", {})), change_request),
            interaction=_pending_interaction(
                state,
                active_intent="add_fixed_schedule_item",
                pending_action="provide_fixed_schedule_add_details",
                current_step="awaiting_add_details",
            ),
            **schedule_patch,
        )

    return _queue_add_confirmation(
        state,
        blocks,
        schedule_patch,
        dict(state.get("replan", {})),
        _base_change_request(operation, stage=""),
        preview.replacement_blocks,
        text,
        current_count,
    )


def _handle_add_details_turn(
    state: AgentState,
    blocks: list[WeeklyScheduleBlock],
    schedule_patch: dict[str, object],
    replan: dict,
    change_request: dict,
    text: str,
    current_count: int,
) -> dict:
    block_type_raw = str(change_request.get("target") or "").strip()
    if not block_type_raw:
        inferred = infer_fixed_schedule_target(text)
        if inferred:
            block_type_raw = inferred
        else:
            change_request["add_text"] = text
            change_request["stage"] = "awaiting_fixed_schedule_block_type"
            return _prompt_update(
                state,
                phase="fixed_schedule_management",
                current_count=current_count,
                last_text=text,
                awaiting_user_input=True,
                prompt=_BLOCK_TYPE_QUESTION,
                replan=_store_change_request(replan, change_request),
                interaction=_pending_interaction(
                    state,
                    active_intent="add_fixed_schedule_item",
                    pending_action="provide_fixed_schedule_block_type",
                    current_step="awaiting_block_type",
                ),
                **schedule_patch,
            )
    block_type = block_type_raw
    timezone = str(state.get("timezone", "America/Bogota"))

    preview = build_fixed_schedule_add_preview(text, block_type, timezone=timezone)  # type: ignore[arg-type]
    if preview.prompt:
        return _prompt_update(
            state,
            phase="fixed_schedule_management",
            current_count=current_count,
            last_text=text,
            awaiting_user_input=True,
            prompt=str(preview.prompt),
            replan=_store_change_request(replan, change_request),
            interaction=_pending_interaction(
                state,
                active_intent="add_fixed_schedule_item",
                pending_action="provide_fixed_schedule_add_details",
                current_step="awaiting_add_details",
            ),
            **schedule_patch,
        )

    return _queue_add_confirmation(
        state,
        blocks,
        schedule_patch,
        replan,
        change_request,
        preview.replacement_blocks,
        text,
        current_count,
    )


def _queue_add_confirmation(
    state: AgentState,
    blocks: list[WeeklyScheduleBlock],
    schedule_patch: dict[str, object],
    replan: dict,
    change_request: dict,
    new_blocks: list[WeeklyScheduleBlock],
    last_text: str,
    current_count: int,
) -> dict:
    payload = {
        "intent": "add_fixed_schedule_item",
        "operation": "add",
        "new_blocks": [_dump_block(block) for block in new_blocks],
        "requires_persistence": True,
        "requires_outlook_sync": True,
    }
    prompt_text = (
        "Voy a agregar este bloque a tu horario fijo:\n\n"
        f"{format_fixed_schedule_blocks(new_blocks)}\n\n"
        "¿Confirmas el cambio?"
    )
    prompt = _try_render_schedule_content(
        blocks + new_blocks,
        prompt_text,
        str(state.get("timezone", "America/Bogota")),
    )
    change_request.update(
        {
            "stage": _CONFIRMATION_STAGE,
            "operation": "add",
            "new_blocks": [_dump_block(block) for block in new_blocks],
            "confirmation_payload": payload,
        }
    )
    replan = _store_change_request(replan, change_request)
    replan["pending_prompt"] = prompt_text
    return _prompt_update(
        state,
        phase="fixed_schedule_management",
        current_count=current_count,
        last_text=last_text,
        awaiting_user_input=True,
        prompt=prompt,
        replan=replan,
        interaction=_confirmation_interaction(state, payload),
        **schedule_patch,
    )


def _handle_block_type_turn(
    state: AgentState,
    blocks: list[WeeklyScheduleBlock],
    schedule_patch: dict[str, object],
    replan: dict,
    change_request: dict,
    text: str,
    current_count: int,
) -> dict:
    """Procesa la respuesta del usuario sobre el tipo de bloque y avanza al preview."""
    block_type = _parse_block_type_answer(text)
    if block_type is None:
        return _prompt_update(
            state,
            phase="fixed_schedule_management",
            current_count=current_count,
            last_text=text,
            awaiting_user_input=True,
            prompt=(
                "No reconocí el tipo. Elige:\n"
                "1. Académico (clase, materia)\n"
                "2. Laboral (trabajo)\n"
                "3. Extracurricular (deporte, actividad personal)"
            ),
            replan=_store_change_request(replan, change_request),
            interaction=_pending_interaction(
                state,
                active_intent="add_fixed_schedule_item",
                pending_action="provide_fixed_schedule_block_type",
                current_step="awaiting_block_type",
            ),
            **schedule_patch,
        )

    add_text = str(change_request.get("add_text") or "").strip()
    timezone = str(state.get("timezone", "America/Bogota"))
    change_request["target"] = block_type

    if not add_text:
        change_request["stage"] = "awaiting_fixed_schedule_add_details"
        return _prompt_update(
            state,
            phase="fixed_schedule_management",
            current_count=current_count,
            last_text=text,
            awaiting_user_input=True,
            prompt="Indica el nombre, día y horario del nuevo bloque.",
            replan=_store_change_request(replan, change_request),
            interaction=_pending_interaction(
                state,
                active_intent="add_fixed_schedule_item",
                pending_action="provide_fixed_schedule_add_details",
                current_step="awaiting_add_details",
            ),
            **schedule_patch,
        )

    preview = build_fixed_schedule_add_preview(add_text, block_type, timezone=timezone)
    if preview.prompt:
        change_request["stage"] = "awaiting_fixed_schedule_add_details"
        return _prompt_update(
            state,
            phase="fixed_schedule_management",
            current_count=current_count,
            last_text=text,
            awaiting_user_input=True,
            prompt=str(preview.prompt),
            replan=_store_change_request(replan, change_request),
            interaction=_pending_interaction(
                state,
                active_intent="add_fixed_schedule_item",
                pending_action="provide_fixed_schedule_add_details",
                current_step="awaiting_add_details",
            ),
            **schedule_patch,
        )

    change_request["stage"] = ""
    return _queue_add_confirmation(
        state,
        blocks,
        schedule_patch,
        replan,
        change_request,
        preview.replacement_blocks,
        add_text,
        current_count,
    )


def _parse_block_type_answer(text: str) -> "ScheduleBlockType | None":
    """Parsea la respuesta del usuario sobre el tipo de bloque a agregar."""
    clean = str(text or "").strip()
    inferred = infer_fixed_schedule_target(clean)
    if inferred:
        return inferred
    normalized = clean.strip(" .)").rstrip(".")
    if normalized in ("1", "1)", "1."):
        return "academic"
    if normalized in ("2", "2)", "2."):
        return "work"
    if normalized in ("3", "3)", "3."):
        return "extracurricular"
    return None


def _queue_update_confirmation(
    state: AgentState,
    blocks: list[WeeklyScheduleBlock],
    schedule_patch: dict[str, object],
    replan: dict,
    change_request: dict,
    selected: WeeklyScheduleBlock,
    update_text: str,
    last_text: str,
    current_count: int,
) -> dict:
    preview = build_fixed_schedule_update_preview(
        selected,
        update_text,
        timezone=state.get("timezone", "America/Bogota"),
    )
    if preview.prompt:
        change_request["stage"] = "awaiting_fixed_schedule_update_details"
        return _prompt_update(
            state,
            phase="fixed_schedule_management",
            current_count=current_count,
            last_text=last_text,
            awaiting_user_input=True,
            prompt=str(preview.prompt),
            replan=_store_change_request(replan, change_request),
            interaction=_pending_interaction(
                state,
                active_intent="update_fixed_schedule",
                pending_action="provide_fixed_schedule_update_details",
                current_step="awaiting_update_details",
            ),
            **schedule_patch,
        )

    payload = {
        "intent": "update_fixed_schedule",
        "operation": "update",
        "selected_block_ids": [selected.block_id],
        "current_blocks": [_dump_block(selected)],
        "replacement_blocks": [_dump_block(block) for block in preview.replacement_blocks],
        "requires_persistence": True,
        "requires_outlook_sync": True,
    }
    prompt_text = (
        "Voy a modificar este bloque de tu horario fijo.\n\n"
        "Actual:\n"
        f"{format_fixed_schedule_blocks([selected])}\n\n"
        "Quedará así:\n"
        f"{format_fixed_schedule_blocks(preview.replacement_blocks)}\n\n"
        "¿Confirmas el cambio?"
    )
    prompt = _try_render_schedule_content(
        blocks,
        prompt_text,
        str(state.get("timezone", "America/Bogota")),
    )
    change_request.update(
        {
            "stage": _CONFIRMATION_STAGE,
            "operation": "update",
            "selected_block_ids": [selected.block_id],
            "replacement_blocks": [_dump_block(block) for block in preview.replacement_blocks],
            "confirmation_payload": payload,
        }
    )
    replan = _store_change_request(replan, change_request)
    replan["pending_prompt"] = prompt_text
    return _prompt_update(
        state,
        phase="fixed_schedule_management",
        current_count=current_count,
        last_text=last_text,
        awaiting_user_input=True,
        prompt=prompt,
        replan=replan,
        interaction=_confirmation_interaction(state, payload),
        **schedule_patch,
    )


def _queue_delete_confirmation(
    state: AgentState,
    blocks: list[WeeklyScheduleBlock],
    schedule_patch: dict[str, object],
    replan: dict,
    change_request: dict,
    selected: list[WeeklyScheduleBlock],
    last_text: str,
    current_count: int,
) -> dict:
    selected_ids = [block.block_id for block in selected]
    payload = {
        "intent": "delete_fixed_schedule_item",
        "operation": "delete",
        "selected_block_ids": selected_ids,
        "current_blocks": [_dump_block(block) for block in selected],
        "requires_persistence": True,
        "requires_outlook_sync": True,
    }
    prompt_text = (
        "¿Estás seguro de que deseas eliminar este bloque de tu horario fijo?\n\n"
        f"{format_fixed_schedule_blocks(selected)}"
    )
    prompt = _try_render_schedule_content(
        blocks,
        prompt_text,
        str(state.get("timezone", "America/Bogota")),
    )
    change_request.update(
        {
            "stage": _CONFIRMATION_STAGE,
            "operation": "delete",
            "selected_block_ids": selected_ids,
            "replacement_blocks": [],
            "confirmation_payload": payload,
        }
    )
    replan = _store_change_request(replan, change_request)
    replan["pending_prompt"] = prompt_text
    return _prompt_update(
        state,
        phase="fixed_schedule_management",
        current_count=current_count,
        last_text=last_text,
        awaiting_user_input=True,
        prompt=prompt,
        replan=replan,
        interaction=_confirmation_interaction(state, payload),
        **schedule_patch,
    )


def _persist_confirmed_schedule_change(
    state: AgentState,
    updated_blocks: list[WeeklyScheduleBlock],
    replan: dict,
    last_text: str,
    current_count: int,
    *,
    success_label: str,
) -> dict:
    schedule_state = ensure_schedule_flow_state(state.get("schedule", {}))
    updated_blocks = [
        ensure_weekly_block(block).model_copy(update={"user_confirmed": True})
        for block in updated_blocks
    ]
    updated_blocks, conflicts = detect_schedule_conflicts(updated_blocks)
    summary_text = build_schedule_summary(updated_blocks)
    schedule_end_date = _parse_iso_date(schedule_state.schedule_end_date)
    profile = dict(state.get("student_profile", {}))

    persist_result = get_schedule_service().persist_schedule(
        student_id=profile.get("persisted_student_id"),
        occupation=str(profile.get("occupation") or ""),
        timezone=state.get("timezone", "America/Bogota"),
        summary_text=summary_text,
        blocks=updated_blocks,
        conflicts=conflicts,
        conflicts_accepted=bool(schedule_state.conflicts_accepted),
        schedule_end_date=schedule_end_date,
    )
    if not persist_result.persisted:
        return _prompt_update(
            state,
            phase="end",
            current_count=current_count,
            last_text=last_text,
            awaiting_user_input=False,
            prompt=(
                "No pude guardar el cambio del horario fijo, así que no lo apliqué.\n"
                f"Detalle técnico: {persist_result.detail or persist_result.error_code or 'desconocido'}"
            ),
            replan=_clear_change_request(replan),
            interaction=_clear_interaction(state),
        )

    schedule_payload = update_schedule_flow_state(
        schedule_state,
        blocks=updated_blocks,
        conflicts=conflicts,
        summary_text=summary_text,
        review_stage="idle",
        persisted_profile_id=persist_result.schedule_profile_id,
        persistence_error=None,
        schedule_end_date=(
            persist_result.schedule_end_date.isoformat()
            if persist_result.schedule_end_date is not None
            else schedule_state.schedule_end_date
        ),
    )
    scheduling_changes = _schedule_side_effects(state, updated_blocks)
    sync_result = get_outlook_fixed_schedule_sync_service().sync_schedule_profile(
        student_id=profile.get("persisted_student_id"),
        schedule_profile_id=persist_result.schedule_profile_id,
        calendar_state=state.get("calendar", {}),
        calendar_id=dict(state.get("calendar", {})).get("calendar_id"),
    )
    calendar_update: dict[str, object] = {}
    sync_message = ""
    if getattr(sync_result, "synced", False):
        calendar_update = {
            "provider": "outlook",
            "authorized": True,
            "synced_event_map": dict(getattr(sync_result, "synced_event_map", {})),
        }
        sync_message = " Outlook quedó reconciliado."
    else:
        calendar_state = dict(state.get("calendar", {}))
        calendar_update = {
            "provider": calendar_state.get("provider") or "outlook",
            "synced_event_map": dict(getattr(sync_result, "synced_event_map", {})),
        }
        detail = getattr(sync_result, "detail", None) or getattr(sync_result, "error_code", None) or "desconocido"
        sync_message = f" No pude reconciliar Outlook automáticamente: {detail}."

    success_text = f"Listo, dejé tu horario fijo {success_label}.{sync_message}"
    timezone = str(state.get("timezone", "America/Bogota"))
    active_blocks = [b for b in updated_blocks if getattr(b, "is_active", True)]
    prompt = _try_render_schedule_content(active_blocks, success_text, timezone)
    return _prompt_update(
        state,
        phase="end",
        current_count=current_count,
        last_text=last_text,
        awaiting_user_input=False,
        prompt=prompt,
        replan=_fixed_schedule_replan_candidate(
            state,
            _clear_change_request(replan),
            persist_result.schedule_profile_id,
            success_label=success_label,
        ),
        interaction=_clear_interaction(state),
        schedule=schedule_payload,
        calendar={**dict(state.get("calendar", {})), **calendar_update},
        **scheduling_changes,
    )


def _current_fixed_schedule_blocks(state: AgentState) -> tuple[list[WeeklyScheduleBlock], dict[str, object]]:
    schedule_state = ensure_schedule_flow_state(state.get("schedule", {}))
    if schedule_state.blocks:
        return [ensure_weekly_block(block) for block in schedule_state.blocks], {}

    profile = dict(state.get("student_profile", {}))
    student_id = profile.get("persisted_student_id")
    if not student_id:
        return [], {}
    try:
        result = get_schedule_service().list_current_schedule_blocks(student_id=student_id)
    except Exception:
        return [], {}
    if not result.found or not result.blocks:
        return [], {}

    blocks = [_block_from_persisted(record) for record in result.blocks or []]
    patch = {
        "schedule": update_schedule_flow_state(
            schedule_state,
            blocks=blocks,
            persisted_profile_id=getattr(result.profile, "id", None),
            schedule_end_date=(
                result.profile.schedule_end_date.isoformat()
                if result.profile and result.profile.schedule_end_date
                else schedule_state.schedule_end_date
            ),
        )
    }
    return blocks, patch


def _schedule_side_effects(state: AgentState, blocks: list[WeeklyScheduleBlock]) -> dict[str, object]:
    raw_inputs = sync_schedule_blocks_to_raw_inputs(
        state.get("raw_inputs", {}),
        "academic",
        current_section_blocks(blocks, "academic"),
    )
    raw_inputs = sync_schedule_blocks_to_raw_inputs(
        raw_inputs,
        "work",
        current_section_blocks(blocks, "work"),
    )
    extracurricular_blocks = current_section_blocks(blocks, "extracurricular")
    extracurricular = build_extracurricular_items_from_blocks(extracurricular_blocks)
    return {
        "raw_inputs": raw_inputs.model_dump(mode="python"),
        "extracurricular": extracurricular,
    }


def _prompt_update(
    state: AgentState,
    *,
    phase: str,
    current_count: int,
    last_text: str | None,
    awaiting_user_input: bool,
    prompt: str | list | None,
    replan: dict | None = None,
    interaction: dict[str, object] | None = None,
    **state_changes: object,
) -> dict:
    conversation_changes: dict[str, object] = {
        "phase": phase,
        "user_message_count": current_count,
        "last_user_text": last_text,
        "awaiting_user_input": awaiting_user_input,
    }
    if prompt:
        conversation_changes["messages"] = append_message(state.get("messages", []), "assistant", prompt)

    update: dict[str, object] = {}
    scheduling_changes = {
        key: value
        for key, value in state_changes.items()
        if key in AgentState.field_groups()["scheduling"]
    }
    if scheduling_changes:
        update.update(update_scheduling_state(state, **scheduling_changes))
    if "calendar" in state_changes:
        update["calendar"] = state_changes["calendar"]
    update.update(update_conversation_state(state, **conversation_changes))
    if replan is not None:
        update["replan"] = replan
    if interaction is not None:
        update.update(update_interaction_state(state, **interaction))
    return update


def _not_found_update(
    state: AgentState,
    schedule_patch: dict[str, object],
    text: str,
    current_count: int,
    intent: str,
    target: ScheduleBlockType | None,
    available_blocks: list[WeeklyScheduleBlock],
) -> dict:
    prompt = (
        "No encontré un bloque claro con esa referencia. Estos son los bloques disponibles:\n"
        f"{format_fixed_schedule_block_options(available_blocks, target=target)}"
    )
    return _prompt_update(
        state,
        phase="end",
        current_count=current_count,
        last_text=text,
        awaiting_user_input=False,
        prompt=prompt,
        replan=_clear_change_request(dict(state.get("replan", {}))),
        interaction={
            "active_intent": intent,
            "current_domain": "schedule_management",
            "clarification_needed": True,
        },
        **schedule_patch,
    )


def _no_schedule_update(
    state: AgentState,
    schedule_patch: dict[str, object],
    text: str,
    current_count: int,
) -> dict:
    return _prompt_update(
        state,
        phase="end",
        current_count=current_count,
        last_text=text,
        awaiting_user_input=False,
        prompt="No encontré un horario fijo registrado para modificar.",
        replan=_clear_change_request(dict(state.get("replan", {}))),
        interaction={
            "active_intent": "manage_fixed_schedule",
            "current_domain": "schedule_management",
            "clarification_needed": True,
        },
        **schedule_patch,
    )


def _base_change_request(operation: FixedScheduleOperation, *, stage: str) -> dict[str, object]:
    _OP_MAP = {
        "delete_fixed_schedule_item": "delete",
        "add_fixed_schedule_item": "add",
    }
    return {
        "domain": _FLOW_DOMAIN,
        "intent": operation.intent,
        "operation": _OP_MAP.get(str(operation.intent), "update"),
        "target": operation.target,
        "reference_text": operation.reference_text,
        "update_text": operation.update_text,
        "apply_to_all": operation.apply_to_all,
        "stage": stage,
    }


def _current_change_request(replan: dict) -> dict:
    change_request = dict(replan.get("change_request") or {})
    if change_request.get("domain") != _FLOW_DOMAIN:
        return {}
    return change_request


def _store_change_request(replan: dict, change_request: dict) -> dict:
    updated = dict(replan)
    updated["change_request"] = dict(change_request)
    updated["pending_prompt"] = updated.get("pending_prompt")
    return updated


def _clear_change_request(replan: dict) -> dict:
    updated = dict(replan)
    updated["change_request"] = None
    updated["pending_prompt"] = None
    return updated


def _fixed_schedule_replan_candidate(
    state: AgentState,
    replan: dict,
    schedule_profile_id: int | None,
    *,
    success_label: str,
) -> dict:
    study_plan = state.get("study_plan", {})
    plan_events = (
        list(study_plan.plan_events)
        if hasattr(study_plan, "plan_events")
        else list(dict(study_plan or {}).get("plan_events") or [])
    )
    if not plan_events:
        return replan
    updated = dict(replan)
    updated["status"] = "pending"
    updated["trigger"] = "fixed_schedule_change"
    updated["change_request"] = {
        "trigger": "fixed_schedule_change",
        "source": _FLOW_DOMAIN,
        "operation": "schedule_change",
        "schedule_profile_id": schedule_profile_id,
        "reason": f"Horario fijo {success_label}",
    }
    updated["pending_prompt"] = None
    return updated


def _confirmation_interaction(state: AgentState, payload: dict[str, object]) -> dict[str, object]:
    del state
    return {
        "active_intent": str(payload.get("intent") or "manage_fixed_schedule"),
        "current_domain": "schedule_management",
        "interaction_mode": "confirmation",
        "pending_action": f"confirm_{payload.get('operation') or 'fixed_schedule_change'}",
        "pending_entity_type": "fixed_schedule_item",
        "pending_entity_payload": payload,
        "missing_fields_json": [],
        "confirmation_pending": True,
        "last_confirmation_payload": payload,
        "clarification_needed": False,
        "current_step": "awaiting_confirmation",
        "current_section": "fixed_schedule",
    }


def _pending_interaction(
    state: AgentState,
    *,
    active_intent: str,
    pending_action: str,
    current_step: str,
) -> dict[str, object]:
    del state
    return {
        "active_intent": active_intent,
        "current_domain": "schedule_management",
        "interaction_mode": "guided",
        "pending_action": pending_action,
        "pending_entity_type": "fixed_schedule_item",
        "confirmation_pending": False,
        "last_confirmation_payload": None,
        "clarification_needed": True,
        "current_step": current_step,
        "current_section": "fixed_schedule",
    }


def _clear_interaction(state: AgentState) -> dict[str, object]:
    del state
    return {
        "active_intent": None,
        "current_domain": "schedule_management",
        "interaction_mode": "guided",
        "pending_action": None,
        "pending_entity_type": None,
        "pending_entity_payload": {},
        "missing_fields_json": [],
        "confirmation_pending": False,
        "last_confirmation_payload": None,
        "clarification_needed": False,
        "current_step": None,
        "current_section": None,
    }


def _selected_block(blocks: list[WeeklyScheduleBlock], change_request: dict) -> WeeklyScheduleBlock | None:
    selected_ids = [str(item) for item in change_request.get("selected_block_ids") or []]
    if not selected_ids:
        return None
    for block in blocks:
        if block.block_id == selected_ids[0]:
            return block
    return None


def _target_blocks(
    blocks: list[WeeklyScheduleBlock],
    target: ScheduleBlockType | None,
) -> list[WeeklyScheduleBlock]:
    if target is None:
        return list(blocks)
    return [block for block in blocks if block.block_type == target]


def _dump_block(block: WeeklyScheduleBlock | dict) -> dict[str, object]:
    return ensure_weekly_block(block).model_dump(mode="python")


def _block_from_persisted(record: object) -> WeeklyScheduleBlock:
    return WeeklyScheduleBlock(
        block_id=str(getattr(record, "source_block_id")),
        block_type=str(getattr(record, "block_type")),
        title=str(getattr(record, "title")),
        day_of_week=str(getattr(record, "day_of_week")),
        start_time=str(getattr(record, "start_time")),
        end_time=str(getattr(record, "end_time")),
        frequency=str(getattr(record, "frequency", "weekly")),
        timezone=str(getattr(record, "timezone", "America/Bogota")),
        source_text=str(getattr(record, "source_text", "")),
        is_active=bool(getattr(record, "is_active", True)),
        user_confirmed=bool(getattr(record, "confirmed_by_user", True)),
        has_conflict=bool(getattr(record, "has_conflict", False)),
        conflict_accepted=bool(getattr(record, "conflict_accepted", False)),
        metadata={"persisted_block_id": getattr(record, "id", None)},
    )


def _parse_iso_date(value: object) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


__all__ = ["handle_fixed_schedule_management_turn"]
