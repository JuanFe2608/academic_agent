"""Filter construction for structured RAG retrieval."""

from __future__ import annotations

from schemas.rag import StudyRecommendationQuery

from .models import QueryUnderstanding

CHUNK_KINDS_BY_INTENT: dict[str, list[str]] = {
    "explain_technique": ["answer_ready", "definition", "use_case", "agent_guidance"],
    "recommend_technique": [
        "answer_ready",
        "agent_guidance",
        "use_case",
        "adaptation",
        "quality_control",
    ],
    "recommend_method": [
        "answer_ready",
        "agent_guidance",
        "use_case",
        "adaptation",
        "steps",
    ],
    "compare_options": ["comparison", "matrix", "answer_ready", "agent_guidance"],
    "technique_vs_method": ["comparison", "definition", "answer_ready", "agent_guidance"],
    "combine_techniques": ["combination", "matrix", "contraindication", "agent_guidance"],
    "adapt_method": ["adaptation", "steps", "agent_guidance", "answer_ready"],
    "session_guidance": ["steps", "agent_guidance", "answer_ready", "quality_control"],
    "contraindication_check": [
        "contraindication",
        "combination",
        "quality_control",
        "agent_guidance",
    ],
}

KNOWLEDGE_TYPES_BY_INTENT: dict[str, list[str]] = {
    "explain_technique": ["technique", "study_method", "study_framework"],
    "recommend_technique": ["technique"],
    "recommend_method": ["study_method"],
    "compare_options": [
        "technique",
        "study_method",
        "study_framework",
        "technique_combination_matrix",
    ],
    "technique_vs_method": ["technique", "study_method", "study_framework"],
    "combine_techniques": ["technique", "study_method", "technique_combination_matrix"],
    "adapt_method": ["study_method", "technique"],
    "session_guidance": ["technique", "study_method"],
    "contraindication_check": ["technique", "study_method", "technique_combination_matrix"],
}


def build_structural_filters(
    query: StudyRecommendationQuery,
    understanding: QueryUnderstanding,
    *,
    strict: bool,
) -> dict[str, list[str]]:
    """Build DB-level filters that reduce noise without encoding all ranking rules."""

    filters: dict[str, list[str]] = {}
    knowledge_types = KNOWLEDGE_TYPES_BY_INTENT.get(understanding.intent, [])
    if knowledge_types:
        filters["knowledge_types"] = knowledge_types

    chunk_kinds = CHUNK_KINDS_BY_INTENT.get(understanding.intent, [])
    if strict and chunk_kinds:
        filters["chunk_kinds"] = chunk_kinds

    if understanding.detected_entities:
        filters["entity_ids"] = understanding.detected_entities
    elif strict and query.top_techniques and understanding.intent in {
        "explain_technique",
        "session_guidance",
        "contraindication_check",
    }:
        filters["entity_ids"] = list(query.top_techniques)

    return {key: _unique(values) for key, values in filters.items() if values}


def relaxed_filter_sets(
    query: StudyRecommendationQuery,
    understanding: QueryUnderstanding,
) -> list[dict[str, list[str]]]:
    """Return strict-to-relaxed filter attempts for controlled degradation."""

    strict = build_structural_filters(query, understanding, strict=True)
    relaxed = build_structural_filters(query, understanding, strict=False)
    broad = dict(relaxed)
    broad.pop("entity_ids", None)
    attempts = [strict, relaxed, broad, {}]
    unique_attempts: list[dict[str, list[str]]] = []
    seen: set[tuple[tuple[str, tuple[str, ...]], ...]] = set()
    for filters in attempts:
        key = tuple(sorted((name, tuple(values)) for name, values in filters.items()))
        if key in seen:
            continue
        seen.add(key)
        unique_attempts.append(filters)
    return unique_attempts


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            unique.append(value)
    return unique


__all__ = [
    "CHUNK_KINDS_BY_INTENT",
    "KNOWLEDGE_TYPES_BY_INTENT",
    "build_structural_filters",
    "relaxed_filter_sets",
]
