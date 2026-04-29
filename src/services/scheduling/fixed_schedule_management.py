"""Contratos puros para gestion conversacional del horario fijo."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from schemas.scheduling import Event
from services.scheduling.activity_matching import normalize_text, resolve_best_title_key
from services.scheduling.constants import DAY_LABELS, DAY_ORDER, SPANISH_TO_ENGLISH, ScheduleBlockType
from services.scheduling.event_projection import build_schedule_block_event
from services.scheduling.models import WeeklyScheduleBlock, ensure_weekly_block, new_block_id
from services.scheduling.text_parser import extract_natural_schedule_components
from services.scheduling.validation import normalize_time

FixedScheduleIntent = Literal[
    "view_fixed_schedule",
    "update_fixed_schedule",
    "delete_fixed_schedule_item",
    "add_fixed_schedule_item",
    "unknown",
]

_ADD_VERBS = {
    "agregar",
    "agrega",
    "anadir",   # normalize_text strips ñ → añadir
    "anade",    # normalize_text strips ñ → añade
    "incluir",
    "incluye",
    "insertar",
    "inserta",
}
_DELETE_VERBS = {
    "elimina",
    "eliminar",
    "borra",
    "borrar",
    "quita",
    "quitar",
    "saca",
    "sacar",
    "cancelar",
    "cancela",
}
_UPDATE_VERBS = {
    "cambia",
    "cambiar",
    "modifica",
    "modificar",
    "mueve",
    "mover",
    "actualiza",
    "actualizar",
    "ajusta",
    "ajustar",
    "reprograma",
    "reprogramar",
}
_VIEW_TERMS = {
    "ver",
    "mostrar",
    "muestrame",
    "consultar",
    "consulta",
    "como esta",
    "cual es",
}
_WORK_TERMS = {"trabajo", "laboral", "empleo", "turno"}
_ACADEMIC_TERMS = {"clase", "clases", "materia", "academico", "academica", "asignatura"}
_EXTRACURRICULAR_TERMS = {
    "extra",
    "extracurricular",
    "actividad extracurricular",
    "gimnasio",
    "deporte",
    "entreno",
    "entrenamiento",
}
_TYPE_LABELS = {
    "academic": "academico",
    "work": "laboral",
    "extracurricular": "extracurricular",
}
_REFERENCE_PREFIX_PATTERN = re.compile(
    r"^\s*(?:mi\s+)?(?:horario\s+)?(?:fijo\s+)?"
    r"(?:(?:la|el|los|las)\s+)?"
    r"(?:(?:clase|materia|asignatura|actividad|bloque|turno|trabajo)\s+(?:de\s+)?)?",
    re.IGNORECASE,
)
_UPDATE_SPLIT_PATTERN = re.compile(
    r"(?P<reference>.+?)\s+(?:a|para|por)\s+(?P<payload>.+)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FixedScheduleOperation:
    """Operacion de horario fijo detectada desde lenguaje natural."""

    intent: FixedScheduleIntent
    target: ScheduleBlockType | None = None
    reference_text: str = ""
    update_text: str = ""
    apply_to_all: bool = False


@dataclass(frozen=True)
class FixedScheduleMatchResult:
    """Resultado de buscar bloques del horario fijo."""

    matches: list[WeeklyScheduleBlock] = field(default_factory=list)
    available_blocks: list[WeeklyScheduleBlock] = field(default_factory=list)


@dataclass(frozen=True)
class FixedScheduleUpdatePreview:
    """Vista previa pura de una modificacion de bloques."""

    replacement_blocks: list[WeeklyScheduleBlock] = field(default_factory=list)
    prompt: str | None = None


def parse_fixed_schedule_operation(text: str | None) -> FixedScheduleOperation:
    """Detecta intencion, referencia y payload de una solicitud de horario fijo."""

    raw_text = str(text or "").strip()
    normalized = normalize_text(raw_text)
    target = infer_fixed_schedule_target(raw_text)
    apply_to_all = "todas" in normalized or "todos" in normalized

    if not normalized:
        return FixedScheduleOperation(intent="unknown", target=target)

    if _contains_any_token(normalized, _ADD_VERBS):
        reference = _clean_reference_text(_strip_command(raw_text, _ADD_VERBS))
        return FixedScheduleOperation(
            intent="add_fixed_schedule_item",
            target=target,
            reference_text=reference,
            apply_to_all=apply_to_all,
        )

    if _contains_any_token(normalized, _DELETE_VERBS):
        reference = _clean_reference_text(_strip_command(raw_text, _DELETE_VERBS))
        return FixedScheduleOperation(
            intent="delete_fixed_schedule_item",
            target=target,
            reference_text=reference,
            apply_to_all=apply_to_all,
        )

    if _contains_any_token(normalized, _UPDATE_VERBS):
        remainder = _strip_command(raw_text, _UPDATE_VERBS)
        reference, payload = _split_update_reference_and_payload(remainder)
        return FixedScheduleOperation(
            intent="update_fixed_schedule",
            target=target,
            reference_text=_clean_reference_text(reference),
            update_text=payload.strip(),
            apply_to_all=apply_to_all,
        )

    if _looks_like_view_request(normalized):
        return FixedScheduleOperation(intent="view_fixed_schedule", target=target)

    return FixedScheduleOperation(intent="unknown", target=target)


def infer_fixed_schedule_target(text: str | None) -> ScheduleBlockType | None:
    """Infiere la seccion del horario fijo mencionada por el usuario."""

    normalized = normalize_text(str(text or ""))
    if _contains_any_token(normalized, _WORK_TERMS):
        return "work"
    if _contains_any_token(normalized, _ACADEMIC_TERMS):
        return "academic"
    if _contains_any_token(normalized, _EXTRACURRICULAR_TERMS):
        return "extracurricular"
    return None


def build_fixed_schedule_summary(
    blocks: list[WeeklyScheduleBlock] | list[dict],
    *,
    target: ScheduleBlockType | None = None,
) -> str:
    """Construye un resumen conversacional del horario fijo actual."""

    normalized_blocks = [
        ensure_weekly_block(block)
        for block in blocks
        if target is None or ensure_weekly_block(block).block_type == target
    ]
    normalized_blocks.sort(key=_block_sort_key)
    if not normalized_blocks:
        if target:
            return f"No tengo bloques de horario {_TYPE_LABELS[target]} registrados."
        return "No tengo un horario fijo registrado todavia."

    lines = ["Este es tu horario fijo actual:"]
    current_day = ""
    for block in normalized_blocks:
        day_label = DAY_LABELS[block.day_of_week]
        if day_label != current_day:
            lines.append(f"\n{day_label}:")
            current_day = day_label
        lines.append(
            f"- {block.title} ({_TYPE_LABELS[block.block_type]}) "
            f"{block.start_time}-{block.end_time}"
        )
    return "\n".join(lines).strip()


def match_fixed_schedule_blocks(
    blocks: list[WeeklyScheduleBlock] | list[dict],
    reference_text: str,
    *,
    target: ScheduleBlockType | None = None,
) -> FixedScheduleMatchResult:
    """Busca bloques del horario fijo reutilizando matching de actividades."""

    candidates = [
        ensure_weekly_block(block)
        for block in blocks
        if target is None or ensure_weekly_block(block).block_type == target
    ]
    if not reference_text:
        return FixedScheduleMatchResult(matches=[], available_blocks=candidates)

    events = [build_schedule_block_event(block) for block in candidates]
    matched_events = _find_matching_events(events, reference_text)
    matched_ids = {
        str(event.id).replace("schedule-block:", "", 1)
        for event in matched_events
    }
    matches = [block for block in candidates if block.block_id in matched_ids]
    return FixedScheduleMatchResult(matches=matches, available_blocks=candidates)


def select_fixed_schedule_block(
    blocks: list[WeeklyScheduleBlock] | list[dict],
    text: str,
    *,
    target: ScheduleBlockType | None = None,
) -> WeeklyScheduleBlock | None:
    """Selecciona un bloque por numero o por referencia textual."""

    candidates = [
        ensure_weekly_block(block)
        for block in blocks
        if target is None or ensure_weekly_block(block).block_type == target
    ]
    candidates.sort(key=_block_sort_key)
    option = _parse_numbered_option(text)
    if option is not None and 1 <= option <= len(candidates):
        return candidates[option - 1]
    result = match_fixed_schedule_blocks(candidates, text, target=target)
    if len(result.matches) == 1:
        return result.matches[0]
    return None


def build_fixed_schedule_update_preview(
    selected_block: WeeklyScheduleBlock | dict,
    update_text: str,
    *,
    timezone: str = "America/Bogota",
) -> FixedScheduleUpdatePreview:
    """Convierte detalles naturales en bloques reemplazo para confirmacion."""

    block = ensure_weekly_block(selected_block)
    clean_text = str(update_text or "").strip()
    if not clean_text:
        return FixedScheduleUpdatePreview(prompt="Indica el nuevo dia y horario del bloque.")

    try:
        parsed = extract_natural_schedule_components(clean_text)
    except ValueError as exc:
        error_text = str(exc).lower()
        if "no day found" in error_text:
            return FixedScheduleUpdatePreview(prompt="Indica el dia exacto del nuevo horario.")
        if "no time range found" in error_text:
            return FixedScheduleUpdatePreview(prompt="Indica hora de inicio y hora de fin.")
        if "invalid time range" in error_text or "ambiguous time range" in error_text:
            return FixedScheduleUpdatePreview(prompt="Aclara AM o PM en el nuevo horario.")
        return FixedScheduleUpdatePreview(prompt="No pude interpretar el nuevo horario.")

    days = [str(day) for day in parsed.get("days") or []]
    start_time = str(parsed.get("start") or "").strip()
    end_time = str(parsed.get("end") or "").strip()
    if not days or not start_time or not end_time:
        return FixedScheduleUpdatePreview(prompt="Indica dia, hora de inicio y hora de fin.")

    title = _updated_title(clean_text, block)
    replacements: list[WeeklyScheduleBlock] = []
    for index, spanish_day in enumerate(days):
        english_day = SPANISH_TO_ENGLISH.get(spanish_day, SPANISH_TO_ENGLISH.get(spanish_day.title()))
        if english_day is None:
            return FixedScheduleUpdatePreview(prompt="No pude interpretar el dia del nuevo horario.")
        preview = block.model_copy(
            update={
                "block_id": block.block_id if index == 0 else new_block_id(),
                "title": "Trabajo" if block.block_type == "work" else title,
                "day_of_week": english_day,
                "start_time": start_time,
                "end_time": end_time,
                "timezone": timezone or block.timezone,
                "source_text": _build_source_text(
                    block.block_type,
                    title="Trabajo" if block.block_type == "work" else title,
                    day_of_week=english_day,
                    start_time=start_time,
                    end_time=end_time,
                ),
                "has_conflict": False,
                "conflict_accepted": False,
                "user_confirmed": False,
            }
        )
        replacements.append(preview)
    return FixedScheduleUpdatePreview(replacement_blocks=replacements)


_ADD_TITLE_DAY_PATTERN = re.compile(
    r"\b(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bados?|domingos?)\b",
    re.IGNORECASE,
)
_ADD_TITLE_TIME_PATTERN = re.compile(
    r"\b\d{1,2}(?::\d{2})?\s*(?:[ap]\.?\s*m\.?)?\s*(?:-|a|hasta)\s*\d{1,2}(?::\d{2})?\s*(?:[ap]\.?\s*m\.?)?\b",
    re.IGNORECASE,
)
_ADD_TITLE_FILLER = re.compile(
    r"\b(?:el|los|la|las|de|a|para|en|al|del|y|todas?|todos?|fijo|cada|clase|clases|"
    r"materia|asignatura|actividad|extracurricular|acad[eé]mic[ao]|laboral|"
    r"tengo|tienes?|tiene|tenemos|mi|me|lo|le|que|se|con)\b",
    re.IGNORECASE,
)


def _extract_new_block_title(text: str, block_type: ScheduleBlockType) -> str:
    if block_type == "work":
        return "Trabajo"
    stripped = _ADD_TITLE_DAY_PATTERN.sub("", text)
    stripped = _ADD_TITLE_TIME_PATTERN.sub("", stripped)
    stripped = _ADD_TITLE_FILLER.sub("", stripped)
    title = re.sub(r"\s+", " ", stripped).strip(" ,.;:()")
    return title


def build_fixed_schedule_add_preview(
    raw_text: str,
    block_type: ScheduleBlockType,
    *,
    timezone: str = "America/Bogota",
) -> FixedScheduleUpdatePreview:
    """Convierte texto libre en bloques nuevos para confirmar antes de persistir."""
    clean_text = str(raw_text or "").strip()
    if not clean_text:
        return FixedScheduleUpdatePreview(prompt="Indica el nombre, dia y horario del nuevo bloque.")

    try:
        parsed = extract_natural_schedule_components(clean_text)
    except ValueError as exc:
        error_text = str(exc).lower()
        if "no day found" in error_text:
            return FixedScheduleUpdatePreview(prompt="Indica el dia del nuevo bloque.")
        if "no time range found" in error_text:
            return FixedScheduleUpdatePreview(prompt="Indica hora de inicio y hora de fin.")
        if "invalid time range" in error_text or "ambiguous time range" in error_text:
            return FixedScheduleUpdatePreview(prompt="Aclara AM o PM en el horario del nuevo bloque.")
        return FixedScheduleUpdatePreview(prompt="No pude interpretar el nuevo bloque.")

    days = [str(day) for day in parsed.get("days") or []]
    start_time = str(parsed.get("start") or "").strip()
    end_time = str(parsed.get("end") or "").strip()
    if not days or not start_time or not end_time:
        return FixedScheduleUpdatePreview(prompt="Indica dia, hora de inicio y hora de fin del nuevo bloque.")

    title = _extract_new_block_title(clean_text, block_type)
    if not title:
        return FixedScheduleUpdatePreview(prompt="Indica el nombre del nuevo bloque.")

    new_blocks: list[WeeklyScheduleBlock] = []
    for index, spanish_day in enumerate(days):
        english_day = SPANISH_TO_ENGLISH.get(spanish_day, SPANISH_TO_ENGLISH.get(spanish_day.title()))
        if english_day is None:
            return FixedScheduleUpdatePreview(prompt="No pude interpretar el dia del nuevo bloque.")
        new_block = WeeklyScheduleBlock(
            block_id=new_block_id() if index > 0 else new_block_id(),
            block_type=block_type,
            title=title,
            day_of_week=english_day,
            start_time=start_time,
            end_time=end_time,
            timezone=timezone,
            source_text=_build_source_text(
                block_type,
                title=title,
                day_of_week=english_day,
                start_time=start_time,
                end_time=end_time,
            ),
            user_confirmed=False,
        )
        new_blocks.append(new_block)
    return FixedScheduleUpdatePreview(replacement_blocks=new_blocks)


def replace_fixed_schedule_blocks(
    blocks: list[WeeklyScheduleBlock] | list[dict],
    selected_block_ids: list[str],
    replacement_blocks: list[WeeklyScheduleBlock] | list[dict],
) -> list[WeeklyScheduleBlock]:
    """Reemplaza uno o mas bloques del horario fijo."""

    selected = {str(block_id) for block_id in selected_block_ids}
    kept = [
        ensure_weekly_block(block)
        for block in blocks
        if ensure_weekly_block(block).block_id not in selected
    ]
    updated = kept + [ensure_weekly_block(block) for block in replacement_blocks]
    updated.sort(key=_block_sort_key)
    return updated


def delete_fixed_schedule_blocks(
    blocks: list[WeeklyScheduleBlock] | list[dict],
    selected_block_ids: list[str],
) -> list[WeeklyScheduleBlock]:
    """Elimina bloques seleccionados del horario fijo."""

    return replace_fixed_schedule_blocks(blocks, selected_block_ids, [])


def format_fixed_schedule_block_options(
    blocks: list[WeeklyScheduleBlock] | list[dict],
    *,
    target: ScheduleBlockType | None = None,
) -> str:
    """Lista bloques para que el usuario pueda escoger uno."""

    candidates = [
        ensure_weekly_block(block)
        for block in blocks
        if target is None or ensure_weekly_block(block).block_type == target
    ]
    candidates.sort(key=_block_sort_key)
    if not candidates:
        return "No tengo bloques disponibles para esa seccion."
    return "\n".join(_format_numbered_block(index, block) for index, block in enumerate(candidates, start=1))


def format_fixed_schedule_blocks(blocks: list[WeeklyScheduleBlock] | list[dict]) -> str:
    """Formatea una lista corta de bloques sin numeracion."""

    normalized_blocks = [ensure_weekly_block(block) for block in blocks]
    normalized_blocks.sort(key=_block_sort_key)
    return "\n".join(f"- {_format_block(block)}" for block in normalized_blocks)


def _find_matching_events(events: list[Event], reference_text: str) -> list[Event]:
    normalized = normalize_text(reference_text)
    hinted_day = _extract_day_hint(normalized)
    hinted_time = _extract_time_hint(reference_text)
    title_key = resolve_best_title_key(events, normalized)
    if not title_key and not hinted_day and not hinted_time and normalized:
        return []

    matches: list[Event] = []
    for event in events:
        event_title = str(event.get("titulo") or "").strip()
        if not event_title:
            continue
        if title_key and normalize_text(event_title) != title_key:
            continue
        if hinted_day and normalize_text(str(event.get("dia") or "")) != hinted_day:
            continue
        if hinted_time and hinted_time != f"{event.get('inicio')}-{event.get('fin')}":
            continue
        matches.append(event)
    return matches


def _extract_day_hint(normalized: str) -> str:
    aliases = {
        "lunes": "lunes",
        "lun": "lunes",
        "martes": "martes",
        "mar": "martes",
        "miercoles": "miercoles",
        "mie": "miercoles",
        "jueves": "jueves",
        "jue": "jueves",
        "viernes": "viernes",
        "vie": "viernes",
        "sabado": "sabado",
        "sab": "sabado",
        "domingo": "domingo",
        "dom": "domingo",
    }
    for token, canonical in aliases.items():
        if re.search(rf"\b{re.escape(token)}\b", normalized):
            return canonical
    return ""


def _extract_time_hint(text: str) -> str:
    match = re.search(
        r"(\d{1,2}(?::\d{2})?\s*(?:[ap]\.?\s*m\.?)?)\s*(?:-|a|hasta)\s*"
        r"(\d{1,2}(?::\d{2})?\s*(?:[ap]\.?\s*m\.?)?)",
        text,
        re.IGNORECASE,
    )
    if not match:
        return ""
    start_raw = _normalize_meridiem_text(match.group(1))
    end_raw = _normalize_meridiem_text(match.group(2))
    start_has_meridiem = bool(re.search(r"[ap]m$", start_raw))
    end_has_meridiem = bool(re.search(r"[ap]m$", end_raw))
    if start_has_meridiem and not end_has_meridiem:
        end_raw = f"{end_raw}{start_raw[-2:]}"
    elif end_has_meridiem and not start_has_meridiem:
        start_raw = f"{start_raw}{end_raw[-2:]}"
    try:
        if not start_has_meridiem and not end_has_meridiem and ":" not in start_raw and ":" not in end_raw:
            return ""
        return f"{normalize_time(start_raw)}-{normalize_time(end_raw)}"
    except ValueError:
        return ""


def _normalize_meridiem_text(value: str) -> str:
    normalized = normalize_text(value)
    normalized = normalized.replace(".", "")
    normalized = normalized.replace(" ", "")
    normalized = normalized.replace("a m", "am").replace("p m", "pm")
    return normalized


def _split_update_reference_and_payload(text: str) -> tuple[str, str]:
    clean_text = str(text or "").strip()
    match = _UPDATE_SPLIT_PATTERN.search(clean_text)
    if not match:
        return clean_text, ""
    return match.group("reference").strip(), match.group("payload").strip()


def _strip_command(text: str, verbs: set[str]) -> str:
    raw_text = str(text or "").strip()
    if not raw_text:
        return ""
    verb_pattern = "|".join(re.escape(verb) for verb in sorted(verbs, key=len, reverse=True))
    pattern = re.compile(
        rf"^\s*(?:quiero\s+|necesito\s+|por\s+favor\s+)?(?:{verb_pattern})\s+",
        re.IGNORECASE,
    )
    return pattern.sub("", raw_text, count=1).strip()


def _clean_reference_text(text: str) -> str:
    reference = _REFERENCE_PREFIX_PATTERN.sub("", str(text or "").strip(), count=1)
    return reference.strip(" ,.;:")


def _looks_like_view_request(normalized: str) -> bool:
    if "horario" not in normalized and "agenda" not in normalized:
        return False
    return _contains_any_token(normalized, _VIEW_TERMS)


def _contains_any_token(normalized: str, terms: set[str]) -> bool:
    if not normalized:
        return False
    return any(re.search(rf"(?<!\w){re.escape(term)}(?!\w)", normalized) for term in terms)


def _updated_title(update_text: str, selected_block: WeeklyScheduleBlock) -> str:
    if selected_block.block_type == "work":
        return "Trabajo"
    match = re.search(
        r"(?:nombre|se\s+llama|renombrar(?:la|lo)?\s+a)\s+(?P<title>[A-Za-z0-9ÁÉÍÓÚáéíóúÑñ ]+)",
        update_text,
        re.IGNORECASE,
    )
    if match:
        title = match.group("title").strip(" ,.;:")
        if title:
            return title
    return selected_block.title


def _build_source_text(
    block_type: ScheduleBlockType,
    *,
    title: str,
    day_of_week: str,
    start_time: str,
    end_time: str,
) -> str:
    day = DAY_LABELS[day_of_week]
    if block_type == "work":
        return f"{day} {start_time}-{end_time}"
    return f"{day} {start_time}-{end_time} {title}".strip()


def _format_numbered_block(index: int, block: WeeklyScheduleBlock) -> str:
    return f"{index}. {_format_block(block)}"


def _format_block(block: WeeklyScheduleBlock) -> str:
    return (
        f"{block.title} ({_TYPE_LABELS[block.block_type]}) - "
        f"{DAY_LABELS[block.day_of_week]} {block.start_time}-{block.end_time}"
    )


def _parse_numbered_option(text: str | None) -> int | None:
    match = re.match(r"^\s*(?:opcion\s+|la\s+)?(\d+)\b", normalize_text(str(text or "")))
    return int(match.group(1)) if match else None


def _block_sort_key(block: WeeklyScheduleBlock) -> tuple[int, str, str, str]:
    return (
        DAY_ORDER.index(block.day_of_week),
        block.start_time,
        block.block_type,
        block.title.lower(),
    )


__all__ = [
    "FixedScheduleIntent",
    "FixedScheduleMatchResult",
    "FixedScheduleOperation",
    "FixedScheduleUpdatePreview",
    "build_fixed_schedule_add_preview",
    "build_fixed_schedule_summary",
    "build_fixed_schedule_update_preview",
    "delete_fixed_schedule_blocks",
    "format_fixed_schedule_block_options",
    "format_fixed_schedule_blocks",
    "infer_fixed_schedule_target",
    "match_fixed_schedule_blocks",
    "parse_fixed_schedule_operation",
    "replace_fixed_schedule_blocks",
    "select_fixed_schedule_block",
]
