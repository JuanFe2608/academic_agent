"""Pruebas para la vista previa resumida del horario."""

from __future__ import annotations

from pathlib import Path

import agents.support.scheduling.render as schedule_rendering
from agents.support.nodes.render_schedule_preview.node import render_schedule_preview
from agents.support.scheduling.formatter import build_schedule_summary
from agents.support.state import AgentState
from services.scheduling import ScheduleConflict, WeeklyScheduleBlock


def test_render_schedule_preview_shows_summary_and_confirmation(monkeypatch, tmp_path) -> None:
    image_path = tmp_path / "schedule.png"
    image_path.write_bytes(b"fake-png")

    monkeypatch.setattr(
        "agents.support.nodes.render_schedule_preview.node.build_rendered_schedule_message_content",
        lambda text, _blocks, **_kwargs: (
                [
                    {"type": "text", "text": text},
                    {"type": "image_url", "image_url": {"url": str(image_path)}},
                ],
                str(image_path),
            ),
    )

    blocks = [
        WeeklyScheduleBlock(
            block_type="academic",
            title="Calculo",
            day_of_week="monday",
            start_time="06:00",
            end_time="08:00",
            source_text="Lunes cálculo de 6 a 8 am",
        ),
        WeeklyScheduleBlock(
            block_type="work",
            title="Trabajo",
            day_of_week="tuesday",
            start_time="07:00",
            end_time="18:00",
            source_text="Martes trabajo 7 a 18",
        ),
    ]

    state = AgentState(
        schedule={
            "blocks": blocks,
            "conflicts": [],
            "summary_text": build_schedule_summary(blocks),
        }
    )

    update = render_schedule_preview(state)

    text = update["messages"][0].content[0]["text"]
    assert "Esto fue lo que entendí" in text
    assert "- Lunes: Calculo" in text
    assert "- Martes: Trabajo" in text
    # La pregunta de confirmación ya no va en el mensaje de imagen; la emite validate_schedule
    assert "¿Entendí bien tu horario?" not in text
    assert "1. Sí, está correcto" not in text
    rendered_image = update["messages"][0].content[1]["image_url"]["url"]
    assert not rendered_image.startswith("data:image")
    assert Path(rendered_image).exists()


def test_render_schedule_preview_prioritizes_conflict_message(monkeypatch, tmp_path) -> None:
    image_path = tmp_path / "schedule.png"
    image_path.write_bytes(b"fake-png")

    monkeypatch.setattr(
        "agents.support.nodes.render_schedule_preview.node.build_rendered_schedule_message_content",
        lambda text, _blocks, **_kwargs: (
                [
                    {"type": "text", "text": text},
                    {"type": "image_url", "image_url": {"url": str(image_path)}},
                ],
                str(image_path),
            ),
    )

    blocks = [
        WeeklyScheduleBlock(
            block_type="academic",
            title="Programacion",
            day_of_week="wednesday",
            start_time="08:00",
            end_time="10:00",
            source_text="Miércoles programación 8-10",
            has_conflict=True,
        ),
        WeeklyScheduleBlock(
            block_type="work",
            title="Trabajo",
            day_of_week="wednesday",
            start_time="09:00",
            end_time="18:00",
            source_text="Miércoles trabajo 9-18",
            has_conflict=True,
        ),
    ]
    conflict = ScheduleConflict(
        day_of_week="wednesday",
        left_block_id=blocks[0].block_id,
        right_block_id=blocks[1].block_id,
        left_title="Programacion",
        right_title="Trabajo",
        left_type="academic",
        right_type="work",
        overlap_start="09:00",
        overlap_end="10:00",
    )

    state = AgentState(
        schedule={
            "blocks": blocks,
            "conflicts": [conflict],
            "summary_text": build_schedule_summary(blocks),
        }
    )

    update = render_schedule_preview(state)

    text = update["messages"][0].content[0]["text"]
    # El mensaje de imagen solo lleva el resumen; los conflictos los emite validate_schedule
    assert "Encontré cruces" not in text
    assert "Miércoles" in text
    assert "Programacion" in text
    assert "Trabajo" in text
    # El review_stage queda correctamente seteado para que validate_schedule emita el conflicto
    schedule_state_dict = update["schedule"]
    assert schedule_state_dict.get("review_stage") == "awaiting_conflict_decision"


def test_render_schedule_preview_inlines_image_for_debugger(monkeypatch) -> None:
    monkeypatch.setenv("MEDIA_INLINE_PREVIEW", "true")
    blocks = [
        WeeklyScheduleBlock(
            block_type="academic",
            title="Calculo",
            day_of_week="monday",
            start_time="06:00",
            end_time="08:00",
            source_text="Lunes cálculo de 6 a 8 am",
        )
    ]
    state = AgentState(
        schedule={
            "blocks": blocks,
            "conflicts": [],
            "summary_text": build_schedule_summary(blocks),
        }
    )

    update = render_schedule_preview(state)

    rendered_image = update["messages"][0].content[1]["image_url"]["url"]
    assert rendered_image.startswith("data:image/")


def test_render_schedule_preview_image_uses_unique_file_names(monkeypatch) -> None:
    filenames: list[str] = []

    def fake_render_recurring_schedule(_blocks, **kwargs) -> str:
        filename = str(kwargs["filename"])
        filenames.append(filename)
        return f"/tmp/{filename}"

    monkeypatch.setattr(
        schedule_rendering,
        "render_recurring_schedule",
        fake_render_recurring_schedule,
    )
    monkeypatch.setattr(
        schedule_rendering,
        "materialize_image_reference",
        lambda image_path: image_path,
    )

    block = WeeklyScheduleBlock(
        block_type="academic",
        title="Calculo",
        day_of_week="monday",
        start_time="06:00",
        end_time="08:00",
        source_text="Lunes cálculo de 6 a 8 am",
    )

    first = schedule_rendering.render_schedule_preview_image([block])
    second = schedule_rendering.render_schedule_preview_image([block])

    assert first.image_path != second.image_path
    assert len(set(filenames)) == 2
    assert all(filename.startswith("schedule-") for filename in filenames)
    assert all(filename.endswith(".png") for filename in filenames)
