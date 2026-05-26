"""Parseo determinístico y asistido por LLM de actividades extracurriculares."""

from __future__ import annotations

import re

from schemas.scheduling import ExtracurricularItem, PendingExtracurricularItem
from services.scheduling.activity_matching import normalize_text
from services.scheduling.ai_support import llm_normalize_extracurricular_items
from services.scheduling.pending_completion_support import build_pending_completion_text
from services.scheduling.text_parser import (
    extract_natural_schedule_components,
    is_ambiguous_time_range,
)
from services.scheduling.title_normalization import normalize_schedule_title
from services.scheduling.validation import (
    DAY_ORDER,
    normalize_day,
    normalize_day_typos_in_text,
)

_DAY_MARKER_PATTERN = re.compile(
    r"\b(lunes|martes|miercoles|miércoles|jueves|viernes|sabados|sabado|sábado|domingos|domingo|lun|mar|mie|jue|vie|sab|dom|todos\s+los\s+dias|todos\s+los\s+días|cada\s+dia|cada\s+día|diario|diariamente)\b"
)
_STOPWORDS = {
    "a",
    "al",
    "con",
    "de",
    "del",
    "el",
    "la",
    "las",
    "los",
    "mi",
    "mis",
    "solo",
    "para",
    "por",
    "fija",
    "fijo",
    "flexible",
    "variable",
    "tentativo",
    "tentativa",
    "todos",
    "dias",
    "dia",
    "cada",
    "desde",
    "hasta",
    "voy",
    "hago",
    "hacer",
    "luego",
    "despues",
    "actividad",
    "extracurricular",
    "y",
}
_TIME_RANGE_PATTERN = re.compile(
    r"(?:de|desde)?\s*(?:las\s+)?\d{1,2}(?::\d{2})?(?:\s*[ap]\.?\s*m\.?)?\s*(?:-|a|hasta)\s*(?:las\s+)?\d{1,2}(?::\d{2})?(?:\s*[ap]\.?\s*m\.?)?",
    re.IGNORECASE,
)
_EXPLICIT_DAY_PATTERN = re.compile(
    r"\b(lunes|martes|miercoles|miércoles|jueves|viernes|sabados|sábado|sabado|domingos|domingo|lun|mar|mie|jue|vie|sab|dom)\b",
    re.IGNORECASE,
)
_ALL_DAYS_PATTERN = re.compile(
    r"\b(?:todos\s+los\s+dias|todos\s+los\s+días|cada\s+dia|cada\s+día|diario|diariamente)\b",
    re.IGNORECASE,
)
_ACTIVITY_SEPARATOR_PATTERN = re.compile(
    r"(?:\s*,\s*|\s+(?:y|e|ademas|además|tambien|también)\s+)",
    re.IGNORECASE,
)
_CONTINUATION_PREFIX_PATTERN = re.compile(
    r"^\s*(?:luego|despues|después|mas\s+tarde|más\s+tarde|ademas|además|tambien|también)\b",
    re.IGNORECASE,
)
_POST_TIME_DAY_BOUNDARY_PATTERN = re.compile(
    r"\s*(?:,|\b(?:y|e)\b)\s+(?=(?:los?\s+)?(?:lunes|martes|miercoles|miércoles|jueves|viernes|sabados|sábado|sabado|domingos|domingo)\b)",
    re.IGNORECASE,
)


def parse_extracurricular_text(
    text: str,
    expected_is_variable: bool | None = None,
    inherited_days: list[str] | None = None,
) -> tuple[ExtracurricularItem, list[str]]:
    """Parsea texto de actividad extracurricular."""

    missing: list[str] = []
    normalized = normalize_text(text)

    nombre = _extract_value(normalized, r"nombre\s*[:\-]?\s*([a-z\s]+)")
    if not nombre:
        nombre = _infer_nombre(text)
    if not nombre:
        missing.append("nombre")
    nombre = normalize_schedule_title(
        nombre,
        "extracurricular",
        text,
    )[1]

    detalle = text.strip() if text.strip() else ""
    parsed_schedule: dict[str, object] | None = None
    if not detalle:
        missing.append("detalle")
    else:
        parsed_schedule, schedule_missing = _parse_schedule_with_optional_inheritance(
            detalle,
            inherited_days=inherited_days,
        )
        missing.extend(schedule_missing)

    es_variable = expected_is_variable
    if es_variable is None:
        es_variable = _parse_variable(normalized)
    if es_variable is None:
        es_variable = _infer_variability(normalized, parsed_schedule)

    detalle_normalizado = _build_normalized_detail(parsed_schedule) if parsed_schedule else detalle
    dias = list(parsed_schedule["days"]) if parsed_schedule else []
    frecuencia = _build_frequency_label(parsed_schedule)
    hora_inicio = str(parsed_schedule["start"]) if parsed_schedule else None
    hora_fin = str(parsed_schedule["end"]) if parsed_schedule else None

    item = ExtracurricularItem(
        nombre=nombre.strip() if nombre else "",
        es_variable=bool(es_variable),
        detalle=detalle_normalizado,
        dias=dias,
        frecuencia=frecuencia,
        hora_inicio=hora_inicio,
        hora_fin=hora_fin,
        tentativo=[],
    )
    return item, missing


def parse_extracurricular_items(
    text: str,
    expected_is_variable: bool | None = None,
) -> tuple[list[ExtracurricularItem], list[str]]:
    """Permite parsear varias actividades en un solo texto."""

    items, missing, _pending_items = parse_extracurricular_items_with_context(
        text,
        expected_is_variable=expected_is_variable,
    )
    return items, missing


def parse_extracurricular_items_with_context(
    text: str,
    expected_is_variable: bool | None = None,
) -> tuple[list[ExtracurricularItem], list[str], list[PendingExtracurricularItem]]:
    """Parsea varias actividades y conserva contexto de las incompletas."""

    chunks = _split_extracurricular_chunks(text)
    items: list[ExtracurricularItem] = []
    missing: list[str] = []
    pending_items: list[PendingExtracurricularItem] = []
    inherited_days_context: list[str] = []

    for index, chunk in enumerate(chunks, start=1):
        inherited_days = (
            inherited_days_context
            if _can_inherit_days(chunk, inherited_days_context)
            else None
        )
        item, item_missing = parse_extracurricular_text(
            chunk,
            expected_is_variable,
            inherited_days=inherited_days,
        )
        explicit_days = _extract_explicit_days(chunk)
        if item_missing:
            label = item.nombre.strip() or f"actividad {index}"
            for field in item_missing:
                missing.append(f"{label}: {field}")
            pending_items.append(
                PendingExtracurricularItem(
                    nombre=item.nombre.strip(),
                    dias=list(explicit_days or item.dias),
                    missing_fields=list(item_missing),
                    es_variable=item.es_variable,
                    raw_text=chunk,
                )
            )
            if explicit_days:
                inherited_days_context = explicit_days
            continue
        items.append(item)
        if explicit_days:
            inherited_days_context = list(item.dias or explicit_days)

    if items and not missing:
        return items, [], pending_items

    if items:
        return items, missing, pending_items

    llm_items = _parse_extracurricular_items_with_llm(text, expected_is_variable)
    if llm_items:
        return llm_items, [], []

    if not chunks:
        missing.append("detalle")

    return items, missing, pending_items


def complete_pending_extracurricular_item(
    response_text: str,
    pending_item: PendingExtracurricularItem | dict,
    expected_is_variable: bool | None = None,
) -> tuple[ExtracurricularItem, list[str]]:
    """Completa una actividad pendiente usando el contexto ya capturado."""

    pending = (
        pending_item
        if isinstance(pending_item, PendingExtracurricularItem)
        else PendingExtracurricularItem(**pending_item)
    )
    resolution_text, used_full_replacement = build_pending_completion_text(
        str(pending.raw_text or ""),
        str(response_text or ""),
    )
    effective_is_variable = (
        expected_is_variable if expected_is_variable is not None else pending.es_variable
    )
    item, missing = parse_extracurricular_text(
        resolution_text,
        expected_is_variable=effective_is_variable,
    )
    updates: dict[str, object] = {}
    if pending.nombre.strip() and not used_full_replacement and not item.nombre.strip():
        updates["nombre"] = pending.nombre.strip()
    if not item.dias and pending.dias:
        updates["dias"] = list(pending.dias)
        updates["frecuencia"] = item.frecuencia or ", ".join(pending.dias)
    if updates:
        item = item.model_copy(update=updates)
    return item, missing


def _parse_extracurricular_items_with_llm(
    text: str,
    expected_is_variable: bool | None = None,
) -> list[ExtracurricularItem]:
    normalized = llm_normalize_extracurricular_items(text)
    if not normalized:
        return []

    items: list[ExtracurricularItem] = []
    for item in normalized:
        nombre = str(item.get("nombre") or "").strip()
        detalle = str(item.get("detalle") or "").strip()
        es_variable = item.get("es_variable")
        if expected_is_variable is not None:
            es_variable = expected_is_variable
        if es_variable is None:
            es_variable = _infer_variability(normalize_text(detalle), None)
        if not nombre or not detalle or not isinstance(es_variable, bool):
            continue
        try:
            parsed_schedule = extract_natural_schedule_components(detalle)
        except ValueError:
            continue
        items.append(
            ExtracurricularItem(
                nombre=_compact_activity_name(nombre),
                es_variable=es_variable,
                detalle=_build_normalized_detail(parsed_schedule),
                dias=list(parsed_schedule["days"]),
                frecuencia=_build_frequency_label(parsed_schedule),
                hora_inicio=str(parsed_schedule["start"]),
                hora_fin=str(parsed_schedule["end"]),
                tentativo=[],
            )
        )
    return items


def _extract_value(text: str, pattern: str) -> str:
    match = re.search(pattern, text)
    return match.group(1) if match else ""


def _infer_nombre(text: str) -> str:
    normalized = normalize_day_typos_in_text(normalize_text(text))
    cleaned = _TIME_RANGE_PATTERN.sub(" ", normalized)
    cleaned = _DAY_MARKER_PATTERN.sub(" ", cleaned)
    cleaned = re.sub(
        r"\b(?:todos\s+los\s+dias|todos\s+los\s+días|cada\s+dia|cada\s+día|diario|diariamente)\b",
        " ",
        cleaned,
    )
    cleaned = re.sub(
        r"\b(?:voy|hago|hacer|asisto|practico|tengo|voy\s+a|voy\s+al|voy\s+a\s+la)\b",
        " ",
        cleaned,
    )
    cleaned = re.sub(r"\s*[-—–]\s*", " ", cleaned)
    cleaned = re.sub(
        r"\b(?:y|e)\b",
        " ",
        cleaned,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,:-")
    article_match = re.match(r"^(?:al|a\s+la|a|el|la)\s+([a-z][a-z\s]+)$", cleaned)
    if article_match:
        return article_match.group(1).strip()
    if "," in cleaned:
        candidate = cleaned.split(",", 1)[0].strip(" ,:-")
        if candidate:
            return candidate
    return cleaned


def _parse_variable(text: str) -> bool | None:
    if any(token in text for token in ("variable", "no fijo", "no fija", "flexible", "rotativo")):
        return True
    if any(token in text for token in ("fijo", "fija", "estable")):
        return False
    return None


def _infer_variability(
    normalized_text: str,
    parsed_schedule: dict[str, object] | None,
) -> bool:
    explicit = _parse_variable(normalized_text)
    if explicit is not None:
        return explicit
    if any(token in normalized_text for token in ("veces por semana", "tentativo", "cuando puedo")):
        return True
    return parsed_schedule is None


def _build_normalized_detail(parsed_schedule: dict[str, object] | None) -> str:
    if not parsed_schedule:
        return ""
    days = list(parsed_schedule.get("days") or [])
    start = str(parsed_schedule.get("start") or "")
    end = str(parsed_schedule.get("end") or "")
    if not days or not start or not end:
        return ""
    if parsed_schedule.get("is_all_days"):
        return f"Todos los dias {start}-{end}"
    return f"{', '.join(days)} {start}-{end}"


def _build_frequency_label(parsed_schedule: dict[str, object] | None) -> str | None:
    if not parsed_schedule:
        return None
    days = list(parsed_schedule.get("days") or [])
    if not days:
        return None
    if parsed_schedule.get("is_all_days"):
        return "todos los dias, desde lunes a domingo"
    return ", ".join(days)


def _split_extracurricular_chunks(text: str) -> list[str]:
    raw = str(text or "").strip()
    if not raw:
        return []

    coarse_parts = [
        part.strip(" ,")
        for part in re.split(r"[;\n]+", raw)
        if part.strip(" ,")
    ]
    chunks: list[str] = []
    for part in coarse_parts:
        chunks.extend(_split_chunk_on_activity_boundaries(part))
    return chunks


def _split_chunk_on_activity_boundaries(text: str) -> list[str]:
    text = text.strip(" ,")
    matches = list(_TIME_RANGE_PATTERN.finditer(text))
    if len(matches) <= 1:
        return _split_day_led_tail_after_last_time(text)

    chunks: list[str] = []
    cursor = 0
    for index, match in enumerate(matches[:-1]):
        next_match = matches[index + 1]
        boundary = _find_activity_boundary(text, match.end(), next_match.start())
        if boundary is None:
            continue
        chunk_end, next_cursor = boundary
        chunk = text[cursor:chunk_end].strip(" ,")
        if chunk:
            chunks.append(chunk)
        cursor = next_cursor

    tail = text[cursor:].strip(" ,")
    if tail:
        chunks.extend(_split_day_led_tail_after_last_time(tail))
    return chunks or [text]


def _find_activity_boundary(text: str, start: int, end: int) -> tuple[int, int] | None:
    between = text[start:end]
    separator = _ACTIVITY_SEPARATOR_PATTERN.search(between)
    if not separator:
        return None
    return start + separator.start(), start + separator.end()


def _split_day_led_tail_after_last_time(text: str) -> list[str]:
    raw = str(text or "").strip(" ,")
    if not raw:
        return []

    matches = list(_TIME_RANGE_PATTERN.finditer(raw))
    if not matches:
        return [raw]

    last = matches[-1]
    tail = raw[last.end() :]
    boundary = _POST_TIME_DAY_BOUNDARY_PATTERN.search(tail)
    if not boundary:
        return [raw]

    head = raw[: last.end()].strip(" ,")
    rest = tail[boundary.end() :].strip(" ,")
    chunks: list[str] = []
    if head:
        chunks.append(head)
    if rest:
        chunks.extend(_split_chunk_on_activity_boundaries(rest))
    return chunks or [raw]


def _compact_activity_name(name: str) -> str:
    return normalize_schedule_title(name, "extracurricular", name)[1]


def _parse_schedule_with_optional_inheritance(
    detail: str,
    inherited_days: list[str] | None = None,
) -> tuple[dict[str, object] | None, list[str]]:
    raw = normalize_day_typos_in_text(str(detail or "")).strip()
    if not raw:
        return None, ["detalle"]

    attempts = [raw]
    if _can_inherit_days(raw, inherited_days):
        attempts.insert(0, f"{', '.join(inherited_days or [])} {raw}")

    last_exc: ValueError | None = None
    for attempt in attempts:
        try:
            return extract_natural_schedule_components(attempt), []
        except ValueError as exc:
            last_exc = exc

    return None, _describe_missing_schedule_fields(raw, last_exc)


def _describe_missing_schedule_fields(
    detail: str,
    error: ValueError | None,
) -> list[str]:
    error_text = str(error).lower() if error else ""
    if "ambiguous time range" in error_text or is_ambiguous_time_range(detail):
        return ["aclarar AM o PM en el horario"]

    has_day = bool(_extract_explicit_days(detail))
    has_time = bool(_TIME_RANGE_PATTERN.search(detail))
    missing: list[str] = []
    if not has_day:
        missing.append("dia o dias exactos")
    if not has_time:
        missing.append("hora de inicio y fin")
    return missing or ["horario con dias y horas"]


def _can_inherit_days(text: str, inherited_days: list[str] | None) -> bool:
    return bool(
        inherited_days
        and _TIME_RANGE_PATTERN.search(text)
        and not _extract_explicit_days(text)
        and _CONTINUATION_PREFIX_PATTERN.search(normalize_text(text))
    )


def _extract_explicit_days(text: str) -> list[str]:
    normalized = normalize_day_typos_in_text(normalize_text(text))
    if not normalized:
        return []
    if _ALL_DAYS_PATTERN.search(normalized):
        return list(DAY_ORDER)

    days: list[str] = []
    for match in _EXPLICIT_DAY_PATTERN.finditer(normalized):
        day = _normalize_day_token(match.group(1))
        if day not in days:
            days.append(day)
    return days


def _normalize_day_token(token: str) -> str:
    try:
        return normalize_day(token)
    except ValueError:
        raw = str(token or "").strip()
        if raw.endswith("s") and len(raw) > 1:
            return normalize_day(raw[:-1])
        raise


__all__ = [
    "complete_pending_extracurricular_item",
    "parse_extracurricular_items",
    "parse_extracurricular_items_with_context",
    "parse_extracurricular_text",
]
