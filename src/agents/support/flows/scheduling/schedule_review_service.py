"""Servicios de aplicación para revisión y corrección del horario.

Centraliza la lógica que antes vivía directamente en los nodos de validación y
corrección, manteniendo intacto el contrato del estado y el comportamiento
observable por el usuario.
"""

from __future__ import annotations

from agents.support.nodes.utils import (
    append_message,
    normalize_text,
    parse_numbered_option,
    parse_yes_no,
)
from agents.support.runtime_state_helpers import update_conversation_state
from agents.support.scheduling import (
    build_conflict_message,
    build_section_summary,
    normalize_schedule_section,
    replace_section_blocks,
)
from services.scheduling.extracurricular_state import (
    build_extracurricular_items_source_text,
    coerce_extracurricular_pending_items,
    merge_extracurricular_items,
)
from services.scheduling.pending_extracurricular_support import (
    build_extracurricular_reply_hint,
)
from agents.support.scheduling.pipeline import (
    parse_extracurricular_section,
    parse_fixed_schedule_section,
)
from agents.support.scheduling.state_helpers import (
    ensure_schedule_flow_state,
    reset_schedule_review_state,
    update_scheduling_state,
    update_schedule_flow_state,
)
from agents.support.state import AgentState
from services.scheduling.contextual_schedule_parsing import complete_pending_schedule_item
from services.scheduling.models import ensure_schedule_conflict, ensure_weekly_block
from services.scheduling.correction_sync import (
    merge_completed_fixed_section,
    replace_fixed_section,
    sync_fixed_section_result,
)
from services.scheduling.extracurricular_parsing import (
    complete_pending_extracurricular_item,
    parse_extracurricular_items,
)
from services.scheduling.pending_schedule_support import build_schedule_pending_prompt
from services.scheduling import format_schedule_end_date, parse_schedule_end_date

from .schedule_pending_resolution_service import coerce_schedule_pending_items
from .section_confirmation_service import (
    SectionReviewCompletion,
    handle_section_review_turn,
    has_active_section_review,
    start_section_review,
)

_CONFIRMATION_QUESTION = (
    "✅ ¿Entendí bien tu horario?\n"
    "(Escribe el número de la opción que quieres elegir)\n"
    "1. Sí, está correcto\n"
    "2. No, quiero corregir algo"
)


def _build_schedule_review_update(
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
    return {
        **update_scheduling_state(state, **scheduling_changes),
        **update_conversation_state(state, **conversation_changes),
    }


def handle_schedule_review_turn(
    state: AgentState,
    *,
    has_new_input: bool,
    last_text: str | None,
    current_count: int,
) -> dict:
    """Gestiona un turno de revisión final del horario semanal."""

    messages = state.get("messages", [])
    schedule_state = ensure_schedule_flow_state(state.get("schedule", {}))
    stage = str(schedule_state.review_stage or "awaiting_confirmation")
    conflicts = list(schedule_state.conflicts)
    correction_target = schedule_state.correction_target

    if not has_new_input and stage in {
        "awaiting_conflict_decision",
        "awaiting_confirmation",
        "awaiting_schedule_end_date",
        "awaiting_correction_target",
        "awaiting_correction_payload",
    }:
        prompt: str | None = None
        if stage == "awaiting_conflict_decision":
            prompt = build_conflict_message(conflicts) or _CONFIRMATION_QUESTION
        elif stage == "awaiting_confirmation":
            prompt = _CONFIRMATION_QUESTION
        return _build_schedule_review_update(
            state,
            schedule=update_schedule_flow_state(schedule_state),
            phase="validate",
            current_count=state.get("user_message_count", 0),
            last_text=state.get("last_user_text"),
            awaiting_user_input=True,
            prompt=prompt,
        )

    if has_active_section_review(state) and str(correction_target or "") in {
        "academic",
        "work",
        "extracurricular",
    }:
        return handle_section_review_turn(
            state,
            has_new_input=has_new_input,
            last_text=last_text,
            current_count=current_count,
            completion=_final_review_section_completion(),
        )

    if stage == "awaiting_conflict_decision":
        decision = _parse_conflict_decision(last_text) if has_new_input else None
        if decision == "accept":
            updated_blocks = [
                ensure_weekly_block(block).model_copy(
                    update={
                        "conflict_accepted": bool(
                            ensure_weekly_block(block).has_conflict
                            or ensure_weekly_block(block).conflict_accepted
                        )
                    }
                )
                for block in schedule_state.blocks
            ]
            updated_conflicts = [
                ensure_schedule_conflict(conflict).model_copy(update={"accepted": True})
                for conflict in conflicts
            ]
            return _build_schedule_review_update(
                state,
                schedule=update_schedule_flow_state(
                    schedule_state,
                    blocks=updated_blocks,
                    conflicts=updated_conflicts,
                    conflicts_accepted=True,
                    review_stage="awaiting_confirmation",
                ),
                phase="validate",
                current_count=current_count,
                last_text=last_text,
                awaiting_user_input=True,
                prompt=(
                    "Entendido. Dejaré esos cruces como aceptados conscientemente.\n"
                    "✅ ¿El horario completo quedó correcto?\n"
                    "(Escribe el número de la opción que quieres elegir)\n"
                    "1. Sí, está correcto\n"
                    "2. No, quiero corregir algo"
                ),
            )
        if decision == "correct":
            return _prompt_correction_target(
                state,
                current_count,
                last_text,
                schedule_state,
                messages,
            )
        return _prompt_again(
            state,
            current_count,
            last_text,
            schedule_state,
            "⚠️ Elige una opción válida.\n"
            "(Escribe el número de la opción que quieres elegir)\n"
            "1. Sí, dejarlo así\n"
            "2. No, quiero corregirlo",
        )

    if stage == "awaiting_correction_target":
        target = _parse_correction_target(last_text, state) if has_new_input else None
        if target:
            return start_section_review(
                state,
                target=target,  # type: ignore[arg-type]
                phase="validate",
                current_count=current_count,
                last_text=last_text,
                initial_stage="section_awaiting_item_selection",
            )
        return _prompt_correction_target(
            state,
            current_count,
            last_text,
            schedule_state,
            messages,
        )

    if stage == "awaiting_correction_payload":
        if not has_new_input or not str(last_text or "").strip():
            return _prompt_again(
                state,
                current_count,
                last_text,
                schedule_state,
                _build_payload_prompt(str(correction_target or "academic"), schedule_state),
            )
        return _build_schedule_review_update(
            state,
            schedule=update_schedule_flow_state(
                schedule_state,
                pending_correction_text=str(last_text).strip(),
            ),
            phase="schedule_edit",
            current_count=current_count,
            last_text=last_text,
            awaiting_user_input=False,
            prompt="Perfecto. Voy a recalcular esa parte del horario.",
        )

    if stage == "awaiting_schedule_end_date":
        parsed_end_date = parse_schedule_end_date(
            last_text,
            timezone_name=state.get("timezone", "America/Bogota"),
        ) if has_new_input else None
        if parsed_end_date is None:
            return _prompt_again(
                state,
                current_count,
                last_text,
                schedule_state,
                _build_schedule_end_date_prompt(),
            )
        return _build_schedule_review_update(
            state,
            schedule=update_schedule_flow_state(
                schedule_state,
                schedule_end_date=parsed_end_date.isoformat(),
                review_stage="idle",
            ),
            phase="schedule_persist",
            current_count=current_count,
            last_text=last_text,
            awaiting_user_input=False,
            prompt=(
                "📅 Perfecto. Voy a guardar tu horario semanal "
                f"hasta el {format_schedule_end_date(parsed_end_date)}."
            ),
        )

    answer = _parse_confirmation_answer(last_text) if has_new_input else None
    if answer is True:
        updated_blocks = [
            ensure_weekly_block(block).model_copy(update={"user_confirmed": True})
            for block in schedule_state.blocks
        ]
        return _build_schedule_review_update(
            state,
            schedule=update_schedule_flow_state(
                schedule_state,
                blocks=updated_blocks,
                review_stage="awaiting_schedule_end_date",
                schedule_end_date=None,
            ),
            phase="validate",
            current_count=current_count,
            last_text=last_text,
            awaiting_user_input=True,
            prompt=_build_schedule_end_date_prompt(),
        )
    if answer is False:
        return _prompt_correction_target(
            state,
            current_count,
            last_text,
            schedule_state,
            messages,
        )

    return _prompt_again(
        state,
        current_count,
        last_text,
        schedule_state,
        "✅ ¿El horario está correcto?\n"
        "(Escribe el número de la opción que quieres elegir)\n"
        "1. Sí, está correcto\n"
        "2. No, quiero corregir algo",
    )


def apply_schedule_correction_turn(state: AgentState) -> dict:
    """Recalcula una sola sección del horario sin reiniciar el flujo."""

    schedule_state = ensure_schedule_flow_state(state.get("schedule", {}))
    target = str(schedule_state.correction_target or "").strip()
    text = str(schedule_state.pending_correction_text or "").strip()
    timezone = state.get("timezone", "America/Bogota")
    blocks = list(schedule_state.blocks)
    pending_items = coerce_extracurricular_pending_items(
        state.get("extras_pending_items", [])
    )
    academic_pending_items = coerce_schedule_pending_items(
        state.get("academic_pending_items", [])
    )
    work_pending_items = coerce_schedule_pending_items(
        state.get("work_pending_items", [])
    )

    if target == "extracurricular" and normalize_text(text) in {
        "ninguna",
        "ninguna actividad",
        "no",
        "no tengo",
    }:
        updated_blocks = replace_section_blocks(blocks, "extracurricular", [])
        return _build_schedule_review_update(
            state,
            schedule=_reset_schedule_review_state(schedule_state, updated_blocks),
            extracurricular=[],
            extras_pending_items=[],
            phase="draft",
            current_count=state.get("user_message_count", 0),
            last_text=state.get("last_user_text"),
            awaiting_user_input=False,
        )

    if target == "extracurricular" and pending_items:
        completed_item, missing = complete_pending_extracurricular_item(
            text,
            pending_items[0],
            expected_is_variable=False,
        )
        if not missing:
            merged_items = merge_extracurricular_items(
                state.get("extracurricular", []),
                [completed_item],
            )
            completion_text = build_extracurricular_items_source_text(merged_items)
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
            return _build_schedule_review_update(
                state,
                schedule=_reset_schedule_review_state(
                    schedule_state,
                    updated_schedule_blocks,
                ),
                extracurricular=merged_items,
                extras_pending_items=[],
                phase="draft",
                current_count=state.get("user_message_count", 0),
                last_text=state.get("last_user_text"),
                awaiting_user_input=False,
            )

    target_pending_items = academic_pending_items if target == "academic" else work_pending_items
    if target in {"academic", "work"} and target_pending_items:
        completed_blocks, _clarifications, updated_pending = complete_pending_schedule_item(
            text,
            target_pending_items[0],
            timezone=timezone,
        )
        if updated_pending is not None:
            refreshed_items = [updated_pending] + target_pending_items[1:]
            return _build_schedule_review_update(
                state,
                schedule=update_schedule_flow_state(
                    schedule_state,
                    review_stage="awaiting_correction_payload",
                ),
                academic_pending_items=(
                    refreshed_items if target == "academic" else academic_pending_items
                ),
                work_pending_items=(
                    refreshed_items if target == "work" else work_pending_items
                ),
                phase="validate",
                current_count=state.get("user_message_count", 0),
                last_text=state.get("last_user_text"),
                awaiting_user_input=True,
                prompt=build_schedule_pending_prompt(target, refreshed_items),
            )

        sync_result = merge_completed_fixed_section(
            blocks,
            state.get("raw_inputs", {}),
            target,  # type: ignore[arg-type]
            completed_blocks,
        )
        updated_schedule_blocks = sync_result.schedule_blocks
        raw_inputs = sync_result.raw_inputs.model_dump(mode="python")
        if target == "academic":
            academic_pending_items = target_pending_items[1:]
        else:
            work_pending_items = target_pending_items[1:]

        remaining_target_items = (
            academic_pending_items if target == "academic" else work_pending_items
        )
        if remaining_target_items:
            return _build_schedule_review_update(
                state,
                schedule=update_schedule_flow_state(
                    schedule_state,
                    blocks=updated_schedule_blocks,
                    review_stage="awaiting_correction_payload",
                    pending_correction_text=None,
                ),
                raw_inputs=raw_inputs,
                academic_pending_items=academic_pending_items,
                work_pending_items=work_pending_items,
                phase="validate",
                current_count=state.get("user_message_count", 0),
                last_text=state.get("last_user_text"),
                awaiting_user_input=True,
                prompt=build_schedule_pending_prompt(target, remaining_target_items),
            )

        return _build_schedule_review_update(
            state,
            schedule=_reset_schedule_review_state(
                schedule_state,
                updated_schedule_blocks,
            ),
            raw_inputs=raw_inputs,
            academic_pending_items=academic_pending_items,
            work_pending_items=work_pending_items,
            extras_pending_items=[],
            phase="draft",
            current_count=state.get("user_message_count", 0),
            last_text=state.get("last_user_text"),
            awaiting_user_input=False,
        )

    if target in {"academic", "work"}:
        section_result = parse_fixed_schedule_section(
            text,
            target,  # type: ignore[arg-type]
            timezone=timezone,
        )
        if section_result.pending_schedule_items:
            updated_schedule_blocks = replace_section_blocks(blocks, target, section_result.blocks)
            return _build_schedule_review_update(
                state,
                schedule=update_schedule_flow_state(
                    schedule_state,
                    blocks=updated_schedule_blocks,
                    review_stage="awaiting_correction_payload",
                ),
                academic_pending_items=(
                    section_result.pending_schedule_items
                    if target == "academic"
                    else academic_pending_items
                ),
                work_pending_items=(
                    section_result.pending_schedule_items
                    if target == "work"
                    else work_pending_items
                ),
                phase="validate",
                current_count=state.get("user_message_count", 0),
                last_text=state.get("last_user_text"),
                awaiting_user_input=True,
                prompt=build_schedule_pending_prompt(
                    target,
                    section_result.pending_schedule_items,
                    section_result.clarifications,
                ),
            )

    result = normalize_schedule_section(text, target or "academic", timezone=timezone)
    if result.needs_clarification:
        if target == "extracurricular":
            section_result = parse_extracurricular_section(
                text,
                timezone=timezone,
                expected_is_variable=False,
            )
            return _build_schedule_review_update(
                state,
                schedule=update_schedule_flow_state(
                    schedule_state,
                    review_stage="awaiting_correction_payload",
                ),
                extracurricular=section_result.extracurricular_items,
                extras_pending_items=section_result.pending_extracurricular_items,
                phase="validate",
                current_count=state.get("user_message_count", 0),
                last_text=state.get("last_user_text"),
                awaiting_user_input=True,
                prompt=_build_extracurricular_correction_prompt(
                    section_result.clarifications or result.clarifications,
                    section_result.pending_extracurricular_items,
                ),
            )
        if target in {"academic", "work"}:
            section_result = parse_fixed_schedule_section(
                text,
                target,  # type: ignore[arg-type]
                timezone=timezone,
            )
            if section_result.blocks and not section_result.pending_schedule_items:
                sync_result = sync_fixed_section_result(
                    blocks,
                    state.get("raw_inputs", {}),
                    target,
                    section_result,
                )
                return _build_schedule_review_update(
                    state,
                    schedule=_reset_schedule_review_state(
                        schedule_state,
                        sync_result.schedule_blocks,
                    ),
                    raw_inputs=sync_result.raw_inputs.model_dump(mode="python"),
                    academic_pending_items=[],
                    work_pending_items=[],
                    extras_pending_items=[],
                    phase="draft",
                    current_count=state.get("user_message_count", 0),
                    last_text=state.get("last_user_text"),
                    awaiting_user_input=False,
                )
            updated_schedule_blocks = replace_section_blocks(
                blocks,
                target,
                section_result.blocks,
            )
            return _build_schedule_review_update(
                state,
                schedule=update_schedule_flow_state(
                    schedule_state,
                    blocks=updated_schedule_blocks,
                    review_stage="awaiting_correction_payload",
                ),
                academic_pending_items=(
                    section_result.pending_schedule_items
                    if target == "academic"
                    else academic_pending_items
                ),
                work_pending_items=(
                    section_result.pending_schedule_items
                    if target == "work"
                    else work_pending_items
                ),
                phase="validate",
                current_count=state.get("user_message_count", 0),
                last_text=state.get("last_user_text"),
                awaiting_user_input=True,
                prompt=build_schedule_pending_prompt(
                    target,
                    section_result.pending_schedule_items,
                    section_result.clarifications or result.clarifications,
                ),
            )
        return _build_schedule_review_update(
            state,
            schedule=update_schedule_flow_state(
                schedule_state,
                review_stage="awaiting_correction_payload",
            ),
            academic_pending_items=academic_pending_items,
            work_pending_items=work_pending_items,
            phase="validate",
            current_count=state.get("user_message_count", 0),
            last_text=state.get("last_user_text"),
            awaiting_user_input=True,
            prompt="\n".join(result.clarifications),
        )

    updated_schedule_blocks = replace_section_blocks(
        blocks,
        target or "academic",
        result.blocks,
    )
    update: dict[str, object] = {
        **_build_schedule_review_update(
            state,
            schedule=_reset_schedule_review_state(schedule_state, updated_schedule_blocks),
            phase="draft",
            current_count=state.get("user_message_count", 0),
            last_text=state.get("last_user_text"),
            academic_pending_items=[],
            work_pending_items=[],
            extras_pending_items=[],
            awaiting_user_input=False,
        ),
    }
    if target == "academic":
        sync_result = replace_fixed_section(
            blocks,
            state.get("raw_inputs", {}),
            "academic",
            result.blocks,
        )
        update["raw_inputs"] = sync_result.raw_inputs.model_dump(mode="python")
    elif target == "work":
        sync_result = replace_fixed_section(
            blocks,
            state.get("raw_inputs", {}),
            "work",
            result.blocks,
        )
        update["raw_inputs"] = sync_result.raw_inputs.model_dump(mode="python")
    elif target == "extracurricular":
        items, _ = parse_extracurricular_items(text, expected_is_variable=False)
        update["extracurricular"] = items
    return update


def _reset_schedule_review_state(schedule_state: object, blocks: list) -> dict:
    """Limpia metadatos de revisión después de una corrección exitosa."""

    return reset_schedule_review_state(schedule_state, blocks)


def _prompt_correction_target(
    state: AgentState,
    current_count: int,
    last_text: str | None,
    schedule_state: object,
    messages: list,
) -> dict:
    return {
        **_build_schedule_review_update(
            state,
            schedule=update_schedule_flow_state(
                schedule_state,
                review_stage="awaiting_correction_target",
                correction_target=None,
                pending_correction_text=None,
            ),
            phase="validate",
            current_count=current_count,
            last_text=last_text,
            awaiting_user_input=True,
            prompt=_build_correction_menu(state),
        ),
    }


def _prompt_again(
    state: AgentState,
    current_count: int,
    last_text: str | None,
    schedule_state: object,
    prompt: str,
) -> dict:
    return {
        **_build_schedule_review_update(
            state,
            schedule=update_schedule_flow_state(schedule_state),
            phase="validate",
            current_count=current_count if current_count else state.get("user_message_count", 0),
            last_text=last_text if current_count else state.get("last_user_text"),
            awaiting_user_input=True,
            prompt=prompt,
        ),
    }


def _parse_conflict_decision(text: str | None) -> str | None:
    option = parse_numbered_option(text)
    if option == 1:
        return "accept"
    if option == 2:
        return "correct"
    normalized = normalize_text(text or "")
    if not normalized:
        return None
    if any(
        token in normalized
        for token in ("dejarlo asi", "dejarlo así", "asi esta bien", "está bien", "si")
    ):
        return "accept"
    if any(
        token in normalized
        for token in ("corregir", "cambiar", "prefiero corregir", "no")
    ):
        return "correct"
    return None


def _parse_confirmation_answer(text: str | None) -> bool | None:
    option = parse_numbered_option(text)
    if option == 1:
        return True
    if option == 2:
        return False
    normalized = normalize_text(text or "")
    if any(token in normalized for token in ("correcto", "esta correcto", "está correcto")):
        return True
    if any(token in normalized for token in ("quiero corregir", "corregir")):
        return False
    return parse_yes_no(text or "")


def _build_correction_menu(state: AgentState) -> str:
    occupation = str(state.get("student_profile", {}).get("occupation") or "").strip()
    lines = ["✏️ ¿Qué parte quieres corregir?"]
    if occupation == "solo_estudio":
        lines.append("1. Horario académico")
        lines.append("2. Actividades extracurriculares")
        return "\n".join(lines)
    lines.append("1. Horario académico")
    if occupation == "ambos":
        lines.append("2. Horario laboral")
        lines.append("3. Actividades extracurriculares")
    else:
        lines.append("2. Actividades extracurriculares")
    return "\n".join(lines)


def _parse_correction_target(text: str | None, state: AgentState) -> str | None:
    normalized = normalize_text(text or "")
    occupation = str(state.get("student_profile", {}).get("occupation") or "").strip()
    if any(token in normalized for token in ("academico", "académico", "materia", "clase")):
        return "academic"
    if any(token in normalized for token in ("laboral", "trabajo")) and occupation == "ambos":
        return "work"
    if any(token in normalized for token in ("extra", "actividad", "gimnasio", "deporte")):
        return "extracurricular"

    if normalized.startswith("1"):
        return "academic"
    if normalized.startswith("2"):
        return "work" if occupation == "ambos" else "extracurricular"
    if normalized.startswith("3") and occupation == "ambos":
        return "extracurricular"
    return None


def _build_payload_prompt(target: str, schedule_state: object) -> str:
    flow_state = ensure_schedule_flow_state(schedule_state)
    current_section = build_section_summary(
        list(flow_state.blocks),
        target,
    )  # type: ignore[arg-type]
    if target == "work":
        return (
            f"💼 {current_section}\n\n"
            "Envíame de nuevo solo tu horario laboral.\n"
            "Incluye días y horas exactas, por ejemplo: lunes a viernes de 7:00 a 18:00."
        )
    if target == "extracurricular":
        return (
            f"🏃 {current_section}\n\n"
            "Envíame de nuevo solo las actividades extracurriculares que quieres dejar activas.\n"
            "Incluye nombre, días y horas. Si no quieres ninguna, responde: ninguna."
        )
    return (
        f"📚 {current_section}\n\n"
        "Envíame de nuevo solo tu horario académico.\n"
        "Incluye materias, días y horas en un solo mensaje."
    )


def _build_extracurricular_correction_prompt(
    clarifications: list[str],
    pending_items: list,
) -> str:
    lines = [str(item).strip() for item in clarifications if str(item).strip()]
    if pending_items:
        lines.append(build_extracurricular_reply_hint(pending_items[0]))
    return "\n".join(lines)


def _build_schedule_end_date_prompt() -> str:
    return (
        "📅 Antes de guardarlo en Outlook, necesito la fecha límite de este horario fijo.\n"
        "Escríbela en uno de estos formatos:\n"
        "1. YYYY-MM-DD\n"
        "2. DD/MM/YYYY\n"
        "Ejemplo: 2026-06-30"
    )


def _final_review_section_completion() -> SectionReviewCompletion:
    return SectionReviewCompletion(
        phase="draft",
        awaiting_user_input=False,
        after_change_phase="draft",
        after_change_awaiting_user_input=False,
    )
