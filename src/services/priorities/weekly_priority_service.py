"""Dominio determinista para prioridades semanales y eventos academicos."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from schemas.common import Prioridad
from schemas.planning import SubjectItem
from .state_helpers import ensure_subject_items

_NONE_COMMANDS = {
    "ninguna",
    "ninguno",
    "no hay",
    "sin urgencias",
    "nada",
    "no tengo nada",
}
_USE_SCHEDULE_COMMANDS = {
    "usar horario",
    "usar el horario",
    "usar materias detectadas",
    "usar lo detectado",
    "despues",
    "dejarlo por ahora",
    "dejalo por ahora",
    "mas tarde",
    "luego",
}
_SKIP_COMMANDS = {"omitir", "skip"}
_CONFIRM_COMMANDS = {"si", "sip", "ok", "listo", "confirmar", "confirmo", "vale"}
_EDIT_COMMANDS = {"editar", "cambiar", "corregir"}
_NO_COMMANDS = {"no", "nop", "negativo"}
_EVENT_TYPE_KEYWORDS = {
    "parcial": {"parcial", "examen", "evaluacion", "evaluacion parcial", "final"},
    "quiz": {"quiz", "control", "prueba corta"},
    "entrega": {"entrega", "trabajo", "tarea", "proyecto"},
    "exposicion": {"exposicion", "presentacion"},
    "actividad": {"actividad", "laboratorio", "taller"},
}
_ACADEMIC_EVENT_WORDS = set().union(*_EVENT_TYPE_KEYWORDS.values())
_ACADEMIC_ACTIVITY_MANAGEMENT_WORDS = {
    "estudio pendiente",
    "sesion de estudio",
    "pendiente estudiar",
    "actividades pendientes",
}
_MISSED_STUDY_WORDS = {
    "no pude estudiar",
    "no estudie",
    "no alcance",
    "me salte",
    "perdi la sesion",
}
_COMPLETION_WORDS = {
    "ya termine",
    "termine",
    "complete",
    "completada",
    "hecho",
}
_WEEKDAYS = {
    "lunes": 0,
    "martes": 1,
    "miercoles": 2,
    "jueves": 3,
    "viernes": 4,
    "sabado": 5,
    "domingo": 6,
}


@dataclass(frozen=True)
class NumberSelectionParseResult:
    """Resultado de parsear una seleccion de materias numeradas."""

    is_valid: bool
    numbers: list[int] = field(default_factory=list)
    command: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class UrgencyDetail:
    """Detalle estructurado de una urgencia academica."""

    subject_number: int
    urgency_type: str
    due_at: str
    raw_text: str


@dataclass(frozen=True)
class UrgencyDetailsParseResult:
    """Resultado de parsear detalles cortos de urgencia."""

    is_valid: bool
    details: list[UrgencyDetail] = field(default_factory=list)
    error: str | None = None


@dataclass(frozen=True)
class PriorityScoreResult:
    """Score normalizado y nivel compatible con el planificador actual."""

    score: float
    level: Prioridad
    urgency_level: Prioridad | None
    components: dict[str, float]


@dataclass(frozen=True)
class WeeklyPriorityResult:
    """Snapshot semanal calculado a partir de datos estructurados."""

    subjects: list[SubjectItem]
    summary: dict[str, object]


@dataclass(frozen=True)
class AcademicEventUpdateResult:
    """Resultado de procesar una actualizacion academica puntual."""

    detected: bool
    event_type: str | None = None
    subjects: list[SubjectItem] = field(default_factory=list)
    message: str = ""
    replan_required: bool = False
    requires_clarification: bool = False
    payload: dict[str, object] = field(default_factory=dict)


def parse_priority_command(text: str | None) -> str | None:
    """Normaliza comandos conversacionales del bloque semanal."""

    normalized = _normalize(text)
    if not normalized:
        return None
    if normalized in _USE_SCHEDULE_COMMANDS:
        return "usar_horario"
    if normalized in _SKIP_COMMANDS:
        return "omitir"
    if normalized in _NONE_COMMANDS:
        return "ninguna"
    if normalized in _CONFIRM_COMMANDS:
        return "confirmar"
    if normalized in _EDIT_COMMANDS:
        return "editar"
    if normalized in _NO_COMMANDS:
        return "no"
    return None


def parse_number_selection(
    text: str | None,
    *,
    subject_count: int,
    min_count: int,
    max_count: int,
    allow_none: bool = False,
    ordered: bool = False,
) -> NumberSelectionParseResult:
    """Parsea respuestas tipo ``3,1,2`` contra una lista numerada."""

    command = parse_priority_command(text)
    if command in {"usar_horario", "omitir"}:
        return NumberSelectionParseResult(is_valid=True, command=command)
    if allow_none and command in {"ninguna", "no"}:
        return NumberSelectionParseResult(is_valid=True, numbers=[], command="ninguna")

    numbers = [int(match.group(0)) for match in re.finditer(r"\d+", str(text or ""))]
    if not numbers:
        return NumberSelectionParseResult(
            is_valid=False,
            error="No encontre numeros de materias. Responde por ejemplo: 3,1,2.",
        )
    if len(numbers) != len(set(numbers)):
        return NumberSelectionParseResult(
            is_valid=False,
            error="Hay materias repetidas. Usa cada numero una sola vez.",
        )
    invalid = [number for number in numbers if number < 1 or number > subject_count]
    if invalid:
        return NumberSelectionParseResult(
            is_valid=False,
            error=f"El numero {invalid[0]} no esta en la lista de materias.",
        )
    if len(numbers) < min_count:
        return NumberSelectionParseResult(
            is_valid=False,
            error=f"Necesito al menos {min_count} materia(s) para continuar.",
        )
    if len(numbers) > max_count:
        return NumberSelectionParseResult(
            is_valid=False,
            error=f"Selecciona maximo {max_count} materia(s).",
        )
    if ordered and len(numbers) != max_count:
        return NumberSelectionParseResult(
            is_valid=False,
            error=f"Necesito {max_count} materias en orden, por ejemplo: 3,1,2.",
        )
    return NumberSelectionParseResult(is_valid=True, numbers=numbers)


def parse_urgency_details(
    text: str | None,
    *,
    subject_count: int,
    reference_date: date,
    timezone: str,
    required_subject_numbers: list[int] | None = None,
    default_subject_number: int | None = None,
) -> UrgencyDetailsParseResult:
    """Parsea lineas cortas como ``2 parcial viernes``."""

    required = set(required_subject_numbers or [])
    command = parse_priority_command(text)
    if command == "ninguna" and not required:
        return UrgencyDetailsParseResult(is_valid=True, details=[])

    details: list[UrgencyDetail] = []
    for line in [item.strip() for item in str(text or "").splitlines() if item.strip()]:
        subject_number = _subject_number_from_detail_line(
            line,
            subject_count=subject_count,
            default_subject_number=default_subject_number,
        )
        if subject_number is None:
            return UrgencyDetailsParseResult(
                is_valid=False,
                error="No pude identificar la materia de ese detalle.",
            )
        if subject_number < 1 or subject_number > subject_count:
            return UrgencyDetailsParseResult(
                is_valid=False,
                error=f"El numero {subject_number} no esta en la lista de materias.",
            )
        urgency_type = _detect_urgency_type(line)
        if urgency_type is None:
            return UrgencyDetailsParseResult(
                is_valid=False,
                error="Indica el tipo: quiz, parcial, entrega, exposicion o actividad.",
            )
        due_at = _resolve_due_at(line, reference_date=reference_date, timezone=timezone)
        if due_at is None:
            return UrgencyDetailsParseResult(
                is_valid=False,
                error="No encontre fecha. Usa algo como: 2 parcial viernes.",
            )
        details.append(
            UrgencyDetail(
                subject_number=subject_number,
                urgency_type=urgency_type,
                due_at=due_at,
                raw_text=line,
            )
        )

    seen = {detail.subject_number for detail in details}
    if required and seen != required:
        missing = sorted(required - seen)
        if missing:
            return UrgencyDetailsParseResult(
                is_valid=False,
                error=f"Falta detalle para la materia {missing[0]}.",
            )
    return UrgencyDetailsParseResult(is_valid=True, details=details)


def _subject_number_from_detail_line(
    line: str,
    *,
    subject_count: int,
    default_subject_number: int | None,
) -> int | None:
    explicit = re.match(r"\s*#?(\d+)(?:[\.\)\-:]|\s+)", line)
    if explicit is not None:
        number = int(explicit.group(1))
        if 1 <= number <= subject_count:
            return number
        return None
    if default_subject_number is not None:
        return int(default_subject_number)
    match = re.search(r"\d+", line)
    if match is None:
        return None
    return int(match.group(0))


def build_weekly_priorities(
    *,
    subjects: list[SubjectItem | dict],
    importance_order: list[int],
    urgency_details: list[UrgencyDetail | dict],
    difficult_subject_numbers: list[int],
    reference_date: date,
    timezone: str,
    source: str = "weekly_flow",
) -> WeeklyPriorityResult:
    """Calcula el snapshot semanal sin depender de texto libre por materia."""

    normalized_subjects = ensure_subject_items(subjects)
    details_by_number = {
        _detail_subject_number(detail): _ensure_urgency_detail(detail)
        for detail in urgency_details
    }
    difficult_numbers = set(difficult_subject_numbers or [])
    rank_by_number = {
        subject_number: rank
        for rank, subject_number in enumerate(importance_order or [], start=1)
    }
    now_iso = _now_iso(timezone)
    scored_subjects: list[SubjectItem] = []
    score_rows: list[dict[str, object]] = []

    for index, subject in enumerate(normalized_subjects, start=1):
        detail = details_by_number.get(index)
        perceived_difficulty = 4 if index in difficult_numbers else None
        effective_difficulty = max(
            int(subject.dificultad or 3),
            int(perceived_difficulty or subject.perceived_difficulty or 0),
        )
        score = calculate_weekly_priority_score(
            student_rank=rank_by_number.get(index),
            urgency_due_at=detail.due_at if detail else None,
            urgency_type=detail.urgency_type if detail else None,
            weekly_load_min=subject.carga_semanal_min,
            perceived_difficulty=perceived_difficulty,
            reference_date=reference_date,
        )
        updated = subject.model_copy(
            update={
                "prioridad": score.level,
                "dificultad": max(1, min(effective_difficulty, 5)),
                "urgencia": score.urgency_level,
                "origen": source,
                "importance_rank_selected_by_student": rank_by_number.get(index),
                "perceived_difficulty": perceived_difficulty,
                "urgency_type": detail.urgency_type if detail else None,
                "urgency_due_at": detail.due_at if detail else None,
                "computed_priority_score": score.score,
                "priority_source": source,
                "is_priority_confirmed": True,
                "updated_from_flow_at": now_iso,
            }
        )
        scored_subjects.append(updated)
        score_rows.append(
            {
                "subject_number": index,
                "subject_name": subject.nombre,
                "importance_rank": rank_by_number.get(index),
                "urgency_type": detail.urgency_type if detail else None,
                "urgency_due_at": detail.due_at if detail else None,
                "difficulty_selected": index in difficult_numbers,
                "score": score.score,
                "priority_level": score.level,
                "urgency_level": score.urgency_level,
                "components": score.components,
            }
        )

    scored_subjects.sort(
        key=lambda subject: (
            -(subject.computed_priority_score or 0.0),
            subject.nombre.lower(),
        )
    )
    return WeeklyPriorityResult(
        subjects=scored_subjects,
        summary={
            "source": source,
            "week_reference_date": reference_date.isoformat(),
            "importance_order": list(importance_order or []),
            "difficult_subject_numbers": list(difficult_subject_numbers or []),
            "urgency_details": [
                _urgency_detail_payload(_ensure_urgency_detail(detail))
                for detail in urgency_details
            ],
            "scores": score_rows,
        },
    )


def calculate_weekly_priority_score(
    *,
    student_rank: int | None,
    urgency_due_at: str | None,
    urgency_type: str | None,
    weekly_load_min: int | None,
    perceived_difficulty: int | None,
    reference_date: date,
    academic_rules: dict[str, object] | None = None,
) -> PriorityScoreResult:
    """Calcula prioridad semanal normalizada, explicable y testeable."""

    rules = dict(academic_rules or {})
    weights = {
        "importance": float(rules.get("importance_weight", 0.40)),
        "urgency": float(rules.get("urgency_weight", 0.30)),
        "difficulty": float(rules.get("difficulty_weight", 0.15)),
        "load": float(rules.get("load_weight", 0.15)),
    }
    importance_component = {1: 1.0, 2: 0.75, 3: 0.55}.get(student_rank or 0, 0.0)
    urgency_component, urgency_level = _urgency_component(
        urgency_due_at=urgency_due_at,
        urgency_type=urgency_type,
        reference_date=reference_date,
    )
    difficulty_component = 0.0
    if perceived_difficulty is not None:
        difficulty_component = (max(1, min(int(perceived_difficulty), 5)) - 1) / 4
    load_component = min(max(int(weekly_load_min or 0), 0) / 300, 1.0)
    score = (
        weights["importance"] * importance_component
        + weights["urgency"] * urgency_component
        + weights["difficulty"] * difficulty_component
        + weights["load"] * load_component
    )
    if urgency_level == "alta":
        score = max(score, 0.55)
        if urgency_component >= 0.95:
            score = max(score, 0.70)
    elif urgency_level == "media":
        score = max(score, 0.40)
    score = round(max(0.0, min(score, 1.0)), 3)
    if score >= 0.70:
        level: Prioridad = "alta"
    elif score >= 0.40:
        level = "media"
    else:
        level = "baja"
    return PriorityScoreResult(
        score=score,
        level=level,
        urgency_level=urgency_level,
        components={
            "importance": round(importance_component, 3),
            "urgency": round(urgency_component, 3),
            "difficulty": round(difficulty_component, 3),
            "load": round(load_component, 3),
        },
    )


def apply_academic_event_update(
    *,
    subjects: list[SubjectItem | dict],
    text: str | None,
    reference_date: date,
    timezone: str,
) -> AcademicEventUpdateResult:
    """Procesa mensajes puntuales sin rehacer el cuestionario semanal."""

    normalized_text = _normalize(text)
    normalized_subjects = ensure_subject_items(subjects)
    if not normalized_text:
        return AcademicEventUpdateResult(detected=False)

    if any(token in normalized_text for token in _MISSED_STUDY_WORDS):
        return AcademicEventUpdateResult(
            detected=True,
            event_type="missed_study",
            subjects=normalized_subjects,
            message=(
                "Entendido. Marco esto como una senal de ajuste: si me dices que bloque "
                "era, lo puedo registrar como no realizado."
            ),
            replan_required=True,
            requires_clarification=True,
            payload={"trigger": "missed_session", "raw_text": str(text or "")},
        )

    if any(token in normalized_text for token in _COMPLETION_WORDS):
        return AcademicEventUpdateResult(
            detected=True,
            event_type="completion_report",
            subjects=normalized_subjects,
            message=(
                "Listo. Para registrarlo necesito saber que bloque o tarea terminaste."
            ),
            requires_clarification=True,
            payload={"trigger": "completion_report", "raw_text": str(text or "")},
        )

    if not any(word in normalized_text for word in _ACADEMIC_EVENT_WORDS):
        return AcademicEventUpdateResult(detected=False)

    subject_number = _match_subject_number(normalized_text, normalized_subjects)
    if subject_number is None:
        return AcademicEventUpdateResult(
            detected=True,
            event_type="academic_deadline",
            subjects=normalized_subjects,
            message=(
                "Detecte una evaluacion o entrega, pero necesito la materia. "
                "Puedes responder, por ejemplo: 2 parcial viernes."
            ),
            requires_clarification=True,
            payload={"trigger": "academic_deadline", "raw_text": str(text or "")},
        )

    parsed = parse_urgency_details(
        f"{subject_number} {text or ''}",
        subject_count=len(normalized_subjects),
        reference_date=reference_date,
        timezone=timezone,
        required_subject_numbers=[subject_number],
    )
    if not parsed.is_valid:
        return AcademicEventUpdateResult(
            detected=True,
            event_type="academic_deadline",
            subjects=normalized_subjects,
            message=f"{parsed.error} Ejemplo: {subject_number} parcial viernes.",
            requires_clarification=True,
            payload={"trigger": "academic_deadline", "raw_text": str(text or "")},
        )

    detail = parsed.details[0]
    updated_subjects: list[SubjectItem] = []
    score_rows: list[dict[str, object]] = []
    now_iso = _now_iso(timezone)
    for index, subject in enumerate(normalized_subjects, start=1):
        if index != subject_number:
            updated_subjects.append(subject)
            continue
        score = calculate_weekly_priority_score(
            student_rank=subject.importance_rank_selected_by_student,
            urgency_due_at=detail.due_at,
            urgency_type=detail.urgency_type,
            weekly_load_min=subject.carga_semanal_min,
            perceived_difficulty=subject.perceived_difficulty,
            reference_date=reference_date,
        )
        updated_subject = subject.model_copy(
            update={
                "prioridad": score.level,
                "urgencia": score.urgency_level,
                "urgency_type": detail.urgency_type,
                "urgency_due_at": detail.due_at,
                "computed_priority_score": score.score,
                "priority_source": "event_update",
                "is_priority_confirmed": True,
                "updated_from_flow_at": now_iso,
            }
        )
        updated_subjects.append(updated_subject)
        score_rows.append(
            {
                "subject_number": index,
                "subject_name": subject.nombre,
                "urgency_type": detail.urgency_type,
                "urgency_due_at": detail.due_at,
                "score": score.score,
                "priority_level": score.level,
                "urgency_level": score.urgency_level,
                "components": score.components,
            }
        )
    updated_subjects.sort(
        key=lambda subject: (
            -(subject.computed_priority_score or 0.0),
            subject.nombre.lower(),
        )
    )
    updated_subject = next(
        subject
        for subject in updated_subjects
        if _normalize(subject.nombre) == _normalize(normalized_subjects[subject_number - 1].nombre)
    )
    return AcademicEventUpdateResult(
        detected=True,
        event_type="academic_deadline",
        subjects=updated_subjects,
        message=(
            f"Actualice {updated_subject.nombre}: prioridad {updated_subject.prioridad}"
            f" por {updated_subject.urgency_type}."
        ),
        replan_required=updated_subject.prioridad == "alta",
        payload={
            "trigger": "academic_deadline",
            "raw_text": str(text or ""),
            "summary": {
                "source": "event_update",
                "week_reference_date": reference_date.isoformat(),
                "scores": score_rows,
            },
        },
    )


def is_academic_update_message(text: str | None) -> bool:
    """Indica si un mensaje parece una actualizacion academica puntual."""

    normalized = _normalize(text)
    if not normalized:
        return False
    return (
        any(token in normalized for token in _MISSED_STUDY_WORDS)
        or any(token in normalized for token in _COMPLETION_WORDS)
        or any(word in normalized for word in _ACADEMIC_EVENT_WORDS)
        or any(word in normalized for word in _ACADEMIC_ACTIVITY_MANAGEMENT_WORDS)
    )


def current_week_bounds(reference_date: date) -> tuple[str, str]:
    """Retorna lunes-domingo para el snapshot semanal."""

    start = reference_date - timedelta(days=reference_date.weekday())
    end = start + timedelta(days=6)
    return start.isoformat(), end.isoformat()


def _urgency_component(
    *,
    urgency_due_at: str | None,
    urgency_type: str | None,
    reference_date: date,
) -> tuple[float, Prioridad | None]:
    if not urgency_due_at:
        return 0.0, None
    try:
        due_date = datetime.fromisoformat(str(urgency_due_at)).date()
    except ValueError:
        return 0.0, None
    days_left = (due_date - reference_date).days
    if days_left < 0:
        return 0.0, None
    if days_left <= 1:
        base = 1.0
    elif days_left <= 3:
        base = 0.85
    elif days_left <= 6:
        base = 0.60
    else:
        base = 0.25
    if urgency_type in {"parcial", "entrega"}:
        base = min(1.0, base + 0.10)
    if base >= 0.75:
        return base, "alta"
    if base >= 0.45:
        return base, "media"
    return base, "baja"


def _detect_urgency_type(text: str) -> str | None:
    normalized = _normalize(text)
    for event_type, keywords in _EVENT_TYPE_KEYWORDS.items():
        if any(keyword in normalized for keyword in keywords):
            return event_type
    return None


def _resolve_due_at(text: str, *, reference_date: date, timezone: str) -> str | None:
    normalized = _normalize(text)
    if "manana" in normalized:
        return _due_datetime(reference_date + timedelta(days=1), timezone)
    if "hoy" in normalized:
        return _due_datetime(reference_date, timezone)
    for token, weekday in _WEEKDAYS.items():
        if token not in normalized:
            continue
        days_ahead = weekday - reference_date.weekday()
        if days_ahead < 0:
            days_ahead += 7
        return _due_datetime(reference_date + timedelta(days=days_ahead), timezone)
    date_match = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", normalized)
    if date_match:
        day = int(date_match.group(1))
        month = int(date_match.group(2))
        raw_year = date_match.group(3)
        year = reference_date.year if raw_year is None else int(raw_year)
        if year < 100:
            year += 2000
        try:
            candidate = date(year, month, day)
        except ValueError:
            return None
        return _due_datetime(candidate, timezone)
    return None


def _due_datetime(value: date, timezone: str) -> str:
    try:
        zone = ZoneInfo(str(timezone or "America/Bogota"))
    except Exception:
        zone = ZoneInfo("America/Bogota")
    return datetime.combine(value, time(23, 59), tzinfo=zone).isoformat()


def _match_subject_number(text: str, subjects: list[SubjectItem]) -> int | None:
    number_match = re.search(r"\d+", text)
    if number_match:
        number = int(number_match.group(0))
        if 1 <= number <= len(subjects):
            return number
    matches = [
        index
        for index, subject in enumerate(subjects, start=1)
        if _normalize(subject.nombre) and _normalize(subject.nombre) in text
    ]
    if len(matches) == 1:
        return matches[0]
    return None


def _normalize(value: str | None) -> str:
    text = str(value or "").strip().lower()
    text = (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return " ".join(text.split())


def _ensure_urgency_detail(detail: UrgencyDetail | dict) -> UrgencyDetail:
    if isinstance(detail, UrgencyDetail):
        return detail
    return UrgencyDetail(**dict(detail))


def _detail_subject_number(detail: UrgencyDetail | dict) -> int:
    if isinstance(detail, UrgencyDetail):
        return detail.subject_number
    return int(dict(detail)["subject_number"])


def _urgency_detail_payload(detail: UrgencyDetail) -> dict[str, object]:
    return {
        "subject_number": detail.subject_number,
        "urgency_type": detail.urgency_type,
        "due_at": detail.due_at,
        "raw_text": detail.raw_text,
    }


def _now_iso(timezone: str) -> str:
    try:
        zone = ZoneInfo(str(timezone or "America/Bogota"))
    except Exception:
        zone = ZoneInfo("America/Bogota")
    return datetime.now(zone).isoformat()
