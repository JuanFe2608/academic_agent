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
from .correction_sync import (
    FixedSectionSyncResult,
    merge_completed_fixed_section,
    replace_fixed_section,
    sync_fixed_section_result,
)
from .contextual_schedule_parsing import (
    complete_pending_schedule_item,
    parse_schedule_section_with_context,
)
from .block_operations import (
    current_section_blocks,
    merge_section_blocks,
    replace_section_blocks,
)
from .extracurricular_state import (
    build_extracurricular_item_source_text,
    build_extracurricular_items_source_text,
    build_extracurricular_reply_hint,
    coerce_extracurricular_pending_items,
    merge_extracurricular_items,
)
from .extracurricular_parsing import (
    complete_pending_extracurricular_item,
    parse_extracurricular_items,
    parse_extracurricular_items_with_context,
    parse_extracurricular_text,
)
from .event_projection import (
    SCHEDULE_BLOCK_EVENT_ID_PREFIX,
    SCHEDULE_BLOCK_EVENT_ORIGIN,
    blocks_to_schedule_events,
    build_schedule_block_event,
    schedule_block_event_id,
    sync_schedule_block_events,
)
from .service import PersistScheduleResult, ScheduleService, build_schedule_service
from .extracurricular_events import (
    build_fixed_events,
    build_tentative_events,
    generate_tentative_extracurricular,
)
from .pending_schedule_support import (
    build_schedule_pending_prompt,
    coerce_pending_schedule_items,
)
from .parsing_results import SectionPipelineResult
from .raw_input_sync import (
    ensure_raw_inputs,
    serialize_blocks_for_schedule_type,
    sync_schedule_blocks_to_raw_inputs,
)
from .section_mutations import (
    SectionMergeResult,
    append_section_blocks,
    merge_completed_section_blocks,
)
from .text_parser import (
    extract_natural_schedule_components,
    is_ambiguous_time_range,
    parse_academic_schedule_text,
    parse_work_schedule_text,
)
from .title_normalization import normalize_schedule_title
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
    "FixedSectionSyncResult",
    "NormalizedScheduleResult",
    "PersistScheduleResult",
    "SPANISH_TO_ENGLISH",
    "ScheduleConflict",
    "ScheduleFlowState",
    "ScheduleService",
    "SectionPipelineResult",
    "WeeklyScheduleBlock",
    "DAY_ORDER",
    "SCHEDULE_BLOCK_EVENT_ID_PREFIX",
    "SCHEDULE_BLOCK_EVENT_ORIGIN",
    "SectionMergeResult",
    "append_section_blocks",
    "blocks_to_schedule_events",
    "build_extracurricular_item_source_text",
    "build_extracurricular_items_source_text",
    "build_extracurricular_reply_hint",
    "build_schedule_pending_prompt",
    "build_schedule_block_event",
    "build_schedule_service",
    "build_fixed_events",
    "build_tentative_events",
    "complete_pending_extracurricular_item",
    "complete_pending_schedule_item",
    "coerce_extracurricular_pending_items",
    "coerce_pending_schedule_items",
    "current_section_blocks",
    "ensure_raw_inputs",
    "ensure_schedule_conflict",
    "ensure_weekly_block",
    "extract_natural_schedule_components",
    "generate_tentative_extracurricular",
    "is_ambiguous_time_range",
    "merge_completed_fixed_section",
    "merge_completed_section_blocks",
    "merge_extracurricular_items",
    "merge_section_blocks",
    "llm_extract_json",
    "llm_extract_schedule_blocks",
    "llm_normalize_extracurricular_items",
    "llm_normalize_schedule",
    "normalize_schedule_title",
    "new_event_id",
    "replace_fixed_section",
    "replace_section_blocks",
    "parse_academic_schedule_text",
    "parse_extracurricular_items",
    "parse_extracurricular_items_with_context",
    "parse_extracurricular_text",
    "parse_schedule_section_with_context",
    "parse_work_schedule_text",
    "normalize_day",
    "normalize_time",
    "resolve_best_title_key",
    "schedule_block_event_id",
    "serialize_blocks_for_schedule_type",
    "sort_events",
    "suggest_similar_titles",
    "sync_schedule_block_events",
    "sync_fixed_section_result",
    "sync_schedule_blocks_to_raw_inputs",
    "validate_event",
]
