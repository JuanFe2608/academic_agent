"""Helpers de parsing y reconstruccion de actividades para replanificacion."""

from __future__ import annotations

import re

from agents.support.nodes.collect_extracurricular_details import parse_extracurricular_text
from agents.support.nodes.utils import normalize_text
from schemas.scheduling import Event, ExtracurricularItem
from services.scheduling.extracurricular_events import build_fixed_events, build_tentative_events
from services.scheduling.text_parser import extract_natural_schedule_components
from services.scheduling.validation import new_event_id, validate_event


_DAY_MARKER_PATTERN = re.compile(
    r"\b(lunes|martes|miercoles|miércoles|jueves|viernes|sabados|sabado|sábado|domingos|domingo|"
    r"lun|mar|mie|jue|vie|sab|dom|todos\s+los\s+dias|todos\s+los\s+días|"
    r"cada\s+dia|cada\s+día|diario|diariamente)\b"
)
_TIME_RANGE_PATTERN = re.compile(
    r"(?:de|desde)?\s*(?:las\s+)?\d{1,2}(?::\d{2})?(?:\s*[ap]\.?\s*m\.?)?"
    r"\s*(?:-|a|hasta)\s*(?:las\s+)?\d{1,2}(?::\d{2})?(?:\s*[ap]\.?\s*m\.?)?",
    re.IGNORECASE,
)
_ACTIVITY_SEPARATOR_PATTERN = re.compile(
    r"(?:\s*,\s*|\s+(?:y|e|ademas|además|tambien|también)\s+)",
    re.IGNORECASE,
)
_ACADEMIC_KEYWORDS = (
    "academica",
    "academico",
    "clase",
    "clases",
    "estudio",
    "estudiar",
    "materia",
    "parcial",
    "parciales",
    "examen",
    "tarea",
    "curso",
)
_WORK_KEYWORDS = (
    "trabajo",
    "trabajar",
    "laboral",
    "turno",
    "empleo",
    "oficina",
)


def ensure_item(item: ExtracurricularItem | dict) -> ExtracurricularItem:
    if isinstance(item, ExtracurricularItem):
        return item
    return ExtracurricularItem(**item)


def build_events_for_new_extracurricular_items(
    items: list[ExtracurricularItem],
    timezone: str,
    errors: list[str],
) -> tuple[list[Event], list[str]]:
    new_events: list[Event] = []
    for item in items:
        generated = build_events_from_extracurricular_item(item, timezone)
        for event in generated:
            try:
                validate_event(event)
            except ValueError as exc:
                errors.append(f"Evento extracurricular invalido: {exc}")
                continue
            new_events.append(event)
    return new_events, errors


def match_extracurricular(
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


def strip_change_intent(details: str, activity_name: str) -> str:
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


def rebuild_extracurricular_events(
    extracurricular_items: list[ExtracurricularItem],
    current_events: list[Event],
    timezone: str,
    errors: list[str],
) -> tuple[list[Event], list[str]]:
    new_events: list[Event] = []
    for item in extracurricular_items:
        generated = build_events_from_extracurricular_item(item, timezone)
        for event in generated:
            try:
                validate_event(event)
            except ValueError as exc:
                errors.append(f"Evento extracurricular invalido: {exc}")
                continue
            new_events.append(event)

    remaining = [event for event in current_events if event.get("categoria") != "extracurricular"]
    return remaining + new_events, errors


def build_events_from_extracurricular_item(item: ExtracurricularItem, timezone: str) -> list[Event]:
    if item.es_variable:
        return build_tentative_events(item, timezone)
    if item.dias and item.hora_inicio and item.hora_fin:
        return [
            Event(
                id=new_event_id(),
                dia=day,
                inicio=item.hora_inicio,
                fin=item.hora_fin,
                titulo=item.nombre,
                tipo="confirmado",
                categoria="extracurricular",
                origen="user_text",
                timezone=timezone,
            )
            for day in item.dias
        ]
    return build_fixed_events(item, timezone)


def find_extracurricular_item_index(
    items: list[ExtracurricularItem],
    event: Event | dict,
) -> int | None:
    event_title = normalize_text(str(event.get("titulo") or ""))
    event_day = normalize_text(str(event.get("dia") or ""))
    event_start = str(event.get("inicio") or "")
    event_end = str(event.get("fin") or "")
    for index, item in enumerate(items):
        if normalize_text(item.nombre) != event_title:
            continue
        if item.hora_inicio and item.hora_fin and item.hora_inicio == event_start and item.hora_fin == event_end:
            if any(normalize_text(day) == event_day for day in item.dias):
                return index
        if not item.dias and not item.hora_inicio and not item.hora_fin:
            return index
    return None


def has_explicit_activity_name(text: str) -> bool:
    inferred = infer_activity_title(text)
    return inferred not in {"", "Actividad", "Y", "E"}


def format_extracurricular_update_summary(item: ExtracurricularItem) -> str:
    days = ", ".join(item.dias) if item.dias else "Sin dias definidos"
    hours = (
        f"{item.hora_inicio}-{item.hora_fin}"
        if item.hora_inicio and item.hora_fin
        else item.detalle or "Sin horario definido"
    )
    return (
        f"- Actividad: {item.nombre}\n"
        f"- Dia(s): {days}\n"
        f"- Horario: {hours}"
    )


def delete_from_extracurricular(
    items: list[ExtracurricularItem],
    deleted_events: list[Event],
) -> list[ExtracurricularItem]:
    if not deleted_events:
        return items
    deleted_by_name: dict[str, set[tuple[str, str, str]]] = {}
    for event in deleted_events:
        deleted_by_name.setdefault(normalize_text(str(event.get("titulo") or "")), set()).add(
            (
                normalize_text(str(event.get("dia") or "")),
                str(event.get("inicio") or ""),
                str(event.get("fin") or ""),
            )
        )

    updated: list[ExtracurricularItem] = []
    for item in items:
        key = normalize_text(item.nombre)
        matches = deleted_by_name.get(key, set())
        if not matches:
            updated.append(item)
            continue
        if item.hora_inicio and item.hora_fin:
            remaining_days = [
                day
                for day in item.dias
                if (normalize_text(day), item.hora_inicio, item.hora_fin) not in matches
            ]
        else:
            remaining_days = [day for day in item.dias if (normalize_text(day), "", "") not in matches]
        if not remaining_days:
            continue
        detail = item.detalle
        if item.hora_inicio and item.hora_fin:
            detail = f"{', '.join(remaining_days)} {item.hora_inicio}-{item.hora_fin}"
        updated_item = (
            item.model_copy(update={"dias": remaining_days, "detalle": detail})
            if hasattr(item, "model_copy")
            else item.copy(update={"dias": remaining_days, "detalle": detail})
        )
        updated.append(updated_item)
    return updated


def parse_activity_additions(text: str, timezone: str) -> dict[str, object]:
    chunks = split_activity_chunks(text)
    if not chunks:
        return {"events": [], "extracurricular": [], "prompt": "Indica la actividad con nombre, dias y horario."}

    events: list[Event] = []
    extracurricular_items: list[ExtracurricularItem] = []
    for chunk in chunks:
        try:
            schedule = extract_natural_schedule_components(chunk)
        except ValueError as exc:
            error_text = str(exc).lower()
            title = infer_activity_title(chunk)
            if "no day found" in error_text:
                return {
                    "events": [],
                    "extracurricular": [],
                    "prompt": f"Indica los dias exactos para la actividad {title}.",
                }
            if "ambiguous time range" in error_text:
                return {
                    "events": [],
                    "extracurricular": [],
                    "prompt": f"Aclara AM o PM para la actividad {title}.",
                }
            return {
                "events": [],
                "extracurricular": [],
                "prompt": f"No pude interpretar el horario de la actividad {title}.",
            }

        category = infer_activity_category(chunk)
        if category == "extracurricular":
            item, missing = parse_extracurricular_text(chunk, expected_is_variable=False)
            if missing:
                return {
                    "events": [],
                    "extracurricular": [],
                    "prompt": build_add_clarification_prompt(missing),
                }
            extracurricular_items.append(item)
            events.extend(build_events_from_extracurricular_item(item, timezone))
            continue

        title = infer_activity_title(chunk)
        chunk_events = build_events_from_schedule(schedule, title, category, timezone)
        events.extend(chunk_events)

    return {"events": events, "extracurricular": extracurricular_items, "prompt": None}


def split_activity_chunks(text: str) -> list[str]:
    raw = str(text or "").strip()
    if not raw:
        return []

    coarse_parts = [part.strip(" ,") for part in re.split(r"[;\n]+", raw) if part.strip(" ,")]
    chunks: list[str] = []
    for part in coarse_parts:
        matches = list(_TIME_RANGE_PATTERN.finditer(part))
        if len(matches) <= 1:
            chunks.append(part)
            continue
        cursor = 0
        for index, match in enumerate(matches[:-1]):
            next_match = matches[index + 1]
            boundary = find_activity_boundary(part, match.end(), next_match.start())
            if boundary is None:
                continue
            chunk_end, next_cursor = boundary
            chunk = part[cursor:chunk_end].strip(" ,")
            if chunk:
                chunks.append(chunk)
            cursor = next_cursor
        tail = part[cursor:].strip(" ,")
        if tail:
            chunks.append(tail)
    return chunks


def find_activity_boundary(text: str, start: int, end: int) -> tuple[int, int] | None:
    between = text[start:end]
    separator = _ACTIVITY_SEPARATOR_PATTERN.search(between)
    if not separator:
        return None
    return start + separator.start(), start + separator.end()


def infer_activity_title(text: str) -> str:
    item, missing = parse_extracurricular_text(text, expected_is_variable=False)
    if item.nombre and "nombre" not in missing:
        return item.nombre

    normalized = normalize_text(text)
    without_time = _TIME_RANGE_PATTERN.sub(" ", normalized)
    without_days = _DAY_MARKER_PATTERN.sub(" ", without_time)
    without_fillers = re.sub(
        r"\b(?:de|desde|hasta|las|actividad|tipo|academica|academico|laboral|extracurricular|"
        r"quiero|anadir|agregar|sumar|incluir|hago|voy|tengo|solo|para|mi|mis|y|e)\b",
        " ",
        without_days,
    )
    words = [word for word in re.findall(r"[a-z]+", without_fillers) if word]
    if not words:
        return "Actividad"
    return " ".join(words[:4]).title()


def infer_activity_category(text: str) -> str:
    normalized = normalize_text(text)
    if any(token in normalized for token in _WORK_KEYWORDS):
        return "laboral"
    if any(token in normalized for token in _ACADEMIC_KEYWORDS):
        return "academico"
    return "extracurricular"


def build_events_from_schedule(
    schedule: dict[str, object],
    title: str,
    category: str,
    timezone: str,
) -> list[Event]:
    events: list[Event] = []
    start = str(schedule["start"])
    end = str(schedule["end"])
    overnight = bool(schedule.get("overnight"))
    for day in list(schedule["days"]):
        if not overnight:
            events.append(
                Event(
                    id=new_event_id(),
                    dia=day,
                    inicio=start,
                    fin=end,
                    titulo=title,
                    tipo="confirmado",
                    categoria=category,
                    origen="user_text",
                    timezone=timezone,
                )
            )
            continue
        events.append(
            Event(
                id=new_event_id(),
                dia=day,
                inicio=start,
                fin="23:59",
                titulo=title,
                tipo="confirmado",
                categoria=category,
                origen="user_text",
                timezone=timezone,
            )
        )
        if end != "00:00":
            events.append(
                Event(
                    id=new_event_id(),
                    dia=next_day(day),
                    inicio="00:00",
                    fin=end,
                    titulo=title,
                    tipo="confirmado",
                    categoria=category,
                    origen="user_text",
                    timezone=timezone,
                )
            )
    return events


def next_day(day: str) -> str:
    order = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"]
    return order[(order.index(day) + 1) % len(order)]


def build_add_clarification_prompt(missing: list[str]) -> str:
    if any("aclarar am o pm" in field.lower() for field in missing):
        return "Aclara AM o PM para las actividades que deseas anadir."
    if any("horario con dias y horas" in field.lower() for field in missing):
        return "Indica el nombre, los dias exactos y el horario de cada actividad que deseas anadir."
    return "Necesito un poco mas de detalle para anadir esas actividades: " + ", ".join(missing) + "."


def extract_activity_name_from_delete_text(details: str) -> str:
    normalized = normalize_text(details)
    if not normalized:
        return ""
    match = re.search(
        r"(?:eliminar|borrar|quitar)\s+(?:la\s+actividad\s+)?(?:de\s+)?([a-z\s]+)",
        normalized,
    )
    if match:
        candidate = match.group(1)
        candidate = _DAY_MARKER_PATTERN.split(candidate)[0]
        candidate = _TIME_RANGE_PATTERN.split(candidate)[0]
        cleaned = re.sub(r"\b(?:el|la|los|las|de)\b", " ", candidate)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.:;")
        if cleaned:
            return cleaned.title()
    return ""


__all__ = [
    "build_add_clarification_prompt",
    "build_events_for_new_extracurricular_items",
    "build_events_from_extracurricular_item",
    "build_events_from_schedule",
    "delete_from_extracurricular",
    "ensure_item",
    "extract_activity_name_from_delete_text",
    "find_extracurricular_item_index",
    "format_extracurricular_update_summary",
    "has_explicit_activity_name",
    "infer_activity_title",
    "match_extracurricular",
    "parse_activity_additions",
    "rebuild_extracurricular_events",
    "strip_change_intent",
]
