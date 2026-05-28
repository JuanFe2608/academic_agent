"""Nodo para persistir el horario semanal recurrente."""

from __future__ import annotations

from datetime import date

from agents.support.dependencies import get_schedule_service
from agents.support.nodes.utils import append_message
from agents.support.state import AgentState


def persist_schedule(state: AgentState) -> dict:
    """Guarda el horario confirmado y deja el flujo listo para cierre."""

    profile = dict(state.get("student_profile", {}))
    schedule_state = dict(state.get("schedule", {}))
    schedule_end_date = _parse_schedule_end_date(schedule_state.get("schedule_end_date"))

    result = get_schedule_service().persist_schedule(
        student_id=profile.get("persisted_student_id"),
        occupation=str(profile.get("occupation") or ""),
        timezone=state.get("timezone", "America/Bogota"),
        summary_text=str(schedule_state.get("summary_text") or ""),
        blocks=list(schedule_state.get("blocks", [])),
        conflicts=list(schedule_state.get("conflicts", [])),
        conflicts_accepted=bool(schedule_state.get("conflicts_accepted")),
        schedule_end_date=schedule_end_date,
    )

    if result.persisted:
        if result.invalid_blocks:
            lines = [
                "✅ Tu horario semanal quedó guardado, aunque omití algunos bloques que no pude interpretar:",
            ]
            lines.extend(f"- {desc}" for desc in result.invalid_blocks)
            lines.append("Puedes volver a indicarme esos bloques cuando quieras.")
            success_msg = "\n".join(lines)
        else:
            success_msg = "✅ Tu horario semanal quedó guardado correctamente."
        return {
            "schedule": {
                **schedule_state,
                "persisted_profile_id": result.schedule_profile_id,
                "persistence_error": None,
                "schedule_end_date": (
                    result.schedule_end_date.isoformat()
                    if result.schedule_end_date is not None
                    else schedule_state.get("schedule_end_date")
                ),
            },
            "phase": "schedule_sync",
            "awaiting_user_input": False,
            "messages": append_message(state.get("messages", []), "assistant", success_msg),
        }

    failure_msg = _build_failure_message(result)
    return {
        "schedule": {
            **schedule_state,
            "persistence_error": result.error_code,
        },
        "phase": "end",
        "awaiting_user_input": False,
        "messages": append_message(state.get("messages", []), "assistant", failure_msg),
    }


def _build_failure_message(result: object) -> str:
    error_code = getattr(result, "error_code", None)
    invalid_blocks = getattr(result, "invalid_blocks", ())
    if error_code == "no_valid_blocks":
        if invalid_blocks:
            lines = ["No pude guardar el horario porque ningún bloque tiene un formato válido:"]
            lines.extend(f"- {desc}" for desc in invalid_blocks)
            lines.append("Por favor, indícame de nuevo tu horario con el formato: día hora_inicio-hora_fin nombre.")
            return "\n".join(lines)
        return (
            "No pude guardar el horario porque no hay bloques para persistir.\n"
            "Por favor, indícame de nuevo tu horario con el formato: día hora_inicio-hora_fin nombre."
        )
    if invalid_blocks:
        lines = ["No pude guardar el horario por un problema técnico."]
        lines.append("Además, estos bloques tenían formato inválido:")
        lines.extend(f"- {desc}" for desc in invalid_blocks)
        return "\n".join(lines)
    return "No pude guardar el horario en este momento. Por favor, intenta de nuevo más tarde."


def _parse_schedule_end_date(raw_value: object) -> date | None:
    value = str(raw_value or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
