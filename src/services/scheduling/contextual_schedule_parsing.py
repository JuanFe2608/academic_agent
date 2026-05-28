"""Parseo contextual de horarios académicos y laborales."""

from __future__ import annotations

import re

from schemas.scheduling import PendingScheduleItem, ScheduleContextType
from services.scheduling.heuristic_schedule_parsing import (
    extract_days_from_text,
    extract_time_range,
    infer_title,
    split_schedule_chunks,
    split_segments,
    to_day_key,
)
from services.scheduling.models import WeeklyScheduleBlock, ensure_weekly_block
from services.scheduling.pending_completion_support import build_pending_completion_text
from services.scheduling.text_parser import (
    is_ambiguous_time_range,
    parse_work_schedule_text,
)
from services.scheduling.text_parser._common import (
    ACADEMIC_DAYS_PATTERN,
    normalize_lines as _normalize_lines,
    strip_accents as _strip_accents,
)
from services.scheduling.text_parser.academic import is_subject_line as _is_subject_line
from services.scheduling.title_normalization import (
    is_placeholder_schedule_title,
    normalize_schedule_title,
)
from services.scheduling.validation import normalize_day

_TIME_RANGE_PATTERN = re.compile(
    r"(?:de|desde)?\s*(?:las\s+)?\d{1,2}(?::\d{2})?(?::\d{2})?(?:\s*[ap]\.?\s*m\.?)?\s*"
    r"(?:-|a|hasta)\s*(?:las\s+)?\d{1,2}(?::\d{2})?(?::\d{2})?(?:\s*[ap]\.?\s*m\.?)?",
    re.IGNORECASE,
)
_DATE_RANGE_LINE_PATTERN = re.compile(
    r"^\s*\d{2}-\d{2}-\d{4}\s*-\s*\d{2}-\d{2}-\d{4}\s*$"
)
_DAY_TOKEN_PATTERN = re.compile(
    r"\b(?:lunes|lun|martes|mar|miercoles|miércoles|mie|mier|jueves|jue|"
    r"viernes|vie|sabado|sábado|sabados|sab|domingo|domingos|dom|"
    r"l-v|lun-vie|lunes\s+a\s+viernes)\b",
    re.IGNORECASE,
)
_INLINE_TITLE_SEPARATOR_PATTERN = re.compile(r"(?:\s[-—–]\s|:\s)")

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
    """Parsea una sección y conserva bloques válidos y pendientes."""

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
    resolution_text, used_full_replacement = build_pending_completion_text(
        str(pending.raw_text or ""),
        str(response_text or ""),
    )

    blocks, clarifications, pending_items = parse_schedule_section_with_context(
        resolution_text,
        pending.schedule_type,
        timezone=timezone,
    )
    if pending_items:
        updated = pending_items[0]
        updates: dict[str, object] = {}
        if pending.title.strip() and not used_full_replacement and not updated.title.strip():
            updates["title"] = pending.title.strip()
        if not updated.days and pending.days:
            updates["days"] = list(pending.days)
        if updates:
            updated = updated.model_copy(update=updates)
        return blocks, clarifications, updated
    return blocks, clarifications, None


def _parse_work_with_context(
    text: str,
    timezone: str,
) -> tuple[list[WeeklyScheduleBlock], list[str], list[PendingScheduleItem]]:
    chunks = split_schedule_chunks(text)
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
    inherited_days_context: list[str] = []

    for chunk_text, inherited_title in chunks:
        explicit_days = extract_days_from_text(chunk_text)
        inherited_days = (
            inherited_days_context
            if _can_inherit_days(chunk_text, inherited_days_context)
            else explicit_days
        )
        parsed_blocks, pending = _parse_academic_chunk(
            chunk_text,
            inherited_title=inherited_title,
            inherited_days=inherited_days,
            timezone=timezone,
        )
        if pending is not None:
            pending_items.append(pending)
            label = pending.title.strip() or "bloque académico"
            clarifications.extend(f"{label}: {field}" for field in pending.missing_fields)
            if explicit_days:
                inherited_days_context = explicit_days
            continue
        blocks.extend(parsed_blocks)
        if explicit_days:
            inherited_days_context = explicit_days
        elif inherited_days:
            inherited_days_context = list(inherited_days)

    return _dedupe_blocks(blocks), clarifications, pending_items


def _iter_academic_chunks(text: str) -> list[tuple[str, str]]:
    lines = _normalize_lines(text)
    if len(lines) <= 1:
        return [(segment, "") for segment in split_schedule_chunks(text)]

    chunks: list[tuple[str, str]] = []
    current_subject = ""
    university_format = _looks_like_university_schedule(text)
    waits_for_university_marker = university_format and _has_university_course_markers(text)
    inside_university_course = not waits_for_university_marker
    for line in lines:
        if waits_for_university_marker and _is_university_course_marker(line):
            inside_university_course = True
            current_subject = ""
            continue
        if waits_for_university_marker and not inside_university_course:
            continue
        if _is_ignored_academic_line(line):
            continue
        if _looks_like_schedule_fragment(line):
            if university_format and ACADEMIC_DAYS_PATTERN.search(line):
                chunks.append((line.strip(), current_subject))
                continue
            chunks.extend(
                (chunk, current_subject)
                for chunk in split_schedule_chunks(line)
                if chunk
            )
            continue
        if _is_subject_line(line):
            if is_placeholder_schedule_title(line):
                continue
            current_subject = line.strip()

    if chunks:
        return chunks
    return [(segment, "") for segment in split_schedule_chunks(text)]


def _looks_like_schedule_fragment(text: str) -> bool:
    if _DATE_RANGE_LINE_PATTERN.fullmatch(str(text or "").strip()):
        return False
    return bool(_TIME_RANGE_PATTERN.search(text) or _DAY_TOKEN_PATTERN.search(text))


def _looks_like_university_schedule(text: str) -> bool:
    normalized = str(text or "").lower()
    return (
        "código asignatura" in normalized
        or "codigo asignatura" in normalized
        or "total asignaturas inscritas" in normalized
        or bool(re.search(r"\b(?:lun|mar|mie|jue|vie|sab|dom)(?:\s*,\s*(?:lun|mar|mie|jue|vie|sab|dom))*\s+\d{1,2}:\d{2}", normalized))
    )


def _is_university_course_marker(line: str) -> bool:
    normalized = str(line or "").lower()
    return "código asignatura" in normalized or "codigo asignatura" in normalized


def _has_university_course_markers(text: str) -> bool:
    normalized = str(text or "").lower()
    return "código asignatura" in normalized or "codigo asignatura" in normalized


def _is_ignored_academic_line(line: str) -> bool:
    normalized = str(line or "").strip().lower()
    folded = _strip_accents(normalized)
    if not folded:
        return True
    if folded.isdigit():
        return True
    # Standalone image placeholders ("image", "imagen", "imagen 1", etc.)
    if is_placeholder_schedule_title(line.strip()):
        return True
    return any(
        token in folded
        for token in (
            "hola ",
            "tenemos buenas noticias",
            "tu horario para el periodo",
            "te presentamos el detalle",
            "total asignaturas inscritas",
            "ingenieria de sistemas",
        )
    )


def _parse_academic_chunk(
    text: str,
    *,
    inherited_title: str,
    inherited_days: list[str],
    timezone: str,
) -> tuple[list[WeeklyScheduleBlock], PendingScheduleItem | None]:
    raw = str(text or "").strip()
    if not raw:
        return [], None

    title = _resolve_academic_chunk_title(raw, inherited_title)
    raw_without_placeholder_title = _strip_placeholder_title_from_schedule_text(
        raw,
        title,
    )
    if is_placeholder_schedule_title(title):
        title = ""
    days = extract_days_from_text(raw) or list(inherited_days)
    missing = _describe_missing_schedule_fields(
        raw,
        schedule_type="academic",
        title=title,
        error=None,
        extracted_days=days,
    )
    if missing:
        return [], PendingScheduleItem(
            schedule_type="academic",
            title=title,
            days=_extract_spanish_days(raw) or [_ENGLISH_TO_SPANISH.get(day, day) for day in days],
            missing_fields=missing,
            raw_text=_build_pending_academic_raw_text(
                raw_without_placeholder_title,
                title,
            ),
        )

    start_time, end_time = extract_time_range(raw)
    original_title, normalized_title = normalize_schedule_title(title, "academic", raw)
    blocks = [
        WeeklyScheduleBlock(
            block_type="academic",
            title=normalized_title or "Clase",
            original_title=original_title or normalized_title or "Clase",
            normalized_title=normalized_title or "Clase",
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


def _resolve_academic_chunk_title(raw: str, inherited_title: str) -> str:
    inherited = inherited_title.strip()
    explicit = infer_title(raw, default_title="").strip()
    if explicit and _has_explicit_inline_academic_title(raw):
        return explicit
    return inherited or explicit


def _has_explicit_inline_academic_title(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False

    explicit = infer_title(raw, default_title="").strip()
    if not explicit:
        return False

    leading = raw.lstrip()
    if _DAY_TOKEN_PATTERN.match(leading):
        return bool(_INLINE_TITLE_SEPARATOR_PATTERN.search(leading))
    return True


def _describe_missing_schedule_fields(
    text: str,
    *,
    schedule_type: ScheduleContextType,
    title: str,
    error: ValueError | None,
    extracted_days: list[str] | None = None,
) -> list[str]:
    error_text = str(error).lower() if error else ""
    if "ambiguous time range" in error_text or is_ambiguous_time_range(text):
        return ["aclarar AM o PM en el horario"]

    missing: list[str] = []
    if not (extracted_days or extract_days_from_text(text)):
        missing.append("dia o dias exactos")

    if not _TIME_RANGE_PATTERN.search(text):
        missing.append("hora de inicio y fin")
    else:
        try:
            extract_time_range(text)
        except ValueError:
            missing.append("hora de inicio y fin")

    if schedule_type == "academic" and (
        not title.strip() or is_placeholder_schedule_title(title)
    ):
        missing.append("nombre de la materia o actividad")

    if missing:
        return missing
    if error is not None:
        return ["dias y horas del horario"]
    return []


def _extract_spanish_days(text: str) -> list[str]:
    days: list[str] = []
    for day_key in extract_days_from_text(text):
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


def _strip_placeholder_title_from_schedule_text(raw_text: str, title: str) -> str:
    raw = str(raw_text or "").strip()
    clean_title = str(title or "").strip()
    if not raw or not clean_title or not is_placeholder_schedule_title(clean_title):
        return raw

    escaped = re.escape(clean_title)
    cleaned = re.sub(
        rf"(?i)^\s*{escaped}\s*[-—–:]?\s*",
        "",
        raw,
    )
    cleaned = re.sub(
        rf"(?i)(?:\s*[-—–:]?\s*){escaped}\s*$",
        "",
        cleaned,
    ).strip(" ,.;:-—–")
    return cleaned or raw


def _can_inherit_days(text: str, inherited_days: list[str]) -> bool:
    return bool(
        inherited_days
        and _TIME_RANGE_PATTERN.search(text)
        and not extract_days_from_text(text)
    )


def _events_to_blocks(
    events: list,
    schedule_type: ScheduleContextType,
    source_text: str,
    confidence: float,
) -> list[WeeklyScheduleBlock]:
    blocks: list[WeeklyScheduleBlock] = []
    for event in events:
        original_title, normalized_title = normalize_schedule_title(
            str(event.titulo).strip() or ("Trabajo" if schedule_type == "work" else "Clase"),
            schedule_type,  # type: ignore[arg-type]
            source_text,
        )
        blocks.append(
            WeeklyScheduleBlock(
                block_type=schedule_type,
                title=normalized_title,
                original_title=original_title,
                normalized_title=normalized_title,
                day_of_week=to_day_key(str(normalize_day(event.dia))),
                start_time=str(event.inicio),
                end_time=str(event.fin),
                timezone=str(event.timezone or "America/Bogota"),
                source_text=source_text,
                confidence=confidence,
            )
        )
    return blocks


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


__all__ = [
    "complete_pending_schedule_item",
    "parse_schedule_section_with_context",
]
