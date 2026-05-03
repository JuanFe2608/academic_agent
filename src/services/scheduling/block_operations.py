"""Operaciones puras sobre bloques recurrentes de horario.

Estas funciones no conocen LangGraph ni el estado conversacional. Su objetivo
es encapsular mutaciones reutilizables sobre `WeeklyScheduleBlock` para que los
flows de `agents/support` dependan menos de lógica estructural dispersa.
"""

from __future__ import annotations

import re
import unicodedata

from services.scheduling.constants import ScheduleBlockType
from services.scheduling.models import WeeklyScheduleBlock, ensure_weekly_block

_TITLE_STOPWORDS = {
    "and",
    "con",
    "de",
    "del",
    "e",
    "el",
    "la",
    "las",
    "los",
    "of",
    "para",
    "the",
    "ti",
    "with",
    "y",
}
_TITLE_SYNONYMS = {
    "ai": "intelligence",
    "artificial": "intelligence",
    "ia": "intelligence",
    "problema": "problem",
    "problemas": "problem",
    "problems": "problem",
    "solucion": "solution",
    "solution": "solution",
}


def current_section_blocks(
    existing: list[WeeklyScheduleBlock] | list[dict],
    block_type: ScheduleBlockType,
) -> list[WeeklyScheduleBlock]:
    """Retorna solo los bloques de una sección concreta del horario."""

    return [
        ensure_weekly_block(block)
        for block in existing
        if ensure_weekly_block(block).block_type == block_type
    ]


def merge_section_blocks(
    existing: list[WeeklyScheduleBlock] | list[dict],
    new_blocks: list[WeeklyScheduleBlock] | list[dict],
) -> list[WeeklyScheduleBlock]:
    """Agrega bloques a una sección eliminando duplicados exactos."""

    merged = [ensure_weekly_block(block) for block in existing] + [
        ensure_weekly_block(block) for block in new_blocks
    ]
    return _dedupe_blocks(merged)


def replace_section_blocks(
    existing: list[WeeklyScheduleBlock] | list[dict],
    block_type: ScheduleBlockType,
    new_blocks: list[WeeklyScheduleBlock] | list[dict],
) -> list[WeeklyScheduleBlock]:
    """Reemplaza por completo una sección del horario."""

    kept = [
        ensure_weekly_block(block)
        for block in existing
        if ensure_weekly_block(block).block_type != block_type
    ]
    normalized_new = [ensure_weekly_block(block) for block in new_blocks]
    return _dedupe_blocks(kept + normalized_new)


def _dedupe_blocks(blocks: list[WeeklyScheduleBlock]) -> list[WeeklyScheduleBlock]:
    deduped: list[WeeklyScheduleBlock] = []
    for raw_block in blocks:
        block = ensure_weekly_block(raw_block)
        duplicate_index = _find_duplicate_index(deduped, block)
        if duplicate_index is None:
            deduped.append(block)
            continue
        preferred = _prefer_more_specific_block(deduped[duplicate_index], block)
        deduped[duplicate_index] = preferred
    return deduped


def _find_duplicate_index(
    existing_blocks: list[WeeklyScheduleBlock],
    candidate: WeeklyScheduleBlock,
) -> int | None:
    for index, existing in enumerate(existing_blocks):
        if _blocks_are_duplicates(existing, candidate):
            return index
    return None


def _blocks_are_duplicates(left: WeeklyScheduleBlock, right: WeeklyScheduleBlock) -> bool:
    if (
        left.block_type != right.block_type
        or left.day_of_week != right.day_of_week
        or left.start_time != right.start_time
        or left.end_time != right.end_time
    ):
        return False

    left_key = _title_key(left.title)
    right_key = _title_key(right.title)
    if not left_key or not right_key:
        return left_key == right_key
    if left_key == right_key:
        return True

    left_tokens = set(left_key.split())
    right_tokens = set(right_key.split())
    shorter, longer = (
        (left_tokens, right_tokens)
        if len(left_tokens) <= len(right_tokens)
        else (right_tokens, left_tokens)
    )
    return bool(shorter) and shorter.issubset(longer)


def _prefer_more_specific_block(
    left: WeeklyScheduleBlock,
    right: WeeklyScheduleBlock,
) -> WeeklyScheduleBlock:
    left_score = _title_specificity_score(left.title)
    right_score = _title_specificity_score(right.title)
    return right if right_score > left_score else left


def _title_specificity_score(title: str) -> tuple[int, int]:
    key = _title_key(title)
    return (len(key.split()), len(str(title or "").strip()))


def _title_key(title: str) -> str:
    folded = (
        unicodedata.normalize("NFKD", str(title or ""))
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    tokens = re.findall(r"[a-z0-9]+", folded.lower())
    canonical_tokens = [
        _TITLE_SYNONYMS.get(token, token)
        for token in tokens
        if token not in _TITLE_STOPWORDS
    ]
    return " ".join(canonical_tokens)


__all__ = [
    "current_section_blocks",
    "merge_section_blocks",
    "replace_section_blocks",
]
