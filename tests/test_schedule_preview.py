"""Pruebas para la vista previa resumida del horario."""

from __future__ import annotations

from agents.support.nodes.render_schedule_preview.node import render_schedule_preview
from agents.support.scheduling.formatter import build_schedule_summary
from agents.support.state import AgentState
from services.scheduling import ScheduleConflict, WeeklyScheduleBlock


def test_render_schedule_preview_shows_summary_and_confirmation(monkeypatch, tmp_path) -> None:
    image_path = tmp_path / "schedule.png"
    image_path.write_bytes(b"fake-png")

    monkeypatch.setattr(
        "agents.support.nodes.render_schedule_preview.node.render_recurring_schedule",
        lambda _blocks, **_kwargs: str(image_path),
    )
    monkeypatch.setattr(
        "agents.support.nodes.render_schedule_preview.node._encode_image",
        lambda _path: "data:image/png;base64,abc",
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
    assert "¿Entendí bien tu horario?" in text
    assert update["messages"][0].content[1]["image_url"]["url"] == "data:image/png;base64,abc"


def test_render_schedule_preview_prioritizes_conflict_message(monkeypatch, tmp_path) -> None:
    image_path = tmp_path / "schedule.png"
    image_path.write_bytes(b"fake-png")

    monkeypatch.setattr(
        "agents.support.nodes.render_schedule_preview.node.render_recurring_schedule",
        lambda _blocks, **_kwargs: str(image_path),
    )
    monkeypatch.setattr(
        "agents.support.nodes.render_schedule_preview.node._encode_image",
        lambda _path: "data:image/png;base64,abc",
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
    assert "Encontré cruces" in text
    assert "Miércoles" in text
    assert "Programacion" in text
    assert "Trabajo" in text
