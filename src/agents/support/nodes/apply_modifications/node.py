"""Nodo para aplicar modificaciones solicitadas por el usuario."""

from __future__ import annotations

import re

from agents.support.nodes.collect_extracurricular_details import parse_extracurricular_text
from agents.support.nodes.generate_tentative_extracurricular.node import (
    build_fixed_events,
    build_tentative_events,
)
from agents.support.nodes.utils import (
    append_message,
    detect_new_input,
    has_time_range,
    normalize_text,
    parse_yes_no,
)
from agents.support.state import AgentState, Event, ExtracurricularItem, validate_event
from agents.support.tools.schedule_parser import parse_academic_schedule_text, parse_work_schedule_text

from .prompt import PROMPT_EXTRAS, PROMPT_HORARIO, PROMPT_HORARIO_ACADEMICO


def apply_modifications(state: AgentState) -> dict:
    """Aplica cambios a horarios laborales o extracurriculares."""
    messages = state.get("messages", [])
    has_new_input, last_text, current_count = detect_new_input(
        messages,
        state.get("user_message_count", 0),
        state.get("awaiting_user_input", False),
        state.get("last_user_text"),
    )
    last_user_text_value = last_text if has_new_input else state.get("last_user_text")
    replan = dict(state.get("replan", {}))
    change_request = replan.get("change_request") or {}

    target = change_request.get("target")
    operation = str(change_request.get("operation") or "update").strip().lower()
    activity_name = str(change_request.get("activity_name") or "").strip()
    details = (change_request.get("details") or "").strip() or (last_text if has_new_input else "")

    if target == "delete":
        return _apply_delete_change(
            state, details, replan, current_count, has_new_input, last_user_text_value
        )
    if target == "horario":
        replan["pending_prompt"] = "Aclara si deseas cambiar el horario academico o el laboral. Usa la tabla anterior como referencia."
        return {
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }
    if target == "laboral":
        return _apply_laboral_change(
            state, details, operation, replan, current_count, has_new_input, last_user_text_value
        )
    if target == "academico":
        return _apply_academic_change(
            state, details, operation, replan, current_count, has_new_input, last_user_text_value
        )
    if target == "extracurricular":
        return _apply_extracurricular_change(
            state,
            details,
            operation,
            activity_name,
            replan,
            current_count,
            has_new_input,
            last_user_text_value,
        )

    return {
        "messages": append_message(
            messages,
            "assistant",
            "Por ahora solo puedo modificar horario o actividades extracurriculares.",
        ),
        "phase": "validate",
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_user_text_value,
        "awaiting_user_input": True,
    }


def _apply_laboral_change(
    state: AgentState,
    details: str,
    operation: str,
    replan: dict,
    current_count: int,
    has_new_input: bool,
    last_user_text_value: str | None,
) -> dict:
    messages = state.get("messages", [])
    if not details or not has_time_range(details):
        replan["pending_prompt"] = PROMPT_HORARIO
        return {
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }

    errors = list(state.get("errors", []))
    try:
        parsed = parse_work_schedule_text(details, state.get("timezone", "America/Bogota"))
    except ValueError as exc:
        errors.append(f"Horario laboral invalido: {exc}")
        replan["pending_prompt"] = PROMPT_HORARIO
        return {
            "errors": errors,
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }

    new_events: list[Event] = []
    for event in parsed:
        try:
            validate_event(event)
        except ValueError as exc:
            errors.append(f"Evento laboral invalido: {exc}")
            continue
        new_events.append(event)

    if operation == "add":
        updated_events = list(state.get("events", [])) + new_events
    else:
        remaining = [event for event in state.get("events", []) if event.get("categoria") != "laboral"]
        updated_events = remaining + new_events

    raw_inputs = dict(state.get("raw_inputs", {}))
    raw_inputs["horario_laboral_text"] = details

    replan["change_request"] = None
    replan["pending_prompt"] = None
    return {
        "events": updated_events,
        "errors": errors,
        "raw_inputs": raw_inputs,
        "replan": replan,
        "phase": "validate",
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_user_text_value,
        "awaiting_user_input": False,
    }


def _apply_academic_change(
    state: AgentState,
    details: str,
    operation: str,
    replan: dict,
    current_count: int,
    has_new_input: bool,
    last_user_text_value: str | None,
) -> dict:
    messages = state.get("messages", [])
    if not details or not has_time_range(details):
        replan["pending_prompt"] = PROMPT_HORARIO_ACADEMICO
        return {
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }

    errors = list(state.get("errors", []))
    try:
        parsed = parse_academic_schedule_text(details, state.get("timezone", "America/Bogota"))
    except ValueError as exc:
        errors.append(f"Horario academico invalido: {exc}")
        replan["pending_prompt"] = PROMPT_HORARIO_ACADEMICO
        return {
            "errors": errors,
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }

    new_events: list[Event] = []
    for event in parsed:
        try:
            validate_event(event)
        except ValueError as exc:
            errors.append(f"Evento academico invalido: {exc}")
            continue
        new_events.append(event)

    if operation == "add":
        updated_events = list(state.get("events", [])) + new_events
    else:
        remaining = [event for event in state.get("events", []) if event.get("categoria") != "academico"]
        updated_events = remaining + new_events

    raw_inputs = dict(state.get("raw_inputs", {}))
    raw_inputs["horario_academico_text"] = details

    replan["change_request"] = None
    replan["pending_prompt"] = None
    return {
        "events": updated_events,
        "errors": errors,
        "raw_inputs": raw_inputs,
        "replan": replan,
        "phase": "validate",
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_user_text_value,
        "awaiting_user_input": False,
    }


def _apply_extracurricular_change(
    state: AgentState,
    details: str,
    operation: str,
    activity_name: str,
    replan: dict,
    current_count: int,
    has_new_input: bool,
    last_user_text_value: str | None,
) -> dict:
    extracurricular_items = [_ensure_item(item) for item in state.get("extracurricular", [])]
    if not extracurricular_items:
        replan["pending_prompt"] = "No hay actividades extracurriculares registradas para modificar."
        return {
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }

    target_item = _match_extracurricular(activity_name, extracurricular_items)
    if operation == "add":
        target_item = None
    if not target_item and activity_name and operation != "add":
        disponibles = ", ".join(item.nombre for item in extracurricular_items)
        replan["pending_prompt"] = (
            f"La actividad '{activity_name}' no existe. "
            f"Actividades disponibles: {disponibles}. Usa la tabla anterior como referencia."
        )
        return {
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }
    if not target_item and len(extracurricular_items) == 1 and operation != "add":
        target_item = extracurricular_items[0]
    if not target_item and operation != "add":
        disponibles = ", ".join(item.nombre for item in extracurricular_items)
        replan["pending_prompt"] = (
            f"Indica que actividad quieres modificar. "
            f"Actividades disponibles: {disponibles}. Usa la tabla anterior como referencia."
        )
        return {
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }

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
        replan["change_request"] = None
        replan["pending_prompt"] = None
        return {
            "events": updated_events,
            "errors": list(state.get("errors", [])),
            "extracurricular": updated_extracurricular,
            "replan": replan,
            "phase": "validate",
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": False,
        }

    if not details:
        replan["pending_prompt"] = f"{PROMPT_EXTRAS}\nActividad actual: {target_item.nombre}."
        return {
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }

    reference_name = target_item.nombre if target_item else ""
    normalized_details = _strip_change_intent(details, reference_name)
    item, missing = parse_extracurricular_text(
        normalized_details,
        expected_is_variable=target_item.es_variable if target_item else None,
    )
    missing = [field for field in missing if field != "nombre"]
    if missing:
        replan["pending_prompt"] = (
            f"{PROMPT_EXTRAS}\nActividad a cambiar: {reference_name or 'nueva actividad'}.\n"
            "Faltan: " + ", ".join(missing) + "."
        )
        return {
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }

    if operation == "add":
        updated_item = item
        updated_extracurricular = extracurricular_items + [updated_item]
    else:
        updated_item = item.model_copy(update={"nombre": target_item.nombre}) if hasattr(item, "model_copy") else item.copy(update={"nombre": target_item.nombre})
        updated_extracurricular = [
            updated_item if normalize_text(existing.nombre) == normalize_text(target_item.nombre) else existing
            for existing in extracurricular_items
        ]
    updated_events, errors = _rebuild_extracurricular_events(
        updated_extracurricular,
        state.get("events", []),
        state.get("timezone", "America/Bogota"),
        list(state.get("errors", [])),
    )

    replan["change_request"] = None
    replan["pending_prompt"] = None
    return {
        "events": updated_events,
        "errors": errors,
        "extracurricular": updated_extracurricular,
        "replan": replan,
        "phase": "validate",
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_user_text_value,
        "awaiting_user_input": False,
    }


def _ensure_item(item: ExtracurricularItem | dict) -> ExtracurricularItem:
    if isinstance(item, ExtracurricularItem):
        return item
    return ExtracurricularItem(**item)


def _match_extracurricular(
    activity_name: str,
    items: list[ExtracurricularItem],
) -> ExtracurricularItem | None:
    normalized_name = normalize_text(activity_name)
    if not normalized_name:
        return None
    for item in items:
        item_name = normalize_text(item.nombre)
        if normalized_name == item_name or normalized_name in item_name or item_name in normalized_name:
            return item
    return None


def _strip_change_intent(details: str, activity_name: str) -> str:
    text = str(details or "").strip()
    if not text:
        return ""
    lowered = normalize_text(text)
    if activity_name:
        pattern = re.compile(re.escape(normalize_text(activity_name)))
        lowered = pattern.sub("", lowered)
    lowered = re.sub(
        r"\b(?:quiero|necesito|por favor|cambiar|modificar|ajustar|la|el|actividad|de|extracurricular|horario)\b",
        " ",
        lowered,
    )
    lowered = re.sub(r"\s+", " ", lowered).strip(" ,.:;")
    return lowered or text


def _rebuild_extracurricular_events(
    extracurricular_items: list[ExtracurricularItem],
    current_events: list[Event],
    timezone: str,
    errors: list[str],
) -> tuple[list[Event], list[str]]:
    new_events: list[Event] = []
    for item in extracurricular_items:
        generated = (
            build_tentative_events(item, timezone)
            if item.es_variable
            else build_fixed_events(item, timezone)
        )
        for event in generated:
            try:
                validate_event(event)
            except ValueError as exc:
                errors.append(f"Evento extracurricular invalido: {exc}")
                continue
            new_events.append(event)

    remaining = [event for event in current_events if event.get("categoria") != "extracurricular"]
    return remaining + new_events, errors


def _apply_delete_change(
    state: AgentState,
    details: str,
    replan: dict,
    current_count: int,
    has_new_input: bool,
    last_user_text_value: str | None,
) -> dict:
    change_request = dict(replan.get("change_request") or {})
    stage = str(change_request.get("stage") or "")
    candidate_ids = list(change_request.get("candidate_event_ids") or [])

    if stage == "awaiting_delete_confirmation":
        answer = parse_yes_no(details)
        if answer is None:
            replan["pending_prompt"] = str(replan.get("pending_prompt") or "Responde si o no para confirmar la eliminacion.")
            return {
                "phase": "validate",
                "replan": replan,
                "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
                "last_user_text": last_user_text_value,
                "awaiting_user_input": True,
            }
        if answer is False:
            replan["change_request"] = None
            replan["pending_prompt"] = None
            return {
                "phase": "validate",
                "replan": replan,
                "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
                "last_user_text": last_user_text_value,
                "awaiting_user_input": False,
            }
        return _delete_selected_events(
            state,
            candidate_ids,
            replan,
            current_count,
            has_new_input,
            last_user_text_value,
        )

    events = [event for event in state.get("events", [])]
    matches = _find_delete_matches(events, details)
    if not matches:
        disponibles = ", ".join(sorted({str(event.get("titulo") or "") for event in events if event.get("titulo")}))
        replan["pending_prompt"] = (
            f"No encontre la actividad indicada. Actividades disponibles: {disponibles}."
        )
        return {
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }

    if len(matches) > 1 and "todas" not in normalize_text(details) and not _has_day_or_time_hint(details):
        table = _build_match_table(matches)
        activity_name = str(matches[0].get("titulo") or "")
        change_request["stage"] = "awaiting_identifier"
        change_request["details"] = details
        replan["change_request"] = change_request
        replan["pending_prompt"] = (
            f"Encontre varias coincidencias para '{activity_name}'.\n{table}\n"
            "Indica si deseas eliminar una de un dia y hora especificos, o responde 'todas' para eliminarlas todas."
        )
        return {
            "phase": "validate",
            "replan": replan,
            "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
            "last_user_text": last_user_text_value,
            "awaiting_user_input": True,
        }

    selected_ids = [str(event.get("id")) for event in matches]
    change_request["candidate_event_ids"] = selected_ids
    change_request["stage"] = "awaiting_delete_confirmation"
    replan["change_request"] = change_request
    replan["pending_prompt"] = _build_delete_confirmation_prompt(matches)
    return {
        "phase": "validate",
        "replan": replan,
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_user_text_value,
        "awaiting_user_input": True,
    }


def _delete_selected_events(
    state: AgentState,
    candidate_ids: list[str],
    replan: dict,
    current_count: int,
    has_new_input: bool,
    last_user_text_value: str | None,
) -> dict:
    id_set = set(candidate_ids)
    selected_events = [event for event in state.get("events", []) if str(event.get("id")) in id_set]
    updated_events = [event for event in state.get("events", []) if str(event.get("id")) not in id_set]
    updated_extracurricular = _delete_from_extracurricular(
        [_ensure_item(item) for item in state.get("extracurricular", [])],
        selected_events,
    )
    replan["change_request"] = None
    replan["pending_prompt"] = None
    return {
        "events": updated_events,
        "extracurricular": updated_extracurricular,
        "errors": list(state.get("errors", [])),
        "replan": replan,
        "phase": "validate",
        "user_message_count": current_count if has_new_input else state.get("user_message_count", 0),
        "last_user_text": last_user_text_value,
        "awaiting_user_input": False,
    }


def _find_delete_matches(events: list[Event], details: str) -> list[Event]:
    normalized = normalize_text(details)
    hinted_day = _extract_day_hint(normalized)
    hinted_time = _extract_time_hint(normalized)

    unique_titles = {str(event.get("titulo") or "").strip() for event in events if str(event.get("titulo") or "").strip()}
    title = ""
    for candidate in unique_titles:
        candidate_normalized = normalize_text(candidate)
        if candidate_normalized and candidate_normalized in normalized:
            title = candidate
            break
    if not title and details.strip():
        title = details.strip()

    matches = []
    for event in events:
        event_title = str(event.get("titulo") or "").strip()
        if not event_title:
            continue
        event_normalized = normalize_text(event_title)
        if title and not (
            normalize_text(title) == event_normalized
            or normalize_text(title) in event_normalized
            or event_normalized in normalize_text(title)
        ):
            continue
        if hinted_day and normalize_text(str(event.get("dia") or "")) != hinted_day:
            continue
        if hinted_time and hinted_time not in f"{event.get('inicio')}-{event.get('fin')}":
            continue
        matches.append(event)
    return matches


def _extract_day_hint(normalized: str) -> str:
    for day in ("lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"):
        if day in normalized:
            return day
    return ""


def _extract_time_hint(details: str) -> str:
    match = re.search(r"\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}", details)
    return match.group(0).replace(" ", "") if match else ""


def _has_day_or_time_hint(details: str) -> bool:
    normalized = normalize_text(details)
    return bool(_extract_day_hint(normalized) or _extract_time_hint(details))


def _build_match_table(matches: list[Event]) -> str:
    rows = [
        (str(event.get("dia") or ""), str(event.get("titulo") or ""), f"{event.get('inicio')}-{event.get('fin')}")
        for event in matches
    ]
    day_width = max(len("Dia"), *(len(row[0]) for row in rows))
    title_width = max(len("Actividad"), *(len(row[1]) for row in rows))
    hour_width = max(len("Hora"), *(len(row[2]) for row in rows))
    separator = "+" + "-" * (day_width + 2) + "+" + "-" * (title_width + 2) + "+" + "-" * (hour_width + 2) + "+"
    lines = [
        separator,
        f"| {'Dia'.ljust(day_width)} | {'Actividad'.ljust(title_width)} | {'Hora'.ljust(hour_width)} |",
        separator,
    ]
    for row in rows:
        lines.append(
            f"| {row[0].ljust(day_width)} | {row[1].ljust(title_width)} | {row[2].ljust(hour_width)} |"
        )
        lines.append(separator)
    return "\n".join(lines)


def _build_delete_confirmation_prompt(matches: list[Event]) -> str:
    if len(matches) == 1:
        event = matches[0]
        return (
            f"Esta seguro que quiere eliminar esta actividad el dia {event.get('dia')} "
            f"de {event.get('inicio')} a {event.get('fin')}? Responde si o no."
        )
    table = _build_match_table(matches)
    return f"Esta seguro que quiere eliminar estas actividades?\n{table}\nResponde si o no."


def _delete_from_extracurricular(
    items: list[ExtracurricularItem],
    deleted_events: list[Event],
) -> list[ExtracurricularItem]:
    if not deleted_events:
        return items
    deleted_by_name: dict[str, list[Event]] = {}
    for event in deleted_events:
        deleted_by_name.setdefault(normalize_text(str(event.get("titulo") or "")), []).append(event)

    updated: list[ExtracurricularItem] = []
    for item in items:
        key = normalize_text(item.nombre)
        matches = deleted_by_name.get(key, [])
        if not matches:
            updated.append(item)
            continue
        deleted_days = {normalize_text(str(event.get("dia") or "")) for event in matches}
        remaining_days = [day for day in item.dias if normalize_text(day) not in deleted_days]
        if not remaining_days:
            continue
        detail = item.detalle
        if item.hora_inicio and item.hora_fin:
            detail = f"{', '.join(remaining_days)} {item.hora_inicio}-{item.hora_fin}"
        updated_item = item.model_copy(update={"dias": remaining_days, "detalle": detail}) if hasattr(item, "model_copy") else item.copy(update={"dias": remaining_days, "detalle": detail})
        updated.append(updated_item)
    return updated
