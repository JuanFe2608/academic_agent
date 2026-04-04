"""Cambios directos sobre agenda y actividades dentro de replanificacion."""

from __future__ import annotations

from agents.support.nodes.collect_extracurricular_details import (
    parse_extracurricular_items,
    parse_extracurricular_text,
)
from agents.support.nodes.utils import has_time_range, normalize_text
from agents.support.state import AgentState
from schemas.scheduling import Event
from services.scheduling.text_parser import parse_academic_schedule_text, parse_work_schedule_text
from services.scheduling.validation import validate_event

from ._activity_additions import (
    build_add_clarification_prompt,
    build_events_for_new_extracurricular_items,
    ensure_item,
    match_extracurricular,
    parse_activity_additions,
    rebuild_extracurricular_events,
    strip_change_intent,
)
from ._prompts import PROMPT_EXTRAS, PROMPT_HORARIO, PROMPT_HORARIO_ACADEMICO
from ._shared import (
    ReplanTurnContext,
    build_prompt_update,
    build_validate_update,
    clear_replan_change_request,
)


def apply_laboral_change(
    state: AgentState,
    details: str,
    operation: str,
    replan: dict,
    ctx: ReplanTurnContext,
) -> dict:
    if not details or not has_time_range(details):
        return build_prompt_update(ctx, replan, PROMPT_HORARIO)

    errors = list(state.get("errors", []))
    try:
        parsed = parse_work_schedule_text(details, state.get("timezone", "America/Bogota"))
    except ValueError as exc:
        errors.append(f"Horario laboral invalido: {exc}")
        return build_prompt_update(ctx, replan, PROMPT_HORARIO, errors=errors)

    new_events = _validated_schedule_events(parsed, errors, "laboral")
    if operation == "add":
        updated_events = list(state.get("events", [])) + new_events
    else:
        remaining = [event for event in state.get("events", []) if event.get("categoria") != "laboral"]
        updated_events = remaining + new_events

    raw_inputs = dict(state.get("raw_inputs", {}))
    raw_inputs["horario_laboral_text"] = details

    clear_replan_change_request(replan)
    return build_validate_update(
        ctx,
        replan=replan,
        awaiting_user_input=False,
        events=updated_events,
        errors=errors,
        raw_inputs=raw_inputs,
    )


def apply_academic_change(
    state: AgentState,
    details: str,
    operation: str,
    replan: dict,
    ctx: ReplanTurnContext,
) -> dict:
    if not details or not has_time_range(details):
        return build_prompt_update(ctx, replan, PROMPT_HORARIO_ACADEMICO)

    errors = list(state.get("errors", []))
    try:
        parsed = parse_academic_schedule_text(details, state.get("timezone", "America/Bogota"))
    except ValueError as exc:
        errors.append(f"Horario academico invalido: {exc}")
        return build_prompt_update(ctx, replan, PROMPT_HORARIO_ACADEMICO, errors=errors)

    new_events = _validated_schedule_events(parsed, errors, "academico")
    if operation == "add":
        updated_events = list(state.get("events", [])) + new_events
    else:
        remaining = [event for event in state.get("events", []) if event.get("categoria") != "academico"]
        updated_events = remaining + new_events

    raw_inputs = dict(state.get("raw_inputs", {}))
    raw_inputs["horario_academico_text"] = details

    clear_replan_change_request(replan)
    return build_validate_update(
        ctx,
        replan=replan,
        awaiting_user_input=False,
        events=updated_events,
        errors=errors,
        raw_inputs=raw_inputs,
    )


def apply_extracurricular_change(
    state: AgentState,
    details: str,
    operation: str,
    activity_name: str,
    replan: dict,
    ctx: ReplanTurnContext,
) -> dict:
    extracurricular_items = [ensure_item(item) for item in state.get("extracurricular", [])]
    if not extracurricular_items and operation != "add":
        return build_prompt_update(
            ctx,
            replan,
            "No hay actividades extracurriculares registradas para modificar.",
        )

    target_item = match_extracurricular(activity_name, extracurricular_items)
    if operation == "add":
        target_item = None
    if not target_item and activity_name and operation != "add":
        disponibles = ", ".join(item.nombre for item in extracurricular_items)
        return build_prompt_update(
            ctx,
            replan,
            (
                f"La actividad '{activity_name}' no existe. "
                f"Actividades disponibles: {disponibles}. Usa la tabla anterior como referencia."
            ),
        )
    if not target_item and len(extracurricular_items) == 1 and operation != "add":
        target_item = extracurricular_items[0]
    if not target_item and operation != "add":
        disponibles = ", ".join(item.nombre for item in extracurricular_items)
        return build_prompt_update(
            ctx,
            replan,
            (
                "Indica que actividad quieres modificar. "
                f"Actividades disponibles: {disponibles}. Usa la tabla anterior como referencia."
            ),
        )

    if operation == "delete":
        updated_extracurricular = [
            item
            for item in extracurricular_items
            if normalize_text(item.nombre) != normalize_text(target_item.nombre)
        ]
        updated_events = [
            event
            for event in state.get("events", [])
            if not (
                event.get("categoria") == "extracurricular"
                and normalize_text(str(event.get("titulo") or "")) == normalize_text(target_item.nombre)
            )
        ]
        clear_replan_change_request(replan)
        return build_validate_update(
            ctx,
            replan=replan,
            awaiting_user_input=False,
            events=updated_events,
            errors=list(state.get("errors", [])),
            extracurricular=updated_extracurricular,
        )

    if not details:
        activity_label = target_item.nombre if target_item else "nueva actividad"
        return build_prompt_update(
            ctx,
            replan,
            f"{PROMPT_EXTRAS}\nActividad actual: {activity_label}.",
        )

    if operation == "add":
        items, missing = parse_extracurricular_items(details)
        if missing:
            return build_prompt_update(ctx, replan, build_add_clarification_prompt(missing))

        new_events, errors = build_events_for_new_extracurricular_items(
            items,
            state.get("timezone", "America/Bogota"),
            list(state.get("errors", [])),
        )
        clear_replan_change_request(replan)
        return build_validate_update(
            ctx,
            replan=replan,
            awaiting_user_input=False,
            events=list(state.get("events", [])) + new_events,
            errors=errors,
            extracurricular=extracurricular_items + items,
        )

    reference_name = target_item.nombre if target_item else ""
    normalized_details = strip_change_intent(details, reference_name)
    item, missing = parse_extracurricular_text(
        normalized_details,
        expected_is_variable=target_item.es_variable if target_item else None,
    )
    missing = [field for field in missing if field != "nombre"]
    if missing:
        return build_prompt_update(
            ctx,
            replan,
            (
                f"{PROMPT_EXTRAS}\nActividad a cambiar: {reference_name or 'nueva actividad'}.\n"
                "Faltan: " + ", ".join(missing) + "."
            ),
        )

    updated_item = (
        item.model_copy(update={"nombre": target_item.nombre})
        if hasattr(item, "model_copy")
        else item.copy(update={"nombre": target_item.nombre})
    )
    updated_extracurricular = [
        updated_item if normalize_text(existing.nombre) == normalize_text(target_item.nombre) else existing
        for existing in extracurricular_items
    ]
    updated_events, errors = rebuild_extracurricular_events(
        updated_extracurricular,
        state.get("events", []),
        state.get("timezone", "America/Bogota"),
        list(state.get("errors", [])),
    )

    clear_replan_change_request(replan)
    return build_validate_update(
        ctx,
        replan=replan,
        awaiting_user_input=False,
        events=updated_events,
        errors=errors,
        extracurricular=updated_extracurricular,
    )


def apply_activity_additions(
    state: AgentState,
    details: str,
    replan: dict,
    ctx: ReplanTurnContext,
) -> dict:
    if not details or not has_time_range(details):
        return build_prompt_update(
            ctx,
            replan,
            (
                "Indica la actividad que deseas anadir con nombre, dias y horario. "
                "Si vas a anadir varias, puedes escribirlas en un solo mensaje."
            ),
        )

    parsed = parse_activity_additions(details, state.get("timezone", "America/Bogota"))
    if parsed["prompt"]:
        return build_prompt_update(ctx, replan, str(parsed["prompt"]))

    errors = list(state.get("errors", []))
    validated_events: list[Event] = []
    for event in list(parsed["events"]):
        try:
            validate_event(event)
        except ValueError as exc:
            errors.append(f"Evento invalido al anadir actividad: {exc}")
            continue
        validated_events.append(event)

    clear_replan_change_request(replan)
    return build_validate_update(
        ctx,
        replan=replan,
        awaiting_user_input=False,
        events=list(state.get("events", [])) + validated_events,
        errors=errors,
        extracurricular=[ensure_item(item) for item in state.get("extracurricular", [])]
        + list(parsed["extracurricular"]),
    )


def _validated_schedule_events(
    parsed: list[Event],
    errors: list[str],
    category: str,
) -> list[Event]:
    new_events: list[Event] = []
    for event in parsed:
        try:
            validate_event(event)
        except ValueError as exc:
            errors.append(f"Evento {category} invalido: {exc}")
            continue
        new_events.append(event)
    return new_events


__all__ = [
    "apply_academic_change",
    "apply_activity_additions",
    "apply_extracurricular_change",
    "apply_laboral_change",
]
