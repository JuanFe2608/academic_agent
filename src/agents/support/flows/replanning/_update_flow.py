"""Subflujo de actualizacion de actividades dentro de replanificacion."""

from __future__ import annotations

import re

from agents.support.nodes.collect_extracurricular_details import parse_extracurricular_text
from agents.support.nodes.utils import normalize_text, parse_yes_no
from agents.support.scheduling.state_helpers import (
    ensure_schedule_flow_state,
    events_for_scheduling_update,
    get_all_schedule_events,
    schedule_flow_state_to_update,
)
from agents.support.state import AgentState
from schemas.scheduling import Event
from services.scheduling.activity_matching import suggest_similar_titles
from services.scheduling.event_projection import (
    blocks_to_schedule_events,
    event_block_id,
    events_to_schedule_blocks,
)
from services.scheduling.text_parser import extract_natural_schedule_components
from services.scheduling.validation import validate_event

from ._prompts import PROMPT_EXTRAS
from ._activity_additions import (
    build_events_from_extracurricular_item,
    build_events_from_schedule,
    ensure_item,
    find_extracurricular_item_index,
    format_extracurricular_update_summary,
    has_explicit_activity_name,
    infer_activity_title,
    strip_change_intent,
)
from ._matching import (
    build_match_table,
    event_from_id,
    events_from_ids,
    filter_events_by_hint,
    find_delete_matches,
)
from ._shared import (
    ReplanTurnContext,
    build_prompt_update,
    build_validate_update,
    clear_replan_change_request,
)


def handle_activity_update(
    state: AgentState,
    target: str,
    activity_name: str,
    details: str,
    replan: dict,
    ctx: ReplanTurnContext,
) -> dict:
    change_request = dict(replan.get("change_request") or {})
    stage = str(change_request.get("stage") or "")
    details = str(details or "").strip()
    candidate_ids = list(change_request.get("candidate_event_ids") or [])
    selected_event_id = str(change_request.get("selected_event_id") or "")
    selected_event_ids = list(change_request.get("selected_event_ids") or [])
    all_events = get_all_schedule_events(state)
    selected_event = event_from_id(all_events, selected_event_id)
    selected_events = events_from_ids(all_events, selected_event_ids)
    apply_to_all = bool(change_request.get("apply_to_all"))

    if stage == "awaiting_update_identifier":
        options = events_from_ids(candidate_events_for_target(state, target), candidate_ids)
        selected = select_update_candidate(options, details)
        if not selected:
            return build_prompt_update(ctx, replan, build_multiple_update_prompt(options))
        change_request["selected_event_id"] = str(selected.get("id"))
        change_request["candidate_event_ids"] = None
        change_request["stage"] = "awaiting_update_candidate_confirmation"
        replan["change_request"] = change_request
        return build_prompt_update(ctx, replan, build_update_candidate_confirmation_prompt(selected))

    if stage == "awaiting_update_candidate_confirmation":
        answer = parse_yes_no(details)
        if answer is None:
            prompt = str(
                replan.get("pending_prompt") or "Responde si o no para confirmar la actividad a modificar."
            )
            return build_prompt_update(ctx, replan, prompt)
        if answer is False:
            change_request["stage"] = "awaiting_update_reference"
            change_request["selected_event_id"] = None
            change_request["candidate_event_ids"] = None
            change_request["update_payload"] = None
            change_request["update_summary"] = None
            replan["change_request"] = change_request
            return build_prompt_update(
                ctx,
                replan,
                build_available_update_reference_prompt(target, candidate_events_for_target(state, target)),
            )
        if not selected_event:
            change_request["stage"] = "awaiting_update_reference"
            replan["change_request"] = change_request
            return build_prompt_update(
                ctx,
                replan,
                build_available_update_reference_prompt(target, candidate_events_for_target(state, target)),
            )
        if str(change_request.get("update_payload") or "").strip():
            return _queue_update_apply_confirmation(
                state,
                target,
                selected_event,
                str(change_request.get("update_payload") or "").strip(),
                change_request,
                replan,
                ctx,
            )
        change_request["stage"] = "awaiting_update_new_details"
        replan["change_request"] = change_request
        return build_prompt_update(
            ctx,
            replan,
            build_update_details_prompt(target, selected_event),
        )

    if stage == "awaiting_update_new_details":
        if not details:
            return build_prompt_update(
                ctx,
                replan,
                build_update_details_prompt(effective_update_target(target, selected_event), selected_event),
            )
        return _queue_update_apply_confirmation(
            state,
            target,
            selected_event,
            details,
            change_request,
            replan,
            ctx,
        )

    if stage == "awaiting_update_all_details":
        if not details:
            return build_prompt_update(ctx, replan, build_update_all_details_prompt(selected_events))
        return _queue_update_all_apply_confirmation(
            state,
            target,
            selected_events,
            details,
            change_request,
            replan,
            ctx,
        )

    if stage == "awaiting_update_apply_confirmation":
        answer = parse_yes_no(details)
        if answer is None:
            prompt = str(replan.get("pending_prompt") or "Responde si o no para confirmar la modificacion.")
            return build_prompt_update(ctx, replan, prompt)
        if answer is False:
            clear_replan_change_request(replan)
            return build_validate_update(ctx, replan=replan, awaiting_user_input=False)
        if selected_events:
            return _apply_confirmed_activity_update_all(
                state,
                target,
                selected_events,
                str(change_request.get("update_payload") or "").strip(),
                replan,
                ctx,
            )
        return _apply_confirmed_activity_update(
            state,
            target,
            selected_event,
            str(change_request.get("update_payload") or "").strip(),
            replan,
            ctx,
        )

    if not details:
        return build_prompt_update(ctx, replan, build_initial_update_reference_prompt(target))

    candidate_events = candidate_events_for_target(state, target)
    reference_text, update_payload = extract_update_reference_and_payload(details, activity_name)
    matches = find_delete_matches(candidate_events, reference_text)
    if not matches and len(candidate_events) == 1 and not activity_name:
        matches = candidate_events
    if not matches:
        return build_prompt_update(
            ctx,
            replan,
            build_not_found_update_prompt(target, candidate_events, activity_name or reference_text or details),
        )

    if len(matches) > 1:
        if apply_to_all:
            change_request["selected_event_ids"] = [str(event.get("id")) for event in matches]
            change_request["candidate_event_ids"] = None
            if update_payload:
                return _queue_update_all_apply_confirmation(
                    state,
                    target,
                    matches,
                    update_payload,
                    change_request,
                    replan,
                    ctx,
                )
            change_request["stage"] = "awaiting_update_all_details"
            replan["change_request"] = change_request
            return build_prompt_update(ctx, replan, build_update_all_details_prompt(matches))
        selected = select_update_candidate(matches, reference_text)
        if not selected:
            change_request["stage"] = "awaiting_update_identifier"
            change_request["candidate_event_ids"] = [str(event.get("id")) for event in matches]
            change_request["update_payload"] = update_payload or None
            replan["change_request"] = change_request
            return build_prompt_update(ctx, replan, build_multiple_update_prompt(matches))
        matches = [selected]

    selected_event = matches[0]
    if not update_payload and reference_is_name_only(reference_text, selected_event):
        change_request["selected_event_id"] = str(selected_event.get("id"))
        change_request["candidate_event_ids"] = None
        change_request["update_payload"] = None
        change_request["stage"] = "awaiting_update_new_details"
        replan["change_request"] = change_request
        return build_prompt_update(ctx, replan, build_update_name_only_prompt(selected_event))

    change_request["selected_event_id"] = str(selected_event.get("id"))
    change_request["candidate_event_ids"] = None
    change_request["update_payload"] = update_payload or None
    change_request["stage"] = "awaiting_update_candidate_confirmation"
    replan["change_request"] = change_request
    return build_prompt_update(ctx, replan, build_update_candidate_confirmation_prompt(selected_event))


def candidate_events_for_target(state: AgentState, target: str) -> list[Event]:
    all_events = get_all_schedule_events(state)
    if target == "activity_lookup":
        return all_events
    return [event for event in all_events if event.get("categoria") == target]


def extract_update_reference_and_payload(details: str, activity_name: str) -> tuple[str, str]:
    text = str(details or "").strip()
    if not text:
        return "", ""
    if activity_name:
        pattern = re.compile(
            rf"(?:cambiar|modificar|ajustar).{{0,80}}{re.escape(activity_name)}\s+a\s+(.+)",
            re.IGNORECASE,
        )
        match = pattern.search(text)
        return (activity_name, match.group(1).strip()) if match else (text, "")

    match = re.search(
        r"(?:quiero\s+|necesito\s+|por\s+favor\s+)?(?:cambiar|modificar|ajustar)\s+"
        r"(?:la\s+actividad\s+)?(?:de\s+)?(.+?)(?:\s+a\s+(.+))?$",
        text,
        re.IGNORECASE,
    )
    if not match:
        return text, ""
    reference = str(match.group(1) or "").strip(" ,.:;")
    payload = str(match.group(2) or "").strip()
    return reference or text, payload


def build_update_candidate_confirmation_prompt(event: Event | dict | None) -> str:
    if not event:
        return "No pude identificar la actividad. Indica nuevamente cual deseas modificar."
    return (
        "Esta es la actividad que quieres cambiar?\n\n"
        f"Actividad: {event.get('titulo')}\n"
        f"Dia(s): {event.get('dia')}\n"
        f"Horario: {event.get('inicio')}-{event.get('fin')}\n"
        f"Tipo: {format_event_type(str(event.get('categoria') or ''))}"
    )


def build_multiple_update_prompt(matches: list[Event]) -> str:
    if not matches:
        return "No encontre coincidencias. Indica nombre, dia u horario de la actividad."
    activity_name = str(matches[0].get("titulo") or "la actividad")
    lines = [
        f"Encontre varias actividades con el nombre {activity_name}.",
        "Indica cual deseas modificar especificando el dia o el horario.",
    ]
    for index, event in enumerate(matches, start=1):
        lines.append(
            f"{index}. {event.get('titulo')} - {event.get('dia')} {event.get('inicio')}-{event.get('fin')}"
        )
    return "\n".join(lines)


def build_update_details_prompt(target: str, event: Event | dict | None) -> str:
    if target == "academico":
        return (
            "Indica el nuevo dia y horario de la actividad academica. "
            "Si cambia, incluye tambien la materia."
        )
    if target == "laboral":
        return "Indica el nuevo dia y horario de la actividad laboral."
    activity_name = str(event.get("titulo") or "la actividad") if event else "la actividad"
    return (
        f"Indica el nuevo dia y horario de {activity_name}. "
        "Si cambia el nombre, tambien puedes incluirlo."
    )


def build_final_update_confirmation_prompt(event: Event | dict | None, update_summary: str) -> str:
    if not event:
        return "No pude identificar la actividad a modificar. Indica nuevamente cual deseas cambiar."
    return (
        "Estas seguro de que deseas modificar esta actividad?\n\n"
        f"Actividad actual: {event.get('titulo')}\n"
        f"Dia(s) actuales: {event.get('dia')}\n"
        f"Horario actual: {event.get('inicio')}-{event.get('fin')}\n"
        f"Tipo: {format_event_type(str(event.get('categoria') or ''))}\n\n"
        "Quedara asi:\n"
        f"{update_summary}"
    )


def build_final_update_all_confirmation_prompt(events: list[Event], update_summary: str) -> str:
    activity_name = str(events[0].get("titulo") or "la actividad") if events else "la actividad"
    return (
        f"Se modificaran todas las actividades llamadas '{activity_name}'.\n\n"
        "Coincidencias actuales:\n"
        f"{build_match_table(events)}\n\n"
        "Quedaran asi:\n"
        f"{update_summary}\n\n"
        "Deseas continuar?"
    )


def format_event_type(category: str) -> str:
    return {
        "academico": "academica",
        "laboral": "laboral",
        "extracurricular": "extracurricular",
    }.get(category, category or "desconocido")


def select_update_candidate(matches: list[Event], details: str) -> Event | None:
    if not matches:
        return None
    selected_index = parse_numeric_selection(details, len(matches))
    if selected_index is not None:
        return matches[selected_index]
    filtered = filter_events_by_hint(matches, details)
    if len(filtered) == 1:
        return filtered[0]
    if len(filtered) > 1:
        return None
    exact_matches = find_delete_matches(matches, details)
    if len(exact_matches) == 1:
        return exact_matches[0]
    return None


def parse_numeric_selection(details: str, total: int) -> int | None:
    normalized = normalize_text(details)
    match = re.fullmatch(r"(\d+)[\).:-]?", normalized)
    if not match:
        return None
    index = int(match.group(1)) - 1
    if 0 <= index < total:
        return index
    return None


def _apply_confirmed_activity_update(
    state: AgentState,
    target: str,
    selected_event: Event | dict | None,
    update_payload: str,
    replan: dict,
    ctx: ReplanTurnContext,
) -> dict:
    if not selected_event:
        return build_prompt_update(
            ctx,
            replan,
            "No encontre la actividad seleccionada. Indica nuevamente cual deseas modificar.",
        )
    effective_target = effective_update_target(target, selected_event)
    if effective_target == "academico":
        return _apply_selected_academic_update(state, selected_event, update_payload, replan, ctx)
    if effective_target == "laboral":
        return _apply_selected_laboral_update(state, selected_event, update_payload, replan, ctx)
    return _apply_selected_extracurricular_update(state, selected_event, update_payload, replan, ctx)


def _apply_confirmed_activity_update_all(
    state: AgentState,
    target: str,
    selected_events: list[Event],
    update_payload: str,
    replan: dict,
    ctx: ReplanTurnContext,
) -> dict:
    if not selected_events:
        return build_prompt_update(ctx, replan, "No encontre las actividades seleccionadas.")
    effective_target = effective_update_target(target, selected_events[0])
    if effective_target == "academico":
        return _apply_selected_academic_update_all(state, selected_events, update_payload, replan, ctx)
    if effective_target == "laboral":
        return _apply_selected_laboral_update_all(state, selected_events, update_payload, replan, ctx)
    return _apply_selected_extracurricular_update(state, selected_events[0], update_payload, replan, ctx)


def _queue_update_apply_confirmation(
    state: AgentState,
    target: str,
    selected_event: Event | dict | None,
    update_payload: str,
    change_request: dict,
    replan: dict,
    ctx: ReplanTurnContext,
) -> dict:
    preview = preview_update_payload(
        state,
        effective_update_target(target, selected_event),
        selected_event,
        update_payload,
    )
    if preview["prompt"]:
        change_request["stage"] = "awaiting_update_new_details"
        change_request["update_payload"] = None
        change_request["update_summary"] = None
        replan["change_request"] = change_request
        return build_prompt_update(ctx, replan, str(preview["prompt"]))

    change_request["update_payload"] = update_payload
    change_request["update_summary"] = str(preview["summary"] or "").strip()
    change_request["stage"] = "awaiting_update_apply_confirmation"
    replan["change_request"] = change_request
    return build_prompt_update(
        ctx,
        replan,
        build_final_update_confirmation_prompt(selected_event, str(preview["summary"] or "").strip()),
    )


def _queue_update_all_apply_confirmation(
    state: AgentState,
    target: str,
    selected_events: list[Event],
    update_payload: str,
    change_request: dict,
    replan: dict,
    ctx: ReplanTurnContext,
) -> dict:
    preview = preview_update_payload_for_all(state, target, selected_events, update_payload)
    if preview["prompt"]:
        change_request["stage"] = "awaiting_update_all_details"
        change_request["update_payload"] = None
        change_request["update_summary"] = None
        replan["change_request"] = change_request
        return build_prompt_update(ctx, replan, str(preview["prompt"]))

    change_request["selected_event_ids"] = [str(event.get("id")) for event in selected_events]
    change_request["update_payload"] = update_payload
    change_request["update_summary"] = str(preview["summary"] or "").strip()
    change_request["stage"] = "awaiting_update_apply_confirmation"
    replan["change_request"] = change_request
    return build_prompt_update(
        ctx,
        replan,
        build_final_update_all_confirmation_prompt(selected_events, str(preview["summary"] or "").strip()),
    )


def preview_update_payload(
    state: AgentState,
    target: str,
    selected_event: Event | dict | None,
    update_payload: str,
) -> dict[str, str | None]:
    if not selected_event:
        return {
            "prompt": build_available_update_reference_prompt(target, candidate_events_for_target(state, target)),
            "summary": None,
        }
    if target in {"academico", "laboral"}:
        parsed = parse_updated_schedule_payload(
            target=target,
            update_payload=update_payload,
            selected_event=selected_event,
            timezone=state.get("timezone", "America/Bogota"),
        )
        if parsed["prompt"]:
            return {"prompt": str(parsed["prompt"]), "summary": None}
        return {
            "prompt": None,
            "summary": format_update_events_summary(list(parsed["events"])),
        }

    extracurricular_items = [ensure_item(item) for item in state.get("extracurricular", [])]
    target_item_index = find_extracurricular_item_index(extracurricular_items, selected_event)
    if target_item_index is None:
        return {
            "prompt": build_available_update_reference_prompt(target, candidate_events_for_target(state, target)),
            "summary": None,
        }

    target_item = extracurricular_items[target_item_index]
    normalized_details = strip_change_intent(update_payload, target_item.nombre)
    item, missing = parse_extracurricular_text(
        normalized_details,
        expected_is_variable=target_item.es_variable,
    )
    missing = [field for field in missing if field != "nombre"]
    if missing:
        return {
            "prompt": (
                f"{PROMPT_EXTRAS}\nActividad a cambiar: {target_item.nombre}.\n"
                "Faltan: " + ", ".join(missing) + "."
            ),
            "summary": None,
        }

    updated_name = target_item.nombre
    if has_explicit_activity_name(update_payload):
        updated_name = item.nombre or target_item.nombre
    updated_item = (
        item.model_copy(update={"nombre": updated_name})
        if hasattr(item, "model_copy")
        else item.copy(update={"nombre": updated_name})
    )
    return {"prompt": None, "summary": format_extracurricular_update_summary(updated_item)}


def preview_update_payload_for_all(
    state: AgentState,
    target: str,
    selected_events: list[Event],
    update_payload: str,
) -> dict[str, str | None]:
    if not selected_events:
        return {"prompt": "No encontre las actividades seleccionadas.", "summary": None}
    return preview_update_payload(
        state,
        effective_update_target(target, selected_events[0]),
        selected_events[0],
        update_payload,
    )


def build_initial_update_reference_prompt(target: str) -> str:
    if target == "academico":
        return "Que actividad academica deseas modificar?"
    if target == "laboral":
        return "Que actividad laboral deseas modificar?"
    if target == "activity_lookup":
        return "Que actividad deseas modificar?"
    return "Que actividad extracurricular deseas modificar?"


def build_available_update_reference_prompt(
    target: str,
    events: list[Event],
    requested_name: str = "",
) -> str:
    target_label = {
        "academico": "academica",
        "laboral": "laboral",
        "extracurricular": "extracurricular",
    }.get(target, "registrada")
    if not events:
        return (
            "No encontre la actividad indicada. "
            f"No hay actividades de tipo {target_label} registradas."
        )

    requested = str(requested_name or "").strip()
    intro = "No pude identificar con claridad la actividad que deseas modificar."
    if requested:
        intro = f"No encontre una coincidencia clara para '{requested}'."
    return (
        f"{intro} Vuelve a escribirla indicando nombre, dia o horario.\n"
        "Estas son las actividades registradas:\n"
        f"{build_match_table(events)}"
    )


def effective_update_target(target: str, event: Event | dict | None) -> str:
    if target != "activity_lookup":
        return target
    return str(event.get("categoria") or "") if event else "extracurricular"


def build_update_name_only_prompt(event: Event | dict | None) -> str:
    activity_name = str(event.get("titulo") or "la actividad") if event else "la actividad"
    return (
        f"Encontre la actividad '{activity_name}'.\n"
        "Indica que dias y horarios deseas modificar."
    )


def build_update_all_details_prompt(events: list[Event]) -> str:
    activity_name = str(events[0].get("titulo") or "la actividad") if events else "la actividad"
    return (
        f"Encontre varias actividades llamadas '{activity_name}'.\n"
        "Indica los nuevos dias y horarios que deseas aplicar a todas."
    )


def build_not_found_update_prompt(target: str, events: list[Event], requested_name: str) -> str:
    base = (
        "No encontre ninguna actividad con ese nombre en tu horario.\n"
        "Por favor verifica el nombre de la actividad."
    )
    if not events:
        return base
    suggestions = suggest_similar_titles(events, requested_name)
    if suggestions:
        return (
            f"{base}\n"
            "Actividades parecidas en tu horario:\n"
            + "\n".join(f"- {title}" for title in suggestions)
        )
    return f"{base}\nEstas son las actividades registradas:\n{build_match_table(events)}"


def reference_is_name_only(reference_text: str, event: Event | dict | None) -> bool:
    if not event:
        return False
    return normalize_text(reference_text) == normalize_text(str(event.get("titulo") or ""))


def format_update_events_summary(events: list[Event]) -> str:
    if not events:
        return "Sin cambios."
    lines = []
    for event in events:
        line = f"- {event.get('dia')} {event.get('inicio')}-{event.get('fin')}"
        title = str(event.get("titulo") or "").strip()
        if title:
            line = f"{line} {title}"
        lines.append(line)
    return "\n".join(lines)


def _apply_selected_academic_update(
    state: AgentState,
    selected_event: Event | dict,
    update_payload: str,
    replan: dict,
    ctx: ReplanTurnContext,
) -> dict:
    parsed = parse_updated_schedule_payload(
        target="academico",
        update_payload=update_payload,
        selected_event=selected_event,
        timezone=state.get("timezone", "America/Bogota"),
    )
    if parsed["prompt"]:
        change_request = dict(replan.get("change_request") or {})
        change_request["stage"] = "awaiting_update_new_details"
        replan["change_request"] = change_request
        return build_prompt_update(ctx, replan, str(parsed["prompt"]))

    schedule_state = ensure_schedule_flow_state(state.get("schedule", {}))
    old_block_id = event_block_id(selected_event)
    remaining_blocks = [b for b in schedule_state.blocks if b.block_id != old_block_id]
    new_blocks = events_to_schedule_blocks(list(parsed["events"]), "academic")
    updated_blocks = remaining_blocks + new_blocks

    updated_academic_events = blocks_to_schedule_events(
        [b for b in updated_blocks if b.block_type == "academic"]
    )
    raw_inputs = dict(state.get("raw_inputs", {}))
    raw_inputs["horario_academico_text"] = serialize_events_for_category(updated_academic_events, "academico")

    clear_replan_change_request(replan)
    updated_schedule = schedule_state.model_copy(update={"blocks": updated_blocks})
    return build_validate_update(
        ctx,
        replan=replan,
        awaiting_user_input=False,
        schedule=schedule_flow_state_to_update(updated_schedule),
        events=events_for_scheduling_update(
            state,
            schedule=updated_schedule,
            exclude_event_ids=[str(selected_event.get("id") or "")],
        ),
        errors=list(state.get("errors", [])),
        raw_inputs=raw_inputs,
    )


def _apply_selected_laboral_update(
    state: AgentState,
    selected_event: Event | dict,
    update_payload: str,
    replan: dict,
    ctx: ReplanTurnContext,
) -> dict:
    parsed = parse_updated_schedule_payload(
        target="laboral",
        update_payload=update_payload,
        selected_event=selected_event,
        timezone=state.get("timezone", "America/Bogota"),
    )
    if parsed["prompt"]:
        change_request = dict(replan.get("change_request") or {})
        change_request["stage"] = "awaiting_update_new_details"
        replan["change_request"] = change_request
        return build_prompt_update(ctx, replan, str(parsed["prompt"]))

    schedule_state = ensure_schedule_flow_state(state.get("schedule", {}))
    old_block_id = event_block_id(selected_event)
    remaining_blocks = [b for b in schedule_state.blocks if b.block_id != old_block_id]
    new_blocks = events_to_schedule_blocks(list(parsed["events"]), "work")
    updated_blocks = remaining_blocks + new_blocks

    updated_work_events = blocks_to_schedule_events(
        [b for b in updated_blocks if b.block_type == "work"]
    )
    raw_inputs = dict(state.get("raw_inputs", {}))
    raw_inputs["horario_laboral_text"] = serialize_events_for_category(updated_work_events, "laboral")

    clear_replan_change_request(replan)
    updated_schedule = schedule_state.model_copy(update={"blocks": updated_blocks})
    return build_validate_update(
        ctx,
        replan=replan,
        awaiting_user_input=False,
        schedule=schedule_flow_state_to_update(updated_schedule),
        events=events_for_scheduling_update(
            state,
            schedule=updated_schedule,
            exclude_event_ids=[str(selected_event.get("id") or "")],
        ),
        errors=list(state.get("errors", [])),
        raw_inputs=raw_inputs,
    )


def _apply_selected_academic_update_all(
    state: AgentState,
    selected_events: list[Event],
    update_payload: str,
    replan: dict,
    ctx: ReplanTurnContext,
) -> dict:
    parsed = parse_updated_schedule_payload(
        target="academico",
        update_payload=update_payload,
        selected_event=selected_events[0],
        timezone=state.get("timezone", "America/Bogota"),
    )
    if parsed["prompt"]:
        change_request = dict(replan.get("change_request") or {})
        change_request["stage"] = "awaiting_update_all_details"
        replan["change_request"] = change_request
        return build_prompt_update(ctx, replan, str(parsed["prompt"]))

    schedule_state = ensure_schedule_flow_state(state.get("schedule", {}))
    old_block_ids = {event_block_id(e) for e in selected_events} - {None}
    remaining_blocks = [b for b in schedule_state.blocks if b.block_id not in old_block_ids]
    new_blocks = events_to_schedule_blocks(list(parsed["events"]), "academic")
    updated_blocks = remaining_blocks + new_blocks

    updated_academic_events = blocks_to_schedule_events(
        [b for b in updated_blocks if b.block_type == "academic"]
    )
    raw_inputs = dict(state.get("raw_inputs", {}))
    raw_inputs["horario_academico_text"] = serialize_events_for_category(updated_academic_events, "academico")

    clear_replan_change_request(replan)
    updated_schedule = schedule_state.model_copy(update={"blocks": updated_blocks})
    return build_validate_update(
        ctx,
        replan=replan,
        awaiting_user_input=False,
        schedule=schedule_flow_state_to_update(updated_schedule),
        events=events_for_scheduling_update(
            state,
            schedule=updated_schedule,
            exclude_event_ids=[str(event.get("id") or "") for event in selected_events],
        ),
        errors=list(state.get("errors", [])),
        raw_inputs=raw_inputs,
    )


def _apply_selected_laboral_update_all(
    state: AgentState,
    selected_events: list[Event],
    update_payload: str,
    replan: dict,
    ctx: ReplanTurnContext,
) -> dict:
    parsed = parse_updated_schedule_payload(
        target="laboral",
        update_payload=update_payload,
        selected_event=selected_events[0],
        timezone=state.get("timezone", "America/Bogota"),
    )
    if parsed["prompt"]:
        change_request = dict(replan.get("change_request") or {})
        change_request["stage"] = "awaiting_update_all_details"
        replan["change_request"] = change_request
        return build_prompt_update(ctx, replan, str(parsed["prompt"]))

    schedule_state = ensure_schedule_flow_state(state.get("schedule", {}))
    old_block_ids = {event_block_id(e) for e in selected_events} - {None}
    remaining_blocks = [b for b in schedule_state.blocks if b.block_id not in old_block_ids]
    new_blocks = events_to_schedule_blocks(list(parsed["events"]), "work")
    updated_blocks = remaining_blocks + new_blocks

    updated_work_events = blocks_to_schedule_events(
        [b for b in updated_blocks if b.block_type == "work"]
    )
    raw_inputs = dict(state.get("raw_inputs", {}))
    raw_inputs["horario_laboral_text"] = serialize_events_for_category(updated_work_events, "laboral")

    clear_replan_change_request(replan)
    updated_schedule = schedule_state.model_copy(update={"blocks": updated_blocks})
    return build_validate_update(
        ctx,
        replan=replan,
        awaiting_user_input=False,
        schedule=schedule_flow_state_to_update(updated_schedule),
        events=events_for_scheduling_update(
            state,
            schedule=updated_schedule,
            exclude_event_ids=[str(event.get("id") or "") for event in selected_events],
        ),
        errors=list(state.get("errors", [])),
        raw_inputs=raw_inputs,
    )


def _apply_selected_extracurricular_update(
    state: AgentState,
    selected_event: Event | dict,
    update_payload: str,
    replan: dict,
    ctx: ReplanTurnContext,
) -> dict:
    extracurricular_items = [ensure_item(item) for item in state.get("extracurricular", [])]
    target_item_index = find_extracurricular_item_index(extracurricular_items, selected_event)
    if target_item_index is None:
        return build_prompt_update(
            ctx,
            replan,
            (
                "No pude ubicar la actividad extracurricular seleccionada. "
                "Indica nuevamente cual deseas modificar."
            ),
        )

    target_item = extracurricular_items[target_item_index]
    normalized_details = strip_change_intent(update_payload, target_item.nombre)
    item, missing = parse_extracurricular_text(
        normalized_details,
        expected_is_variable=target_item.es_variable,
    )
    missing = [field for field in missing if field != "nombre"]
    if missing:
        change_request = dict(replan.get("change_request") or {})
        change_request["stage"] = "awaiting_update_new_details"
        replan["change_request"] = change_request
        return build_prompt_update(
            ctx,
            replan,
            (
                f"{PROMPT_EXTRAS}\nActividad a cambiar: {target_item.nombre}.\n"
                "Faltan: " + ", ".join(missing) + "."
            ),
        )

    updated_name = target_item.nombre
    if has_explicit_activity_name(update_payload):
        updated_name = item.nombre or target_item.nombre
    updated_item = (
        item.model_copy(update={"nombre": updated_name})
        if hasattr(item, "model_copy")
        else item.copy(update={"nombre": updated_name})
    )

    errors = list(state.get("errors", []))
    tz = state.get("timezone", "America/Bogota")
    new_tentativo = _validated_extracurricular_events(
        build_events_from_extracurricular_item(updated_item, tz), errors
    )
    updated_item = updated_item.model_copy(update={"tentativo": new_tentativo})
    extracurricular_items[target_item_index] = updated_item

    clear_replan_change_request(replan)
    return build_validate_update(
        ctx,
        replan=replan,
        awaiting_user_input=False,
        extracurricular=extracurricular_items,
        events=events_for_scheduling_update(
            state,
            extracurricular=extracurricular_items,
            exclude_event_ids=[str(selected_event.get("id") or "")],
        ),
        errors=errors,
    )


def parse_updated_schedule_payload(
    target: str,
    update_payload: str,
    selected_event: Event | dict,
    timezone: str,
) -> dict[str, object]:
    text = str(update_payload or "").strip()
    if not text:
        return {"events": [], "prompt": "Indica los nuevos datos de la actividad."}
    try:
        schedule = extract_natural_schedule_components(text)
    except ValueError as exc:
        error_text = str(exc).lower()
        if "no day found" in error_text:
            return {"events": [], "prompt": "Indica los dias exactos para la actividad."}
        if "ambiguous time range" in error_text:
            return {"events": [], "prompt": "Aclara AM o PM en el nuevo horario."}
        return {"events": [], "prompt": "No pude interpretar el nuevo horario de la actividad."}

    title = str(selected_event.get("titulo") or "Actividad")
    if target == "academico" and has_explicit_activity_name(text):
        title = infer_activity_title(text) or title
    if target == "laboral":
        title = "Trabajo"

    return {
        "events": build_events_from_schedule(schedule, title, target, timezone),
        "prompt": None,
    }


def _validated_extracurricular_events(events: list[Event], errors: list[str]) -> list[Event]:
    valid: list[Event] = []
    for event in events:
        try:
            validate_event(event)
        except ValueError as exc:
            errors.append(f"Evento extracurricular invalido: {exc}")
            continue
        valid.append(event)
    return valid


def serialize_events_for_category(events: list[Event], category: str) -> str:
    filtered = [event for event in events if event.get("categoria") == category]
    filtered.sort(key=lambda event: (str(event.get("dia")), str(event.get("inicio"))))
    if category == "laboral":
        return "\n".join(
            f"{event.get('dia')} {event.get('inicio')}-{event.get('fin')}"
            for event in filtered
        )
    return "\n".join(
        f"{event.get('dia')} {event.get('inicio')}-{event.get('fin')} {event.get('titulo')}"
        for event in filtered
    )


__all__ = ["handle_activity_update"]
