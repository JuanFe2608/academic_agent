"""Servicios y contratos del dominio de scheduling."""

from .constants import (
    BLOCK_TYPE_TO_EVENT_CATEGORY,
    DAY_LABELS,
    SPANISH_TO_ENGLISH,
)
from .activity_matching import resolve_best_title_key, suggest_similar_titles
from .ai_support import (
    llm_extract_json,
    llm_extract_schedule_blocks,
    llm_normalize_extracurricular_items,
    llm_normalize_schedule,
)
from .models import (
    NormalizedScheduleResult,
    ScheduleConflict,
    ScheduleFlowState,
    WeeklyScheduleBlock,
    ensure_schedule_conflict,
    ensure_weekly_block,
)
from .service import PersistScheduleResult, ScheduleService, build_schedule_service
from .extracurricular_events import (
    build_fixed_events,
    build_tentative_events,
    generate_tentative_extracurricular,
)
from .text_parser import (
    extract_natural_schedule_components,
    is_ambiguous_time_range,
    parse_academic_schedule_text,
    parse_work_schedule_text,
)
from .validation import (
    DAY_ORDER,
    new_event_id,
    normalize_day,
    normalize_time,
    sort_events,
    validate_event,
)

__all__ = [
    "BLOCK_TYPE_TO_EVENT_CATEGORY",
    "DAY_LABELS",
    "NormalizedScheduleResult",
    "PersistScheduleResult",
    "SPANISH_TO_ENGLISH",
    "ScheduleConflict",
    "ScheduleFlowState",
    "ScheduleService",
    "WeeklyScheduleBlock",
    "DAY_ORDER",
    "build_schedule_service",
    "build_fixed_events",
    "build_tentative_events",
    "ensure_schedule_conflict",
    "ensure_weekly_block",
    "extract_natural_schedule_components",
    "generate_tentative_extracurricular",
    "is_ambiguous_time_range",
    "llm_extract_json",
    "llm_extract_schedule_blocks",
    "llm_normalize_extracurricular_items",
    "llm_normalize_schedule",
    "new_event_id",
    "parse_academic_schedule_text",
    "parse_work_schedule_text",
    "normalize_day",
    "normalize_time",
    "resolve_best_title_key",
    "sort_events",
    "suggest_similar_titles",
    "validate_event",
]
