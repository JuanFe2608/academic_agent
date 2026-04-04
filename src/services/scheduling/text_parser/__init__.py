"""Parsers de texto para horarios académicos y laborales."""

from ._common import extract_natural_schedule_components, is_ambiguous_time_range
from .academic import parse_academic_schedule_text
from .work import parse_work_schedule_text

__all__ = [
    "extract_natural_schedule_components",
    "is_ambiguous_time_range",
    "parse_academic_schedule_text",
    "parse_work_schedule_text",
]

