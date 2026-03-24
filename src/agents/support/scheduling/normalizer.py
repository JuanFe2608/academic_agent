"""Normalización híbrida para horarios recurrentes semanales."""

from __future__ import annotations

import re
from typing import Callable

from agents.support.nodes.collect_extracurricular_details.parsing import (
    parse_extracurricular_items,
)
from agents.support.state import normalize_day, normalize_time
from agents.support.tools.llm import llm_extract_schedule_blocks, llm_normalize_schedule
from agents.support.tools.schedule_parser import (
    extract_natural_schedule_components,
    is_ambiguous_time_range,
    parse_academic_schedule_text,
    parse_work_schedule_text,
)

from .constants import DAY_ORDER, ScheduleBlockType, SPANISH_TO_ENGLISH
from .models import NormalizedScheduleResult, WeeklyScheduleBlock, ensure_weekly_block
from .titles import normalize_schedule_title

_DAY_TOKEN_PATTERN = (
    r"(?:"
    r"lunes|lun|l|"
    r"martes|mar|ma|"
    r"miercoles|miércoles|mier|mie|mi|x|"
    r"jueves|jue|ju|j|"
    r"viernes|vie|vi|v|"
    r"sabados|sábado|sabado|sab|sa|s|"
    r"domingos|domingo|dom|do|d"
    r")"
)
_DAY_RANGE_PATTERN = re.compile(
    rf"\b({_DAY_TOKEN_PATTERN})\b\s*(?:-|a|hasta)\s*\b({_DAY_TOKEN_PATTERN})\b",
    re.IGNORECASE,
)
_DAY_LIST_PATTERN = re.compile(rf"\b({_DAY_TOKEN_PATTERN})\b", re.IGNORECASE)
_ALL_DAYS_PATTERN = re.compile(
    r"\b(?:todos\s+los\s+dias|todos\s+los\s+días|cada\s+dia|cada\s+día|diario|diariamente)\b",
    re.IGNORECASE,
)
_ALL_DAYS_EXCEPT_PATTERN = re.compile(
    r"\b(?:todos\s+los\s+dias|todos\s+los\s+días|cada\s+dia|cada\s+día)\b\s+menos\s+(?P<excluded>.+)",
    re.IGNORECASE,
)
_TIME_RANGE_PATTERN = re.compile(
    r"(?:de|desde)?\s*(?:las\s+)?\d{1,2}(?::\d{2})?(?::\d{2})?(?:\s*[ap]\.?\s*m\.?)?\s*"
    r"(?:-|a|hasta)\s*(?:las\s+)?\d{1,2}(?::\d{2})?(?::\d{2})?(?:\s*[ap]\.?\s*m\.?)?",
    re.IGNORECASE,
)
_SEPARATOR_PATTERN = re.compile(r"(?:[\n;]+|,\s*(?=[A-Za-zÁÉÍÓÚáéíóúÑñ]))")


def normalize_schedule_section(
    text: str,
    schedule_type: ScheduleBlockType,
    timezone: str = "America/Bogota",
) -> NormalizedScheduleResult:
    """Normaliza una sección del horario a bloques recurrentes."""

    cleaned = str(text or "").strip()
    if not cleaned:
        return NormalizedScheduleResult(
            needs_clarification=True,
            clarifications=["No recibí texto para esa parte del horario."],
        )

    if schedule_type == "work":
        return _normalize_work_schedule(cleaned, timezone)
    if schedule_type == "academic":
        return _normalize_academic_schedule(cleaned, timezone)
    return _normalize_extracurricular_schedule(cleaned, timezone)


def merge_section_blocks(
    existing: list[WeeklyScheduleBlock],
    new_blocks: list[WeeklyScheduleBlock],
) -> list[WeeklyScheduleBlock]:
    """Agrega bloques y elimina duplicados exactos."""

    merged = [ensure_weekly_block(block) for block in existing] + [
        ensure_weekly_block(block) for block in new_blocks
    ]
    return _dedupe_blocks(merged)


def replace_section_blocks(
    existing: list[WeeklyScheduleBlock],
    block_type: ScheduleBlockType,
    new_blocks: list[WeeklyScheduleBlock],
) -> list[WeeklyScheduleBlock]:
    """Reemplaza por completo una sección del horario."""

    kept = [
        ensure_weekly_block(block)
        for block in existing
        if ensure_weekly_block(block).block_type != block_type
    ]
    normalized_new = [ensure_weekly_block(block) for block in new_blocks]
    return _dedupe_blocks(kept + normalized_new)


def _normalize_work_schedule(text: str, timezone: str) -> NormalizedScheduleResult:
    candidates: list[tuple[str, Callable[[], list[WeeklyScheduleBlock]]]] = [
        ("deterministic_work", lambda: _blocks_from_events(parse_work_schedule_text(text, timezone), "work", text, 0.92)),
    ]
    llm_lines = llm_normalize_schedule(text, "laboral")
    if llm_lines:
        candidates.append(
            ("llm_work_lines", lambda: _blocks_from_events(parse_work_schedule_text(llm_lines, timezone), "work", text, 0.8))
        )
    return _resolve_best_candidate(
        text,
        "work",
        candidates,
        timezone,
        fallback_clarification=_generic_clarifications(text, require_title=False),
    )


def _normalize_academic_schedule(text: str, timezone: str) -> NormalizedScheduleResult:
    candidates: list[tuple[str, Callable[[], list[WeeklyScheduleBlock]]]] = [
        ("deterministic_academic", lambda: _blocks_from_events(parse_academic_schedule_text(text, timezone), "academic", text, 0.9)),
        ("heuristic_academic_chunks", lambda: _heuristic_academic_blocks(text, timezone)),
    ]
    llm_lines = llm_normalize_schedule(text, "academico")
    if llm_lines:
        candidates.insert(
            1,
            (
                "llm_academic_lines",
                lambda: _blocks_from_events(parse_academic_schedule_text(llm_lines, timezone), "academic", text, 0.78),
            ),
        )
    return _resolve_best_candidate(
        text,
        "academic",
        candidates,
        timezone,
        fallback_clarification=_generic_clarifications(text, require_title=True),
    )


def _normalize_extracurricular_schedule(
    text: str,
    timezone: str,
) -> NormalizedScheduleResult:
    items, missing = parse_extracurricular_items(text, expected_is_variable=False)
    if items:
        blocks = _blocks_from_extracurricular_items(items, text, timezone)
        if not missing:
            return NormalizedScheduleResult(
                blocks=blocks,
                parser_used="deterministic_extracurricular",
            )
        return NormalizedScheduleResult(
            blocks=blocks,
            needs_clarification=True,
            clarifications=[_humanize_missing_fields(missing)],
            parser_used="deterministic_extracurricular_partial",
        )
    llm_result = _normalize_with_json_llm(text, "extracurricular", timezone)
    if llm_result.blocks:
        return llm_result
    clarifications = [
        "Necesito el nombre de cada actividad extracurricular, sus días y la hora de inicio y fin."
    ]
    if missing:
        clarifications = [_humanize_missing_fields(missing)]
    return NormalizedScheduleResult(
        needs_clarification=True,
        clarifications=clarifications,
    )


def _resolve_best_candidate(
    text: str,
    schedule_type: ScheduleBlockType,
    candidates: list[tuple[str, Callable[[], list[WeeklyScheduleBlock]]]],
    timezone: str,
    fallback_clarification: list[str],
) -> NormalizedScheduleResult:
    best_blocks: list[WeeklyScheduleBlock] = []
    best_parser: str | None = None
    for parser_name, parser in candidates:
        try:
            blocks = _dedupe_blocks(parser())
        except ValueError:
            continue
        if not blocks:
            continue
        if len(blocks) > len(best_blocks):
            best_blocks = blocks
            best_parser = parser_name
    if best_blocks:
        return NormalizedScheduleResult(blocks=best_blocks, parser_used=best_parser)
    llm_result = _normalize_with_json_llm(text, schedule_type, timezone)
    if llm_result.blocks:
        return llm_result
    return NormalizedScheduleResult(
        needs_clarification=True,
        clarifications=fallback_clarification,
        parser_used=best_parser,
    )


def _normalize_with_json_llm(
    text: str,
    schedule_type: ScheduleBlockType,
    timezone: str,
) -> NormalizedScheduleResult:
    payload = llm_extract_schedule_blocks(text, schedule_type=schedule_type)
    if not payload:
        return NormalizedScheduleResult()

    blocks: list[WeeklyScheduleBlock] = []
    clarifications = list(payload.get("clarifications") or [])
    for item in payload.get("blocks") or []:
        try:
            day_of_week = _normalize_day_token(str(item.get("day_of_week") or ""))
            start_time = normalize_time(str(item.get("start_time") or ""))
            end_time = normalize_time(str(item.get("end_time") or ""))
        except ValueError:
            continue
        if start_time >= end_time:
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            title = "Trabajo" if schedule_type == "work" else "Clase"
        confidence = item.get("confidence")
        try:
            confidence_value = float(confidence) if confidence is not None else 0.7
        except (TypeError, ValueError):
            confidence_value = 0.7
        blocks.append(
            WeeklyScheduleBlock(
                block_type=schedule_type,
                title=title,
                day_of_week=day_of_week,
                start_time=start_time,
                end_time=end_time,
                timezone=timezone,
                source_text=str(item.get("source_text") or text).strip() or text,
                confidence=max(0.0, min(confidence_value, 1.0)),
                ambiguity_flags=[
                    str(flag).strip()
                    for flag in list(item.get("ambiguity_flags") or [])
                    if str(flag).strip()
                ],
            )
        )
    return NormalizedScheduleResult(
        blocks=_dedupe_blocks(blocks),
        needs_clarification=bool(payload.get("needs_clarification")),
        clarifications=clarifications,
        parser_used="llm_structured_json",
    )


def _heuristic_academic_blocks(text: str, timezone: str) -> list[WeeklyScheduleBlock]:
    segments = _split_segments(text)
    blocks: list[WeeklyScheduleBlock] = []
    default_days: list[str] = []
    for segment in segments:
        days = _extract_days_from_text(segment)
        has_time_range = bool(_TIME_RANGE_PATTERN.search(segment))
        if days and not has_time_range:
            default_days = days
            continue
        if not has_time_range:
            continue
        effective_days = days or default_days
        if not effective_days:
            raise ValueError("Falta el día del bloque académico.")
        start_time, end_time = _extract_time_range(segment)
        title = _infer_title(segment, default_title="Clase")
        original_title, normalized_title = normalize_schedule_title(
            title,
            "academic",
            segment,
        )
        for day in effective_days:
            blocks.append(
                WeeklyScheduleBlock(
                    block_type="academic",
                    title=normalized_title,
                    original_title=original_title,
                    normalized_title=normalized_title,
                    day_of_week=day,
                    start_time=start_time,
                    end_time=end_time,
                    timezone=timezone,
                    source_text=segment,
                    confidence=0.82,
                )
            )
    return blocks


def _blocks_from_events(
    events: list,
    schedule_type: ScheduleBlockType,
    source_text: str,
    confidence: float,
) -> list[WeeklyScheduleBlock]:
    blocks: list[WeeklyScheduleBlock] = []
    for event in events:
        original_title, normalized_title = normalize_schedule_title(
            str(event.titulo).strip() or ("Trabajo" if schedule_type == "work" else "Clase"),
            schedule_type,
            source_text,
        )
        blocks.append(
            WeeklyScheduleBlock(
                block_type=schedule_type,
                title=normalized_title,
                original_title=original_title,
                normalized_title=normalized_title,
                day_of_week=_to_day_key(str(event.dia)),
                start_time=normalize_time(str(event.inicio)),
                end_time=normalize_time(str(event.fin)),
                timezone=str(event.timezone or "America/Bogota"),
                source_text=source_text,
                confidence=confidence,
            )
        )
    return blocks


def _blocks_from_extracurricular_items(
    items: list,
    source_text: str,
    timezone: str,
) -> list[WeeklyScheduleBlock]:
    blocks: list[WeeklyScheduleBlock] = []
    for item in items:
        if not item.dias or not item.hora_inicio or not item.hora_fin:
            continue
        original_title, normalized_title = normalize_schedule_title(
            item.nombre.strip() or "Actividad extracurricular",
            "extracurricular",
            item.detalle or source_text,
        )
        blocks.extend(
            WeeklyScheduleBlock(
                block_type="extracurricular",
                title=normalized_title,
                original_title=original_title,
                normalized_title=normalized_title,
                day_of_week=_to_day_key(day),
                start_time=normalize_time(item.hora_inicio),
                end_time=normalize_time(item.hora_fin),
                timezone=timezone,
                source_text=item.detalle or source_text,
                confidence=0.9,
            )
            for day in item.dias
        )
    return _dedupe_blocks(blocks)


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


def _split_segments(text: str) -> list[str]:
    parts = [part.strip() for part in _SEPARATOR_PATTERN.split(text) if part.strip()]
    return parts or [str(text).strip()]


def _extract_days_from_text(text: str) -> list[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    except_match = _ALL_DAYS_EXCEPT_PATTERN.search(raw)
    if except_match:
        excluded = {
            _normalize_day_token(match.group(1))
            for match in _DAY_LIST_PATTERN.finditer(except_match.group("excluded"))
        }
        return [day for day in DAY_ORDER if day not in excluded]
    range_match = _DAY_RANGE_PATTERN.search(raw)
    if range_match:
        start_day = _normalize_day_token(range_match.group(1))
        end_day = _normalize_day_token(range_match.group(2))
        return _expand_day_range(start_day, end_day)
    if _ALL_DAYS_PATTERN.search(raw):
        return list(DAY_ORDER)
    days: list[str] = []
    for match in _DAY_LIST_PATTERN.finditer(raw):
        day = _normalize_day_token(match.group(1))
        if day not in days:
            days.append(day)
    return days


def _extract_time_range(text: str) -> tuple[str, str]:
    seed = text if _extract_days_from_text(text) else f"Lunes {text}"
    parsed = extract_natural_schedule_components(seed)
    return normalize_time(str(parsed["start"])), normalize_time(str(parsed["end"]))


def _infer_title(text: str, default_title: str) -> str:
    cleaned = str(text or "")
    cleaned = _DAY_RANGE_PATTERN.sub(" ", cleaned)
    cleaned = _ALL_DAYS_EXCEPT_PATTERN.sub(" ", cleaned)
    cleaned = _ALL_DAYS_PATTERN.sub(" ", cleaned)
    cleaned = _DAY_LIST_PATTERN.sub(" ", cleaned)
    cleaned = _TIME_RANGE_PATTERN.sub(" ", cleaned)
    cleaned = re.sub(
        r"\b(de|desde|hasta|las|los|el|la|en|por|para|todos|dias|días|actualmente|voy|tengo|hago|y|e)\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,.-")
    if not cleaned:
        return default_title
    compact = " ".join(cleaned.split()[:6]).strip()
    return compact.title()


def _normalize_day_token(token: str) -> str:
    normalized = normalize_day(token)
    return _to_day_key(normalized)


def _to_day_key(spanish_day: str) -> str:
    normalized = normalize_day(spanish_day)
    day_key = SPANISH_TO_ENGLISH.get(normalized)
    if not day_key:
        raise ValueError(f"Dia no soportado: {spanish_day!r}")
    return day_key


def _expand_day_range(start_day: str, end_day: str) -> list[str]:
    start_index = DAY_ORDER.index(start_day)
    end_index = DAY_ORDER.index(end_day)
    if start_index <= end_index:
        return DAY_ORDER[start_index : end_index + 1]
    return DAY_ORDER[start_index:] + DAY_ORDER[: end_index + 1]


def _generic_clarifications(text: str, require_title: bool) -> list[str]:
    clarifications: list[str] = []
    if not _extract_days_from_text(text):
        clarifications.append("Necesito el día o los días exactos de ese horario.")
    if is_ambiguous_time_range(text):
        clarifications.append(
            "Necesito que aclares AM o PM en ese rango horario."
        )
    else:
        try:
            _extract_time_range(text)
        except ValueError:
            clarifications.append(
                "Necesito la hora de inicio y fin con un rango claro, por ejemplo: 7:00 a 18:00."
            )
    if require_title:
        compact_title = _infer_title(text, default_title="")
        if not compact_title:
            clarifications.append("Necesito el nombre de la materia o actividad.")
    if not clarifications:
        clarifications.append(
            "No pude interpretar esa parte del horario. Envíamela con días, horas y nombre."
        )
    return clarifications


def _humanize_missing_fields(missing: list[str]) -> str:
    unique = sorted({str(item).strip() for item in missing if str(item).strip()})
    if not unique:
        return "Necesito nombre, días y horas para cada actividad extracurricular."
    return (
        "Necesito algunos datos para cerrar bien las actividades extracurriculares: "
        + ", ".join(unique)
        + "."
    )
