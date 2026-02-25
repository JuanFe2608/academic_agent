"""Nodo para construir un borrador del horario."""

from __future__ import annotations

from agents.support.state import AgentState, Event, new_event_id, normalize_time, sort_events


def build_draft_schedule(state: AgentState) -> dict:
    """Normaliza eventos, ordena y detecta solapamientos basicos."""
    timezone = state.get("timezone", "America/Bogota")
    events: list[Event] = []
    errors = list(state.get("errors", []))

    for event in state.get("events", []):
        events.append(_ensure_event(event, timezone))

    events = sort_events(events)
    errors.extend(_detect_overlaps(events))

    return {"events": events, "errors": errors, "phase": "validate"}


def _ensure_event(event: Event | dict, timezone: str) -> Event:
    if isinstance(event, Event):
        updates: dict = {}
        if not event.id:
            updates["id"] = new_event_id()
        if not event.timezone:
            updates["timezone"] = timezone
        if updates:
            return _copy_model(event, updates)
        return event

    data = dict(event)
    data.setdefault("id", new_event_id())
    data.setdefault("timezone", timezone)
    return Event(**data)


def _copy_model(event: Event, updates: dict) -> Event:
    if hasattr(event, "model_copy"):
        return event.model_copy(update=updates)
    return event.copy(update=updates)


def _detect_overlaps(events: list[Event]) -> list[str]:
    warnings: list[str] = []
    by_day: dict[str, list[Event]] = {}
    for event in events:
        by_day.setdefault(event.get("dia", ""), []).append(event)

    for day, day_events in by_day.items():
        sorted_day = sorted(day_events, key=lambda e: normalize_time(e.get("inicio", "00:00")))
        prev_end = None
        for event in sorted_day:
            start = normalize_time(event.get("inicio", "00:00"))
            end = normalize_time(event.get("fin", "00:00"))
            if prev_end and start < prev_end:
                warnings.append(f"Solapamiento en {day}: {event.get('titulo', '')}")
            prev_end = end
    return warnings
