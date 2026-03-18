"""API pública perezosa para el dominio de horarios recurrentes."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "NormalizedScheduleResult",
    "ScheduleConflict",
    "ScheduleFlowState",
    "WeeklyScheduleBlock",
    "build_conflict_message",
    "build_schedule_summary",
    "detect_schedule_conflicts",
    "merge_section_blocks",
    "normalize_schedule_section",
    "render_recurring_schedule",
    "replace_section_blocks",
]

_MODULE_BY_NAME = {
    "NormalizedScheduleResult": "agents.support.scheduling.models",
    "ScheduleConflict": "agents.support.scheduling.models",
    "ScheduleFlowState": "agents.support.scheduling.models",
    "WeeklyScheduleBlock": "agents.support.scheduling.models",
    "build_conflict_message": "agents.support.scheduling.formatter",
    "build_schedule_summary": "agents.support.scheduling.formatter",
    "detect_schedule_conflicts": "agents.support.scheduling.conflicts",
    "merge_section_blocks": "agents.support.scheduling.normalizer",
    "normalize_schedule_section": "agents.support.scheduling.normalizer",
    "render_recurring_schedule": "agents.support.scheduling.render",
    "replace_section_blocks": "agents.support.scheduling.normalizer",
}


def __getattr__(name: str) -> Any:
    module_name = _MODULE_BY_NAME.get(name)
    if not module_name:
        raise AttributeError(name)
    module = import_module(module_name)
    return getattr(module, name)
