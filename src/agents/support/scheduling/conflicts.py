"""Detección determinística de cruces entre bloques recurrentes."""

from __future__ import annotations

from collections import defaultdict

from agents.support.state import normalize_time

from .constants import DAY_ORDER
from .models import ScheduleConflict, WeeklyScheduleBlock, ensure_weekly_block


def detect_schedule_conflicts(
    blocks: list[WeeklyScheduleBlock],
) -> tuple[list[WeeklyScheduleBlock], list[ScheduleConflict]]:
    """Marca y retorna los cruces detectados por día."""

    by_day: dict[str, list[WeeklyScheduleBlock]] = defaultdict(list)
    for raw_block in blocks:
        block = ensure_weekly_block(raw_block)
        by_day[block.day_of_week].append(block.model_copy(update={"has_conflict": False}))

    conflicts: list[ScheduleConflict] = []
    updated: list[WeeklyScheduleBlock] = []

    for day in DAY_ORDER:
        day_blocks = sorted(
            by_day.get(day, []),
            key=lambda item: _minutes(item.start_time),
        )
        flags: dict[str, bool] = {block.block_id: False for block in day_blocks}
        for left_index, left in enumerate(day_blocks):
            for right in day_blocks[left_index + 1 :]:
                if _minutes(right.start_time) >= _minutes(left.end_time):
                    break
                overlap_start = max(_minutes(left.start_time), _minutes(right.start_time))
                overlap_end = min(_minutes(left.end_time), _minutes(right.end_time))
                if overlap_start >= overlap_end:
                    continue
                flags[left.block_id] = True
                flags[right.block_id] = True
                conflicts.append(
                    ScheduleConflict(
                        day_of_week=day,
                        left_block_id=left.block_id,
                        right_block_id=right.block_id,
                        left_title=left.title,
                        right_title=right.title,
                        left_type=left.block_type,
                        right_type=right.block_type,
                        overlap_start=_format_minutes(overlap_start),
                        overlap_end=_format_minutes(overlap_end),
                        accepted=bool(left.conflict_accepted and right.conflict_accepted),
                    )
                )
        for block in day_blocks:
            updated.append(block.model_copy(update={"has_conflict": flags[block.block_id]}))

    return updated, conflicts


def _minutes(value: str) -> int:
    normalized = normalize_time(value)
    return int(normalized[:2]) * 60 + int(normalized[3:])


def _format_minutes(total: int) -> str:
    hour, minute = divmod(total, 60)
    return f"{hour:02d}:{minute:02d}"
