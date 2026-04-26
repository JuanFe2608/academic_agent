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
    """Genera un resumen liviano y una imagen a partir de bloques semanales.

    Solo emite la imagen del horario con el resumen. La pregunta de confirmación
    la emite validate_schedule en el turno siguiente, separando ambos mensajes.
    """

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

    header = f"{PROMPT}\n{summary_text}".strip()
    message_content, image_path = build_rendered_schedule_message_content(
        header,
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
