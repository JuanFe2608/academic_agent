"""Nodo para generar el resumen conversacional e imagen del horario."""

from __future__ import annotations

import base64

from agents.support.nodes.utils import append_message
from agents.support.scheduling import (
    build_conflict_message,
    render_recurring_schedule,
)
from agents.support.state import AgentState

from .prompt import PROMPT


def render_schedule_preview(state: AgentState) -> dict:
    """Genera un resumen liviano y una imagen a partir de bloques semanales."""

    schedule_state = dict(state.get("schedule", {}))
    blocks = list(schedule_state.get("blocks", []))
    conflicts = list(schedule_state.get("conflicts", []))
    timezone_name = state.get("timezone", "America/Bogota")
    summary_text = str(schedule_state.get("summary_text") or state.get("schedule_preview", {}).get("text") or "").strip()
    image_path = render_recurring_schedule(blocks, timezone_name=timezone_name)
    image_data_url = _encode_image(image_path)

    conflict_text = build_conflict_message(conflicts)
    question = (
        conflict_text
        if conflict_text and not schedule_state.get("conflicts_accepted")
        else "✅ ¿Entendí bien tu horario?\nResponde: sí, está correcto o no, quiero corregirlo."
    )
    text = f"{PROMPT}\n{summary_text}\n\n{question}".strip()

    replan = dict(state.get("replan", {}))
    replan["return_to_menu"] = None

    return {
        "schedule_preview": {"text": summary_text, "image_path": image_path},
        "schedule": {
            **schedule_state,
            "review_stage": (
                "awaiting_conflict_decision"
                if conflict_text and not schedule_state.get("conflicts_accepted")
                else "awaiting_confirmation"
            ),
        },
        "replan": replan,
        "messages": append_message(
            state.get("messages", []),
            "assistant",
            [
                {"type": "text", "text": text},
                {"type": "image_url", "image_url": {"url": image_data_url}},
            ],
        ),
    }


def _encode_image(path: str) -> str:
    with open(path, "rb") as file:
        data = base64.b64encode(file.read()).decode("ascii")
    return f"data:image/png;base64,{data}"
