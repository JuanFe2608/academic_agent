"""Adaptadores entre bloques recurrentes y el renderer semanal existente."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime

from agents.support.scheduling.schedule_renderer import render_week_schedule
from schemas.scheduling import Event
from services.scheduling.event_projection import blocks_to_schedule_events
from services.scheduling.models import WeeklyScheduleBlock


@dataclass(frozen=True)
class RenderedSchedulePreview:
    image_path: str
    image_data_url: str


def blocks_to_events(blocks: list[WeeklyScheduleBlock]) -> list[Event]:
    """Convierte bloques recurrentes al modelo visual actual de eventos."""

    return blocks_to_schedule_events(blocks)


def render_recurring_schedule(
    blocks: list[WeeklyScheduleBlock],
    out_dir: str = "tmp",
    filename: str = "schedule.png",
    timezone_name: str = "America/Bogota",
    reference: datetime | None = None,
) -> str:
    """Renderiza bloques recurrentes reutilizando el renderer actual."""

    return render_week_schedule(
        blocks_to_events(blocks),
        out_dir=out_dir,
        filename=filename,
        timezone_name=timezone_name,
        reference=reference,
    )


def render_schedule_preview_image(
    blocks: list[WeeklyScheduleBlock],
    *,
    timezone_name: str = "America/Bogota",
) -> RenderedSchedulePreview:
    """Renderiza el horario y devuelve path + data URL reutilizable."""

    image_path = render_recurring_schedule(blocks, timezone_name=timezone_name)
    return RenderedSchedulePreview(
        image_path=image_path,
        image_data_url=_encode_image(image_path),
    )


def build_rendered_schedule_message_content(
    text: str,
    blocks: list[WeeklyScheduleBlock],
    *,
    timezone_name: str = "America/Bogota",
) -> tuple[list[dict[str, object]], str]:
    """Construye contenido multimodal con texto e imagen del horario."""

    preview = render_schedule_preview_image(blocks, timezone_name=timezone_name)
    return (
        [
            {"type": "text", "text": text},
            {"type": "image_url", "image_url": {"url": preview.image_data_url}},
        ],
        preview.image_path,
    )


def _encode_image(path: str) -> str:
    with open(path, "rb") as file:
        data = base64.b64encode(file.read()).decode("ascii")
    return f"data:image/png;base64,{data}"
