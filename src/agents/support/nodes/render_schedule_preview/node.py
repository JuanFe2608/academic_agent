"""Nodo para generar el resumen conversacional e imagen del horario."""

from __future__ import annotations

from agents.support.nodes.utils import append_message
from agents.support.scheduling import (
    build_conflict_message,
)
from agents.support.scheduling.render import build_rendered_schedule_message_content
from agents.support.scheduling.state_helpers import (
    ensure_schedule_flow_state,
    update_schedule_flow_state,
)
from agents.support.state import AgentState

from .prompt import PROMPT


def render_schedule_preview(state: AgentState) -> dict:
    """Genera un resumen liviano y una imagen a partir de bloques semanales."""

    schedule_state = ensure_schedule_flow_state(state.get("schedule", {}))
    blocks = list(schedule_state.blocks)
    conflicts = list(schedule_state.conflicts)
    timezone_name = state.get("timezone", "America/Bogota")
    summary_text = str(
        schedule_state.summary_text
        or state.get("schedule_preview", {}).get("text")
        or ""
    ).strip()

    conflict_text = build_conflict_message(conflicts)
    review_stage = (
        "awaiting_conflict_decision"
        if conflict_text and not schedule_state.conflicts_accepted
        else "awaiting_confirmation"
    )
    question = (
        conflict_text
        if conflict_text and not schedule_state.conflicts_accepted
        else (
            "✅ ¿Entendí bien tu horario?\n"
            "(Escribe el número de la opción que quieres elegir)\n"
            "1. Sí, está correcto\n"
            "2. No, quiero corregir algo"
        )
    )
    text = f"{PROMPT}\n{summary_text}\n\n{question}".strip()
    message_content, image_path = build_rendered_schedule_message_content(
        text,
        blocks,
        timezone_name=timezone_name,
    )

    replan = dict(state.get("replan", {}))
    replan["return_to_menu"] = None

    return {
        "schedule_preview": {"text": summary_text, "image_path": image_path},
        "schedule": update_schedule_flow_state(
            schedule_state,
            review_stage=review_stage,
        ),
        "replan": replan,
        "messages": append_message(
            state.get("messages", []),
            "assistant",
            message_content,
        ),
    }
