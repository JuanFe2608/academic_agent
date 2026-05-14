"""Cambios directos sobre agenda y actividades dentro de replanificacion."""

from __future__ import annotations

from agents.support.nodes.collect_extracurricular_details import (
    parse_extracurricular_items,
    parse_extracurricular_text,
)
from agents.support.nodes.utils import has_time_range, normalize_text
from agents.support.scheduling.state_helpers import (
    ensure_schedule_flow_state,
    events_for_scheduling_update,
    schedule_flow_state_to_update,
)
from agents.support.state import AgentState
from schemas.scheduling import Event
from services.scheduling.event_projection import events_to_schedule_blocks
from services.scheduling.text_parser import parse_academic_schedule_text, parse_work_schedule_text
from services.scheduling.validation import validate_event

from ._activity_additions import (
    build_add_clarification_prompt,
    build_events_from_extracurricular_item,
    ensure_item,
    match_extracurricular,
    parse_activity_additions,
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
    new_work_blocks = events_to_schedule_blocks(new_events, "work")

    schedule_state = ensure_schedule_flow_state(state.get("schedule", {}))
    if operation == "add":
        updated_blocks = list(schedule_state.blocks) + new_work_blocks
    else:
        non_work = [b for b in schedule_state.blocks if b.block_type != "work"]
        updated_blocks = non_work + new_work_blocks

    raw_inputs = dict(state.get("raw_inputs", {}))
    raw_inputs["horario_laboral_text"] = details

    clear_replan_change_request(replan)
    updated_schedule = schedule_state.model_copy(update={"blocks": updated_blocks})
    return build_validate_update(
        ctx,
        replan=replan,
        awaiting_user_input=False,
        schedule=schedule_flow_state_to_update(updated_schedule),
        events=events_for_scheduling_update(state, schedule=updated_schedule),
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
    new_academic_blocks = events_to_schedule_blocks(new_events, "academic")

    schedule_state = ensure_schedule_flow_state(state.get("schedule", {}))
    if operation == "add":
        updated_blocks = list(schedule_state.blocks) + new_academic_blocks
    else:
        non_academic = [b for b in schedule_state.blocks if b.block_type != "academic"]
        updated_blocks = non_academic + new_academic_blocks

    raw_inputs = dict(state.get("raw_inputs", {}))
    raw_inputs["horario_academico_text"] = details

    clear_replan_change_request(replan)
    updated_schedule = schedule_state.model_copy(update={"blocks": updated_blocks})
    return build_validate_update(
        ctx,
        replan=replan,
        awaiting_user_input=False,
        schedule=schedule_flow_state_to_update(updated_schedule),
        events=events_for_scheduling_update(state, schedule=updated_schedule),
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
        clear_replan_change_request(replan)
        return build_validate_update(
            ctx,
            replan=replan,
            awaiting_user_input=False,
            errors=list(state.get("errors", [])),
            extracurricular=updated_extracurricular,
            events=events_for_scheduling_update(
                state,
                extracurricular=updated_extracurricular,
            ),
        )

    if not details:
        activity_label = target_item.nombre if target_item else "nueva actividad"
        return build_prompt_update(
            ctx,
            replan,
            f"{PROMPT_EXTRAS}\nActividad actual: {activity_label}.",
        )

    tz = state.get("timezone", "America/Bogota")

    if operation == "add":
        items, missing = parse_extracurricular_items(details)
        if missing:
            return build_prompt_update(ctx, replan, build_add_clarification_prompt(missing))

        errors = list(state.get("errors", []))
        items_with_events = []
        for item in items:
            generated = _valid_extracurricular_events(
                build_events_from_extracurricular_item(item, tz), errors
            )
            items_with_events.append(item.model_copy(update={"tentativo": generated}))

        clear_replan_change_request(replan)
        return build_validate_update(
            ctx,
            replan=replan,
            awaiting_user_input=False,
            errors=errors,
            extracurricular=extracurricular_items + items_with_events,
            events=events_for_scheduling_update(
                state,
                extracurricular=extracurricular_items + items_with_events,
            ),
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
    errors = list(state.get("errors", []))
    new_tentativo = _valid_extracurricular_events(
        build_events_from_extracurricular_item(updated_item, tz), errors
    )
    updated_item = updated_item.model_copy(update={"tentativo": new_tentativo})
    updated_extracurricular = [
        updated_item if normalize_text(existing.nombre) == normalize_text(target_item.nombre) else existing
        for existing in extracurricular_items
    ]

    clear_replan_change_request(replan)
    return build_validate_update(
        ctx,
        replan=replan,
        awaiting_user_input=False,
        errors=errors,
        extracurricular=updated_extracurricular,
        events=events_for_scheduling_update(
            state,
            extracurricular=updated_extracurricular,
        ),
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
    tz = state.get("timezone", "America/Bogota")

    # Convertir eventos académicos/laborales a bloques y actualizar schedule
    academic_blocks = events_to_schedule_blocks(
        _filter_valid_events(list(parsed["events"]), errors), "academic"
    )
    work_blocks = events_to_schedule_blocks(
        _filter_valid_events(list(parsed["events"]), errors), "work"
    )
    schedule_state = ensure_schedule_flow_state(state.get("schedule", {}))
    updated_blocks = list(schedule_state.blocks) + academic_blocks + work_blocks

    # Agregar eventos generados a los items extracurriculares nuevos
    new_extra_items = list(parsed["extracurricular"])
    new_extra_items_with_events = []
    for item in new_extra_items:
        generated = _valid_extracurricular_events(
            build_events_from_extracurricular_item(item, tz), errors
        )
        new_extra_items_with_events.append(item.model_copy(update={"tentativo": generated}))

    clear_replan_change_request(replan)
    update: dict = {
        "errors": errors,
        "extracurricular": [ensure_item(item) for item in state.get("extracurricular", [])]
        + new_extra_items_with_events,
    }
    if updated_blocks != list(schedule_state.blocks):
        updated_schedule = schedule_state.model_copy(update={"blocks": updated_blocks})
        update["schedule"] = schedule_flow_state_to_update(updated_schedule)
        update["events"] = events_for_scheduling_update(
            state,
            schedule=updated_schedule,
            extracurricular=update["extracurricular"],
        )
    else:
        update["events"] = events_for_scheduling_update(
            state,
            extracurricular=update["extracurricular"],
        )
    return build_validate_update(ctx, replan=replan, awaiting_user_input=False, **update)


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


def _filter_valid_events(events: list[Event], errors: list[str]) -> list[Event]:
    valid: list[Event] = []
    for event in events:
        try:
            validate_event(event)
        except ValueError as exc:
            errors.append(f"Evento invalido al anadir actividad: {exc}")
            continue
        valid.append(event)
    return valid


def _valid_extracurricular_events(
    events: list[Event],
    errors: list[str],
) -> list[Event]:
    valid: list[Event] = []
    for event in events:
        try:
            validate_event(event)
        except ValueError as exc:
            errors.append(f"Evento extracurricular invalido: {exc}")
            continue
        valid.append(event)
    return valid


__all__ = [
    "apply_academic_change",
    "apply_activity_additions",
    "apply_extracurricular_change",
    "apply_laboral_change",
]
