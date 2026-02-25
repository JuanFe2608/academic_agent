"""Nodo para generar la vista previa del horario."""

from __future__ import annotations

from agents.support.nodes.utils import append_message
from agents.support.state import DAY_ORDER, AgentState, Event
from agents.support.tools.schedule_renderer import render_week_schedule

from .prompt import PROMPT

import base64


def render_schedule_preview(state: AgentState) -> dict:
    """Genera el texto e imagen de la vista previa."""
    events: list[Event] = list(state.get("events", []))
    preview_text = _build_text_preview(events)
    image_path = render_week_schedule(events)
    image_data_url = _encode_image(image_path)

    return {
        "schedule_preview": {"text": preview_text, "image_path": image_path},
        "messages": append_message(
            state.get("messages", []),
            "assistant",
            [
                {"type": "text", "text": f"{PROMPT}\n{preview_text}"},
                {"type": "image_url", "image_url": {"url": image_data_url}},
            ],
        ),
    }


def _build_text_preview(events: list[Event]) -> str:
    lines: list[str] = []
    for day in DAY_ORDER:
        day_events = [event for event in events if event.get("dia") == day]
        if not day_events:
            continue
        parts = [
            f"{event.get('inicio')}-{event.get('fin')} "
            f"{event.get('titulo')} ({event.get('tipo')})"
            for event in day_events
        ]
        lines.append(f"{day}: " + "; ".join(parts))
    if not lines:
        return "No hay eventos para mostrar."
    return "\n".join(lines)


def _encode_image(path: str) -> str:
    with open(path, "rb") as file:
        data = base64.b64encode(file.read()).decode("ascii")
    return f"data:image/png;base64,{data}"
