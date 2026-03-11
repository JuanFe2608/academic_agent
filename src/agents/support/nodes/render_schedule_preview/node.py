"""Nodo para generar la vista previa del horario."""

from __future__ import annotations

from datetime import datetime

from agents.support.nodes.utils import append_message
from agents.support.state import AgentState, Event, sort_events
from agents.support.tools.calendar_logic import (
    format_day_label,
    format_week_title,
    resolve_weekly_events_to_current_week,
)
from agents.support.tools.event_labels import normalize_activity_label
from agents.support.tools.schedule_renderer import render_week_schedule

from .prompt import PROMPT

import base64


def render_schedule_preview(state: AgentState) -> dict:
    """Genera el texto e imagen de la vista previa."""
    events: list[Event] = list(state.get("events", []))
    timezone_name = state.get("timezone", "America/Bogota")
    preview_text = _build_text_preview(events, timezone_name)
    image_path = render_week_schedule(events, timezone_name=timezone_name)
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


def _build_text_preview(
    events: list[Event],
    timezone_name: str,
    reference: datetime | None = None,
) -> str:
    ordered_events = sort_events(events)
    slots, occurrences = resolve_weekly_events_to_current_week(
        ordered_events,
        timezone_name,
        reference,
    )
    table = _build_ascii_schedule_table(occurrences, slots)
    if not table:
        return format_week_title(slots)
    return format_week_title(slots) + "\n" + table


def _build_ascii_schedule_table(
    occurrences: list,
    slots: list,
) -> str:
    rows: list[tuple[str, str, str]] = []
    for slot in slots:
        day_occurrences = [
            occurrence
            for occurrence in occurrences
            if occurrence.event.get("dia") == slot.day_name
        ]
        if not day_occurrences:
            rows.append((format_day_label(slot), "Sin eventos", "-"))
            continue
        for occurrence in day_occurrences:
            event = occurrence.event
            rows.append(
                (
                    format_day_label(slot),
                    normalize_activity_label(
                        str(event.get("titulo") or ""),
                        str(event.get("categoria") or ""),
                    ),
                    f"{event.get('inicio')}-{event.get('fin')}",
                )
            )

    if not rows:
        return ""

    day_width = max(len("Dia"), *(len(row[0]) for row in rows))
    activity_width = max(len("Actividad"), *(len(row[1]) for row in rows))
    hour_width = max(len("Hora"), *(len(row[2]) for row in rows))

    separator = (
        "+"
        + "-" * (day_width + 2)
        + "+"
        + "-" * (activity_width + 2)
        + "+"
        + "-" * (hour_width + 2)
        + "+"
    )
    header = (
        f"| {'Dia'.ljust(day_width)} | "
        f"{'Actividad'.ljust(activity_width)} | "
        f"{'Hora'.ljust(hour_width)} |"
    )

    lines = [separator, header, separator]
    for row in rows:
        lines.append(
            f"| {row[0].ljust(day_width)} | "
            f"{row[1].ljust(activity_width)} | "
            f"{row[2].ljust(hour_width)} |"
        )
        lines.append(separator)
    return "\n".join(lines)


def _encode_image(path: str) -> str:
    with open(path, "rb") as file:
        data = base64.b64encode(file.read()).decode("ascii")
    return f"data:image/png;base64,{data}"
