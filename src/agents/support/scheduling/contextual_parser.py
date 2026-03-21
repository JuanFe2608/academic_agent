"""Parseo parcial con contexto para horarios academicos y laborales."""

from __future__ import annotations

import re

from agents.support.scheduling.models import WeeklyScheduleBlock, ensure_weekly_block
from agents.support.scheduling.normalizer import (
    _extract_days_from_text,
    _extract_time_range,
    _infer_title,
    _split_segments,
    _to_day_key,
)
from agents.support.state import PendingScheduleItem, ScheduleContextType, normalize_day
from agents.support.tools.schedule_parser import (
    _is_subject_line,
    _normalize_lines,
    is_ambiguous_time_range,
    parse_work_schedule_text,
)

_TIME_RANGE_PATTERN = re.compile(
    r"(?:de|desde)?\s*(?:las\s+)?\d{1,2}(?::\d{2})?(?:\s*[ap]\.?\s*m\.?)?\s*"
    r"(?:-|a|hasta)\s*(?:las\s+)?\d{1,2}(?::\d{2})?(?:\s*[ap]\.?\s*m\.?)?",
    re.IGNORECASE,
)
_DAY_TOKEN_PATTERN = re.compile(
    r"\b(?:lunes|lun|martes|mar|miercoles|miércoles|mie|mier|jueves|jue|"
    r"viernes|vie|sabado|sábado|sabados|sab|domingo|domingos|dom|"
    r"l-v|lun-vie|lunes\s+a\s+viernes)\b",
    re.IGNORECASE,
)

_ENGLISH_TO_SPANISH = {
    "monday": "Lunes",
    "tuesday": "Martes",
    "wednesday": "Miercoles",
    "thursday": "Jueves",
    "friday": "Viernes",
    "saturday": "Sabado",
    "sunday": "Domingo",
}


def parse_schedule_section_with_context(
    text: str,
    schedule_type: ScheduleContextType,
    timezone: str = "America/Bogota",
) -> tuple[list[WeeklyScheduleBlock], list[str], list[PendingScheduleItem]]:
    """Parsea una seccion y conserva bloques validos y pendientes."""

    raw = str(text or "").strip()
    if not raw:
        return [], [], []

    if schedule_type == "work":
        return _parse_work_with_context(raw, timezone)
    return _parse_academic_with_context(raw, timezone)


def complete_pending_schedule_item(
    response_text: str,
    pending_item: PendingScheduleItem | dict,
    timezone: str = "America/Bogota",
) -> tuple[list[WeeklyScheduleBlock], list[str], PendingScheduleItem | None]:
    """Completa un bloque pendiente usando la respuesta corta del usuario."""

    pending = (
        pending_item
        if isinstance(pending_item, PendingScheduleItem)
        else PendingScheduleItem(**pending_item)
    )
    combined_text = " ".join(
        part.strip()
        for part in [str(pending.raw_text or ""), str(response_text or "")]
        if str(part).strip()
    )

    blocks, clarifications, pending_items = parse_schedule_section_with_context(
        combined_text,
        pending.schedule_type,
        timezone=timezone,
    )
    if pending_items:
        updated = pending_items[0]
        updates: dict[str, object] = {}
        if pending.title.strip():
            updates["title"] = pending.title.strip()
        if not updated.days and pending.days:
            updates["days"] = list(pending.days)
        if updates:
            updated = updated.model_copy(update=updates)
        return blocks, clarifications, updated
    return blocks, clarifications, None


def serialize_blocks_for_schedule_type(
    blocks: list[WeeklyScheduleBlock] | list[dict],
    schedule_type: ScheduleContextType,
) -> str:
    """Serializa bloques a un texto simple y estable para raw_inputs."""

    normalized = [
        block if isinstance(block, WeeklyScheduleBlock) else WeeklyScheduleBlock(**block)
        for block in blocks
        if ensure_weekly_block(block).block_type == schedule_type
    ]
    normalized.sort(key=lambda block: (block.day_of_week, block.start_time, block.title))

    lines: list[str] = []
    for block in normalized:
        day = _ENGLISH_TO_SPANISH.get(block.day_of_week, block.day_of_week)
        if schedule_type == "work":
            lines.append(f"{day} {block.start_time}-{block.end_time}")
        else:
            lines.append(f"{day} {block.start_time}-{block.end_time} {block.title}".strip())
    return "\n".join(lines)


def build_schedule_pending_prompt(
    schedule_type: ScheduleContextType,
    pending_items: list[PendingScheduleItem] | list[dict],
    clarifications: list[str] | None = None,
) -> str:
    """Construye un prompt corto para pedir solo el dato faltante."""

    items = _coerce_pending_items(pending_items)
    if not items:
        return "\n".join(str(item).strip() for item in (clarifications or []) if str(item).strip())

    current = items[0]
    section_label = "horario académico" if schedule_type == "academic" else "horario laboral"
    title = current.title.strip() or ("Trabajo" if schedule_type == "work" else "bloque académico")
    missing_text = ", ".join(current.missing_fields) if current.missing_fields else "datos del horario"

    lines = [f"Necesito algunos datos para cerrar bien tu {section_label}: {title}: {missing_text}."]
    if missing_text == "aclarar AM o PM en el horario":
        lines.append("Puedes responder solo con lo que falta. Ejemplo: de 7 pm a 9 pm.")
    elif missing_text == "nombre de la materia o actividad":
        lines.append("Puedes responder solo con el nombre. Ejemplo: Algebra.")
    else:
        lines.append("Si prefieres, envíalo completo en formato: Dia(s) de HH:MM a HH:MM Nombre.")
    return "\n".join(lines)


def _parse_work_with_context(
    text: str,
    timezone: str,
) -> tuple[list[WeeklyScheduleBlock], list[str], list[PendingScheduleItem]]:
    chunks = [chunk.strip() for chunk in re.split(r"[\n;]+", text) if chunk.strip()] or [text]
    blocks: list[WeeklyScheduleBlock] = []
    clarifications: list[str] = []
    pending_items: list[PendingScheduleItem] = []

    for chunk in chunks:
        try:
            events = parse_work_schedule_text(chunk, timezone)
        except ValueError as exc:
            pending = PendingScheduleItem(
                schedule_type="work",
                title="Trabajo",
                days=_extract_spanish_days(chunk),
                missing_fields=_describe_missing_schedule_fields(
                    chunk,
                    schedule_type="work",
                    title="Trabajo",
                    error=exc,
                ),
                raw_text=chunk,
            )
            pending_items.append(pending)
            clarifications.extend(f"Trabajo: {field}" for field in pending.missing_fields)
            continue
        blocks.extend(_events_to_blocks(events, "work", chunk, 0.92))

    return _dedupe_blocks(blocks), clarifications, pending_items


def _parse_academic_with_context(
    text: str,
    timezone: str,
) -> tuple[list[WeeklyScheduleBlock], list[str], list[PendingScheduleItem]]:
    blocks: list[WeeklyScheduleBlock] = []
    clarifications: list[str] = []
    pending_items: list[PendingScheduleItem] = []
    chunks = _iter_academic_chunks(text)

    for chunk_text, inherited_title in chunks:
        parsed_blocks, pending = _parse_academic_chunk(
            chunk_text,
            inherited_title=inherited_title,
            timezone=timezone,
        )
        if pending is not None:
            pending_items.append(pending)
            label = pending.title.strip() or "bloque académico"
            clarifications.extend(f"{label}: {field}" for field in pending.missing_fields)
            continue
        blocks.extend(parsed_blocks)

    return _dedupe_blocks(blocks), clarifications, pending_items


def _iter_academic_chunks(text: str) -> list[tuple[str, str]]:
    lines = _normalize_lines(text)
    if len(lines) <= 1:
        return [(segment, "") for segment in _split_segments(text)]

    chunks: list[tuple[str, str]] = []
    current_subject = ""
    for line in lines:
        if _looks_like_schedule_fragment(line):
            chunks.append((line.strip(), current_subject))
            continue
        if _is_subject_line(line):
            current_subject = line.strip()

    if chunks:
        return chunks
    return [(segment, "") for segment in _split_segments(text)]


def _looks_like_schedule_fragment(text: str) -> bool:
    return bool(_TIME_RANGE_PATTERN.search(text) or _DAY_TOKEN_PATTERN.search(text))


def _parse_academic_chunk(
    text: str,
    *,
    inherited_title: str,
    timezone: str,
) -> tuple[list[WeeklyScheduleBlock], PendingScheduleItem | None]:
    raw = str(text or "").strip()
    if not raw:
        return [], None

    title = inherited_title.strip() or _infer_title(raw, default_title="")
    missing = _describe_missing_schedule_fields(
        raw,
        schedule_type="academic",
        title=title,
        error=None,
    )
    if missing:
        return [], PendingScheduleItem(
            schedule_type="academic",
            title=title,
            days=_extract_spanish_days(raw),
            missing_fields=missing,
            raw_text=_build_pending_academic_raw_text(raw, title),
        )

    start_time, end_time = _extract_time_range(raw)
    days = _extract_days_from_text(raw)
    blocks = [
        WeeklyScheduleBlock(
            block_type="academic",
            title=title.strip() or "Clase",
            day_of_week=day_of_week,
            start_time=start_time,
            end_time=end_time,
            timezone=timezone,
            source_text=raw,
            confidence=0.84,
        )
        for day_of_week in days
    ]
    return blocks, None


def _describe_missing_schedule_fields(
    text: str,
    *,
    schedule_type: ScheduleContextType,
    title: str,
    error: ValueError | None,
) -> list[str]:
    error_text = str(error).lower() if error else ""
    if "ambiguous time range" in error_text or is_ambiguous_time_range(text):
        return ["aclarar AM o PM en el horario"]

    missing: list[str] = []
    if not _extract_days_from_text(text):
        missing.append("dia o dias exactos")

    if not _TIME_RANGE_PATTERN.search(text):
        missing.append("hora de inicio y fin")
    else:
        try:
            _extract_time_range(text)
        except ValueError:
            missing.append("hora de inicio y fin")

    if schedule_type == "academic" and not title.strip():
        missing.append("nombre de la materia o actividad")

    if missing:
        return missing
    if error is not None:
        return ["dias y horas del horario"]
    return []


def _extract_spanish_days(text: str) -> list[str]:
    days: list[str] = []
    for day_key in _extract_days_from_text(text):
        label = _ENGLISH_TO_SPANISH.get(day_key, day_key)
        if label not in days:
            days.append(label)
    return days


def _build_pending_academic_raw_text(raw_text: str, title: str) -> str:
    raw = str(raw_text or "").strip()
    if not raw:
        return title.strip()
    compact_title = title.strip()
    if not compact_title:
        return raw
    if compact_title.lower() in raw.lower():
        return raw
    return f"{raw} {compact_title}".strip()


def _events_to_blocks(
    events: list,
    schedule_type: ScheduleContextType,
    source_text: str,
    confidence: float,
) -> list[WeeklyScheduleBlock]:
    return [
        WeeklyScheduleBlock(
            block_type=schedule_type,
            title=str(event.titulo).strip() or ("Trabajo" if schedule_type == "work" else "Clase"),
            day_of_week=_to_day_key(str(normalize_day(event.dia))),
            start_time=str(event.inicio),
            end_time=str(event.fin),
            timezone=str(event.timezone or "America/Bogota"),
            source_text=source_text,
            confidence=confidence,
        )
        for event in events
    ]


def _dedupe_blocks(blocks: list[WeeklyScheduleBlock]) -> list[WeeklyScheduleBlock]:
    seen: set[tuple[str, str, str, str, str]] = set()
    deduped: list[WeeklyScheduleBlock] = []
    for raw_block in blocks:
        block = ensure_weekly_block(raw_block)
        key = (
            block.block_type,
            block.title.strip().lower(),
            block.day_of_week,
            block.start_time,
            block.end_time,
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(block)
    return deduped


def _coerce_pending_items(
    raw_items: list[PendingScheduleItem] | list[dict],
) -> list[PendingScheduleItem]:
    return [
        item if isinstance(item, PendingScheduleItem) else PendingScheduleItem(**item)
        for item in raw_items
    ]
