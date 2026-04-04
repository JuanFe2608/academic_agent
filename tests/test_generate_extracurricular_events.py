"""Pruebas de generacion de eventos extracurricular."""

from __future__ import annotations

from services.scheduling.extracurricular_events import (
    generate_tentative_extracurricular,
)
from agents.support.state import AgentState
from schemas.scheduling import ExtracurricularItem


def test_generate_fixed_extracurricular_events_from_schedule(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.scheduling.extracurricular_events.llm_normalize_schedule",
        lambda *_args, **_kwargs: None,
    )
    state = AgentState(
        phase="extras",
        extracurricular=[
            ExtracurricularItem(
                nombre="Natacion",
                es_variable=False,
                detalle="martes y jueves 18:00-19:00",
                tentativo=[],
            )
        ],
    )

    update = generate_tentative_extracurricular(state)

    assert update["phase"] == "draft"
    events = update["events"]
    assert len(events) == 2
    assert all(event.categoria == "extracurricular" for event in events)
    assert all(event.tipo == "confirmado" for event in events)
    assert {event.dia for event in events} == {"Martes", "Jueves"}
