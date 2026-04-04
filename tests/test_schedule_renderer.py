"""Prueba basica para el renderer semanal."""

import os
from datetime import datetime

from PIL import Image
from PIL import ImageDraw

from agents.support.scheduling.event_labels import normalize_activity_label
from agents.support.scheduling.schedule_renderer import (
    _load_fonts,
    _wrap_text,
    render_week_schedule,
)
from schemas.scheduling import Event
from services.scheduling.validation import new_event_id


def test_render_week_schedule(tmp_path):
    """Genera una imagen y verifica existencia y tamano."""
    events = [
        Event(
            id=new_event_id(),
            dia="Lunes",
            inicio="08:00",
            fin="10:00",
            titulo="Trabajo",
            tipo="confirmado",
            categoria="laboral",
            origen="user_text",
            timezone="America/Bogota",
        ),
        Event(
            id=new_event_id(),
            dia="Miercoles",
            inicio="14:00",
            fin="16:30",
            titulo="Clase",
            tipo="confirmado",
            categoria="academico",
            origen="user_text",
            timezone="America/Bogota",
        ),
        Event(
            id=new_event_id(),
            dia="Viernes",
            inicio="09:00",
            fin="11:00",
            titulo="Estudio",
            tipo="confirmado",
            categoria="estudio",
            origen="user_text",
            timezone="America/Bogota",
        ),
    ]

    output_path = render_week_schedule(
        events,
        out_dir=str(tmp_path),
        reference=datetime(2026, 3, 10, 9, 0),
    )

    assert os.path.exists(output_path)
    assert os.path.getsize(output_path) > 0
    with Image.open(output_path) as image:
        assert image.size == (1200, 828)


def test_wrap_text_splits_long_titles() -> None:
    image = Image.new("RGB", (400, 200), "white")
    draw = ImageDraw.Draw(image)
    fonts = _load_fonts()

    lines = _wrap_text(
        draw,
        "Actividad extracurricular con nombre demasiado largo para una sola linea",
        fonts["title"],
        120,
    )

    assert len(lines) > 1


def test_normalize_block_title_compacts_long_activity_text() -> None:
    title = normalize_activity_label(
        "Tengo que hacer trabajos para la universidad todos los dias desde las 4 am hasta las 5 am"
    )

    assert title in {"Hacer trabajos", "Trabajos universidad"}


def test_normalize_block_title_keeps_labor_as_trabajo_laboral() -> None:
    title = normalize_activity_label("Trabajo", "laboral")

    assert title == "Trabajo laboral"


def test_normalize_block_title_preserves_trabajo_de_grado_as_subject() -> None:
    title = normalize_activity_label("Trabajo de Grado II", "academico")

    assert title == "Trabajo de Grado II"
