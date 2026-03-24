"""Nodo para validar, aceptar cruces y corregir secciones del horario."""

from __future__ import annotations

from agents.support.nodes.utils import (
    append_message,
    detect_new_input,
    normalize_text,
    parse_yes_no,
)
from agents.support.scheduling import build_section_summary
from agents.support.scheduling.models import ensure_schedule_conflict, ensure_weekly_block
from agents.support.state import AgentState


def validate_schedule(state: AgentState) -> dict:
    """Gestiona la revisión final del horario semanal."""

    messages = state.get("messages", [])
    has_new_input, last_text, current_count = detect_new_input(
        messages,
        state.get("user_message_count", 0),
        state.get("awaiting_user_input", False),
        state.get("last_user_text"),
    )
    schedule_state = dict(state.get("schedule", {}))
    stage = str(schedule_state.get("review_stage") or "awaiting_confirmation")
    conflicts = list(schedule_state.get("conflicts", []))
    correction_target = schedule_state.get("correction_target")

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
                for block in schedule_state.get("blocks", [])
            ]
            updated_conflicts = [
                ensure_schedule_conflict(conflict).model_copy(update={"accepted": True})
                for conflict in conflicts
            ]
            return {
                "schedule": {
                    **schedule_state,
                    "blocks": updated_blocks,
                    "conflicts": updated_conflicts,
                    "conflicts_accepted": True,
                    "review_stage": "awaiting_confirmation",
                },
                "phase": "validate",
                "user_message_count": current_count,
                "last_user_text": last_text,
                "awaiting_user_input": True,
                "messages": append_message(
                    messages,
                    "assistant",
                    "Entendido. Dejaré esos cruces como aceptados conscientemente.\n"
                    "✅ ¿El horario completo quedó correcto? Responde sí o no.",
                ),
            }
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
            "Si deseas mantener los cruces, responde: dejarlo así. "
            "Si prefieres cambiarlos, responde: corregir.",
        )

    if stage == "awaiting_correction_target":
        target = _parse_correction_target(last_text, state) if has_new_input else None
        if target:
            return {
                "schedule": {
                    **schedule_state,
                    "review_stage": "awaiting_correction_payload",
                    "correction_target": target,
                },
                "phase": "validate",
                "user_message_count": current_count,
                "last_user_text": last_text,
                "awaiting_user_input": True,
                "messages": append_message(
                    messages,
                    "assistant",
                    _build_payload_prompt(target, schedule_state),
                ),
            }
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
        return {
            "schedule": {
                **schedule_state,
                "pending_correction_text": str(last_text).strip(),
            },
            "phase": "schedule_edit",
            "user_message_count": current_count,
            "last_user_text": last_text,
            "awaiting_user_input": False,
            "messages": append_message(
                messages,
                "assistant",
                "Perfecto. Voy a recalcular esa parte del horario.",
            ),
        }

    answer = _parse_confirmation_answer(last_text) if has_new_input else None
    if answer is True:
        updated_blocks = [
            ensure_weekly_block(block).model_copy(update={"user_confirmed": True})
            for block in schedule_state.get("blocks", [])
        ]
        return {
            "schedule": {
                **schedule_state,
                "blocks": updated_blocks,
                "review_stage": "idle",
            },
            "events_validated": True,
            "phase": "schedule_persist",
            "user_message_count": current_count,
            "last_user_text": last_text,
            "awaiting_user_input": False,
            "messages": append_message(
                messages,
                "assistant",
                "Perfecto. Voy a guardar tu horario semanal.",
            ),
        }
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
        "✅ ¿El horario está correcto? Responde sí o no.",
    )


def _prompt_correction_target(
    state: AgentState,
    current_count: int,
    last_text: str | None,
    schedule_state: dict,
    messages: list,
) -> dict:
    return {
        "schedule": {
            **schedule_state,
            "review_stage": "awaiting_correction_target",
            "correction_target": None,
            "pending_correction_text": None,
        },
        "phase": "validate",
        "user_message_count": current_count,
        "last_user_text": last_text,
        "awaiting_user_input": True,
        "messages": append_message(
            messages,
            "assistant",
            _build_correction_menu(state),
        ),
    }


def _prompt_again(
    state: AgentState,
    current_count: int,
    last_text: str | None,
    schedule_state: dict,
    prompt: str,
) -> dict:
    return {
        "schedule": schedule_state,
        "phase": "validate",
        "user_message_count": current_count if current_count else state.get("user_message_count", 0),
        "last_user_text": last_text if current_count else state.get("last_user_text"),
        "awaiting_user_input": True,
        "messages": append_message(state.get("messages", []), "assistant", prompt),
    }


def _parse_conflict_decision(text: str | None) -> str | None:
    normalized = normalize_text(text or "")
    if not normalized:
        return None
    if any(token in normalized for token in ("dejarlo asi", "dejarlo así", "asi esta bien", "está bien", "si")):
        return "accept"
    if any(token in normalized for token in ("corregir", "cambiar", "prefiero corregir", "no")):
        return "correct"
    return None


def _parse_confirmation_answer(text: str | None) -> bool | None:
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


def _build_payload_prompt(target: str, schedule_state: dict) -> str:
    current_section = build_section_summary(list(schedule_state.get("blocks", [])), target)  # type: ignore[arg-type]
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
