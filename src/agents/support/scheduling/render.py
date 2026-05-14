"""Adaptadores entre bloques recurrentes y el renderer semanal existente."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from agents.support.scheduling.schedule_renderer import (
    _DEFAULT_RENDER_DIR,
    render_week_schedule,
)
from schemas.scheduling import Event
from services.scheduling.event_projection import blocks_to_schedule_events
from services.scheduling.models import WeeklyScheduleBlock
from utils.media_artifacts import materialize_image_reference


@dataclass(frozen=True)
class RenderedSchedulePreview:
    image_path: str
    image_ref: str


def blocks_to_events(blocks: list[WeeklyScheduleBlock]) -> list[Event]:
    """Convierte bloques recurrentes al modelo visual actual de eventos."""

    return blocks_to_schedule_events(blocks)


def render_recurring_schedule(
    blocks: list[WeeklyScheduleBlock],
    out_dir: str = _DEFAULT_RENDER_DIR,
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

    filename = f"schedule-{uuid4().hex}.png"
    image_path = render_recurring_schedule(
        blocks,
        filename=filename,
        timezone_name=timezone_name,
    )
    return RenderedSchedulePreview(
        image_path=image_path,
        image_ref=materialize_image_reference(image_path),
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
            {"type": "image_url", "image_url": {"url": preview.image_ref}},
        ],
        preview.image_path,
    )
