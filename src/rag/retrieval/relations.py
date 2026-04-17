"""Relation expansion for graph-aware retrieval."""

from __future__ import annotations

from repositories.rag import RagRepository
from schemas.rag import RagRelation, StudyRecommendationQuery

from rag.ingestion.normalization import normalize_signals, slugify_identifier

from .models import QueryUnderstanding, RagRetrievedChunk

RELATION_TYPES_BY_INTENT: dict[str, list[str]] = {
    "explain_technique": ["recommended_with", "uses_component", "compares_with"],
    "recommend_technique": [
        "supports_signal",
        "best_for_activity",
        "recommended_with",
        "not_ideal_for_activity",
    ],
    "recommend_method": [
        "uses_component",
        "supports_signal",
        "best_for_activity",
        "routes_to",
    ],
    "compare_options": ["compares_with", "routes_to", "recommended_with"],
    "technique_vs_method": ["routes_to", "uses_component", "compares_with"],
    "combine_techniques": ["recommended_with", "contraindicated_with", "excludes"],
    "adapt_method": ["uses_component", "supports_signal", "best_for_activity"],
    "session_guidance": ["uses_component", "recommended_with", "best_for_activity"],
    "contraindication_check": [
        "contraindicated_with",
        "excludes",
        "not_ideal_for_activity",
    ],
}


def relation_types_for_intent(intent: str) -> list[str]:
    """Return relevant relation types for an intent."""

    return list(RELATION_TYPES_BY_INTENT.get(intent, []))


def expand_relations(
    *,
    repository: RagRepository,
    query: StudyRecommendationQuery,
    understanding: QueryUnderstanding,
    chunks: list[RagRetrievedChunk],
    limit: int = 50,
) -> list[RagRelation]:
    """Fetch explicit relations around selected chunks and query constraints."""

    entity_ids = _relation_entity_ids(query, understanding, chunks)
    if not entity_ids:
        return []
    return repository.list_relations_for_entities(
        entity_ids=entity_ids,
        relation_types=understanding.relation_types or None,
        limit=limit,
    )


def _relation_entity_ids(
    query: StudyRecommendationQuery,
    understanding: QueryUnderstanding,
    chunks: list[RagRetrievedChunk],
) -> list[str]:
    values: list[str] = []
    values.extend(understanding.detected_entities)
    values.extend(understanding.detected_signals)
    values.extend(normalize_signals(query.student_signals))
    values.extend(chunk.entity_id for chunk in chunks[:10])
    if query.activity_type:
        values.append(slugify_identifier(query.activity_type))
    if query.subject_type:
        values.append(slugify_identifier(query.subject_type))
    return _unique(values)


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            unique.append(value)
    return unique


__all__ = [
    "RELATION_TYPES_BY_INTENT",
    "expand_relations",
    "relation_types_for_intent",
]
