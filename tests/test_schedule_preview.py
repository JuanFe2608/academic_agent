"""Pruebas para la vista previa textual del horario."""

from __future__ import annotations

from datetime import datetime

from agents.support.nodes.render_schedule_preview.node import render_schedule_preview
import agents.support.nodes.render_schedule_preview.node as preview_node
from agents.support.state import AgentState, Event, new_event_id


def test_render_schedule_preview_lists_all_days_and_mentions_full_day(monkeypatch, tmp_path) -> None:
    image_path = tmp_path / "schedule.png"
    image_path.write_bytes(b"fake-png")

    monkeypatch.setattr(
        "agents.support.nodes.render_schedule_preview.node.render_week_schedule",
        lambda _events, **_kwargs: str(image_path),
    )
    monkeypatch.setattr(
        "agents.support.nodes.render_schedule_preview.node._encode_image",
        lambda _path: "data:image/png;base64,abc",
    )

    state = AgentState(
        events=[
            Event(
                id=new_event_id(),
                dia="Lunes",
                inicio="05:00",
                fin="06:00",
                titulo="Gym",
                tipo="confirmado",
                categoria="extracurricular",
                origen="user_text",
                timezone="America/Bogota",
            ),
            Event(
                id=new_event_id(),
                dia="Viernes",
                inicio="17:00",
                fin="18:00",
                titulo="Trabajo",
                tipo="confirmado",
                categoria="laboral",
                origen="user_text",
                timezone="America/Bogota",
            ),
        ]
    )

    preview_text = preview_node._build_text_preview(
        state.get("events", []),
        "America/Bogota",
        datetime(2026, 3, 10, 9, 0),
    )
    monkeypatch.setattr(
        "agents.support.nodes.render_schedule_preview.node._build_text_preview",
        lambda _events, _timezone_name: preview_text,
    )

    update = render_schedule_preview(state)

    preview_text = update["schedule_preview"]["text"]
    assert update["schedule_preview"]["image_path"] == str(image_path)
    assert "Semana del 9 al 15 de Marzo de 2026" in preview_text
    assert "| Dia" in preview_text
    assert "| Lunes 09/03/2026" in preview_text
    assert "| Gym" in preview_text
    assert "| 05:00-06:00" in preview_text
    assert "| Martes 10/03/2026" in preview_text
    assert "| Sin eventos" in preview_text
    assert "| Trabajo laboral" in preview_text

    message = update["messages"][0].content
    assert message[0]["type"] == "text"
    assert "00:00 a 23:59" in message[0]["text"]
    assert "| Martes 10/03/2026" in message[0]["text"]
    assert message[1]["type"] == "image_url"
    assert message[1]["image_url"]["url"] == "data:image/png;base64,abc"
