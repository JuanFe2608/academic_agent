"""Pruebas para expansion de eventos a fechas reales."""

from __future__ import annotations

from datetime import datetime

from agents.support.state import Event, new_event_id
from agents.support.tools.calendar_logic import (
    build_current_week_slots,
    format_week_title,
    resolve_weekly_events_to_current_week,
)


def test_build_current_week_slots_uses_current_week_dates() -> None:
    slots = build_current_week_slots(
        "America/Bogota",
        datetime(2026, 3, 10, 9, 0),
    )

    assert slots[0].day_name == "Lunes"
    assert slots[0].day_date.isoformat() == "2026-03-09"
    assert slots[-1].day_name == "Domingo"
    assert slots[-1].day_date.isoformat() == "2026-03-15"
    assert "Marzo de 2026" in format_week_title(slots)


def test_resolve_weekly_events_to_current_week_creates_concrete_datetimes() -> None:
    events = [
        Event(
            id=new_event_id(),
            dia="Lunes",
            inicio="18:00",
            fin="23:59",
            titulo="Trabajo",
            tipo="confirmado",
            categoria="laboral",
            origen="user_text",
            timezone="America/Bogota",
        ),
        Event(
            id=new_event_id(),
            dia="Martes",
            inicio="00:00",
            fin="03:00",
            titulo="Trabajo",
            tipo="confirmado",
            categoria="laboral",
            origen="user_text",
            timezone="America/Bogota",
        ),
    ]

    slots, occurrences = resolve_weekly_events_to_current_week(
        events,
        "America/Bogota",
        datetime(2026, 3, 10, 9, 0),
    )

    assert len(slots) == 7
    assert len(occurrences) == 2
    assert occurrences[0].start_at.isoformat().startswith("2026-03-09T18:00:00")
    assert occurrences[1].start_at.isoformat().startswith("2026-03-10T00:00:00")
