"""Prueba basica para el renderer semanal."""

import os

from agents.support.tools.schedule_renderer import render_week_schedule
from agents.support.state import Event, new_event_id


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

    output_path = render_week_schedule(events, out_dir=str(tmp_path))

    assert os.path.exists(output_path)
    assert os.path.getsize(output_path) > 0
