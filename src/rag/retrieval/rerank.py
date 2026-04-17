"""Deterministic reranking for hybrid RAG retrieval."""

from __future__ import annotations

from dataclasses import replace

from repositories.rag import RagChunkSearchResult
from schemas.rag import RagRelation, StudyRecommendationQuery

from rag.ingestion.normalization import normalize_signals, slugify_identifier

from .models import QueryUnderstanding, RagRetrievedChunk

CHUNK_KIND_BOOSTS: dict[str, dict[str, float]] = {
    "explain_technique": {
        "answer_ready": 0.55,
        "definition": 0.45,
        "use_case": 0.25,
        "agent_guidance": 0.20,
    },
    "recommend_technique": {
        "answer_ready": 0.55,
        "agent_guidance": 0.45,
        "use_case": 0.35,
        "adaptation": 0.25,
        "quality_control": 0.20,
    },
    "recommend_method": {
        "answer_ready": 0.55,
        "agent_guidance": 0.45,
        "use_case": 0.30,
        "adaptation": 0.25,
        "steps": 0.20,
    },
    "session_guidance": {
        "steps": 0.55,
        "agent_guidance": 0.45,
        "answer_ready": 0.35,
        "quality_control": 0.25,
    },
    "combine_techniques": {
        "combination": 0.55,
        "matrix": 0.45,
        "contraindication": 0.35,
        "agent_guidance": 0.25,
    },
    "contraindication_check": {
        "contraindication": 0.60,
        "combination": 0.35,
        "quality_control": 0.30,
        "agent_guidance": 0.20,
    },
    "compare_options": {
        "comparison": 0.55,
        "matrix": 0.45,
        "answer_ready": 0.30,
        "agent_guidance": 0.20,
    },
    "technique_vs_method": {
        "comparison": 0.55,
        "definition": 0.35,
        "answer_ready": 0.30,
        "agent_guidance": 0.20,
    },
    "adapt_method": {
        "adaptation": 0.55,
        "steps": 0.35,
        "agent_guidance": 0.30,
        "answer_ready": 0.25,
    },
}

CONFIDENCE_BOOSTS = {
    "alto": 0.25,
    "alta": 0.25,
    "medio": 0.12,
    "media": 0.12,
    "bajo": -0.05,
    "baja": -0.05,
}

EVIDENCE_BOOSTS = {
    "alto": 0.25,
    "alta": 0.25,
    "solido": 0.25,
    "solida": 0.25,
    "medio": 0.12,
    "media": 0.12,
    "mixto": 0.08,
    "mixta": 0.08,
    "bajo": -0.05,
    "baja": -0.05,
}


def merge_search_results(
    *,
    vector_results: list[RagChunkSearchResult],
    lexical_results: list[RagChunkSearchResult],
) -> list[RagRetrievedChunk]:
    """Merge vector and lexical results by chunk ID."""

    merged: dict[str, RagRetrievedChunk] = {}
    for result in vector_results:
        merged[result.chunk_id] = _from_search_result(
            result,
            semantic_score=result.semantic_score,
            source="vector",
        )
    for result in lexical_results:
        existing = merged.get(result.chunk_id)
        if existing is None:
            merged[result.chunk_id] = _from_search_result(
                result,
                lexical_score=result.lexical_score,
                source="lexical",
            )
            continue
        merged[result.chunk_id] = replace(
            existing,
            lexical_score=max(existing.lexical_score, result.lexical_score),
            semantic_score=max(existing.semantic_score, result.semantic_score),
            retrieval_sources=_merge_tuple(existing.retrieval_sources, "lexical"),
        )
    return list(merged.values())


def rerank_candidates(
    *,
    candidates: list[RagRetrievedChunk],
    query: StudyRecommendationQuery,
    understanding: QueryUnderstanding,
    relations: list[RagRelation] | None = None,
) -> list[RagRetrievedChunk]:
    """Apply deterministic domain ranking to candidate chunks."""

    ranked = [
        _score_candidate(
            candidate,
            query=query,
            understanding=understanding,
            relations=relations or [],
        )
        for candidate in candidates
    ]
    return sorted(
        ranked,
        key=lambda item: (
            item.final_score,
            item.semantic_score,
            item.lexical_score,
            -item.token_estimate,
            item.chunk_id,
        ),
        reverse=True,
    )


def _score_candidate(
    candidate: RagRetrievedChunk,
    *,
    query: StudyRecommendationQuery,
    understanding: QueryUnderstanding,
    relations: list[RagRelation],
) -> RagRetrievedChunk:
    notes: list[str] = list(candidate.ranking_notes)
    semantic = max(0.0, candidate.semantic_score)
    lexical = min(max(0.0, candidate.lexical_score), 2.0)
    metadata_score, metadata_notes = _metadata_match_score(candidate, query, understanding)
    notes.extend(metadata_notes)
    chunk_kind_boost = CHUNK_KIND_BOOSTS.get(understanding.intent, {}).get(
        candidate.chunk_kind,
        0.0,
    )
    if chunk_kind_boost:
        notes.append(f"chunk_kind:{candidate.chunk_kind}")
    relation_boost, relation_penalty, relation_notes = _relation_scores(
        candidate,
        query=query,
        understanding=understanding,
        relations=relations,
    )
    notes.extend(relation_notes)
    evidence_boost = _evidence_boost(candidate.metadata)
    contraindication_penalty = _metadata_penalty(candidate, query, understanding) + relation_penalty
    if contraindication_penalty:
        notes.append("penalty:contraindication_or_not_ideal")
    final_score = (
        semantic
        + (lexical * 1.15)
        + metadata_score
        + chunk_kind_boost
        + relation_boost
        + evidence_boost
        - contraindication_penalty
    )
    return replace(
        candidate,
        metadata_score=round(metadata_score, 6),
        chunk_kind_boost=round(chunk_kind_boost, 6),
        relation_boost=round(relation_boost, 6),
        evidence_boost=round(evidence_boost, 6),
        contraindication_penalty=round(contraindication_penalty, 6),
        final_score=round(final_score, 6),
        ranking_notes=tuple(_unique(notes)),
    )


def _metadata_match_score(
    candidate: RagRetrievedChunk,
    query: StudyRecommendationQuery,
    understanding: QueryUnderstanding,
) -> tuple[float, list[str]]:
    score = 0.0
    notes: list[str] = []
    if candidate.entity_id in understanding.detected_entities:
        score += 0.80
        notes.append(f"entity:{candidate.entity_id}")
    normalized_top = [slugify_identifier(item) for item in query.top_techniques]
    if candidate.entity_id in normalized_top:
        score += 0.45
        notes.append(f"top_technique:{candidate.entity_id}")
    activity_type = slugify_identifier(query.activity_type or "")
    if activity_type and activity_type in _metadata_list(candidate.metadata, "best_for_activity_types"):
        score += 0.35
        notes.append(f"activity:{activity_type}")
    subject_type = slugify_identifier(query.subject_type or "")
    if subject_type and subject_type in _metadata_list(candidate.metadata, "best_for_subject_types"):
        score += 0.30
        notes.append(f"subject:{subject_type}")
    signal_matches = set(understanding.detected_signals) & set(
        _metadata_list(candidate.metadata, "best_for_signals")
    )
    if signal_matches:
        score += min(0.75, 0.25 * len(signal_matches))
        notes.append("signals:" + ",".join(sorted(signal_matches)))
    return score, notes


def _metadata_penalty(
    candidate: RagRetrievedChunk,
    query: StudyRecommendationQuery,
    understanding: QueryUnderstanding,
) -> float:
    penalty = 0.0
    activity_type = slugify_identifier(query.activity_type or "")
    if activity_type and activity_type in _metadata_list(
        candidate.metadata,
        "not_ideal_for_activity_types",
    ):
        penalty += 0.70
    subject_type = slugify_identifier(query.subject_type or "")
    if subject_type and subject_type in _metadata_list(
        candidate.metadata,
        "not_ideal_for_subject_types",
    ):
        penalty += 0.50
    signal_matches = set(understanding.detected_signals) & set(
        _metadata_list(candidate.metadata, "not_ideal_for_signals")
    )
    if signal_matches:
        penalty += min(0.60, 0.30 * len(signal_matches))
    return penalty


def _relation_scores(
    candidate: RagRetrievedChunk,
    *,
    query: StudyRecommendationQuery,
    understanding: QueryUnderstanding,
    relations: list[RagRelation],
) -> tuple[float, float, list[str]]:
    boost = 0.0
    penalty = 0.0
    notes: list[str] = []
    related = [
        relation
        for relation in relations
        if relation.source_id == candidate.entity_id or relation.target_id == candidate.entity_id
    ]
    activity_type = slugify_identifier(query.activity_type or "")
    query_entities = set(understanding.detected_entities)
    query_signals = set(normalize_signals(query.student_signals)) | set(
        understanding.detected_signals
    )
    for relation in related:
        if relation.relation_type in {"recommended_with", "uses_component", "routes_to"}:
            boost += 0.18 * relation.weight
            notes.append(f"relation:{relation.relation_type}")
        if relation.relation_type == "supports_signal" and relation.target_id in query_signals:
            boost += 0.30 * relation.weight
            notes.append(f"relation_signal:{relation.target_id}")
        if relation.relation_type == "best_for_activity" and relation.target_id == activity_type:
            boost += 0.30 * relation.weight
            notes.append(f"relation_activity:{relation.target_id}")
        if relation.relation_type == "not_ideal_for_activity" and relation.target_id == activity_type:
            penalty += 0.60 * relation.weight
            notes.append(f"relation_not_ideal:{relation.target_id}")
        if relation.relation_type in {"contraindicated_with", "excludes"}:
            pair = {relation.source_id, relation.target_id}
            if query_entities and len(pair & query_entities) >= 2:
                penalty += 1.0 * relation.weight
                notes.append(f"relation_block:{relation.relation_type}")
            elif understanding.intent == "contraindication_check":
                boost += 0.25 * relation.weight
                notes.append(f"relation_check:{relation.relation_type}")
    return boost, penalty, notes


def _evidence_boost(metadata: dict[str, object]) -> float:
    confidence = slugify_identifier(str(metadata.get("confidence_level") or ""))
    evidence = slugify_identifier(str(metadata.get("evidence_level") or ""))
    return CONFIDENCE_BOOSTS.get(confidence, 0.0) + EVIDENCE_BOOSTS.get(evidence, 0.0)


def _metadata_list(metadata: dict[str, object], key: str) -> list[str]:
    value = metadata.get(key)
    if isinstance(value, list):
        return [slugify_identifier(str(item)) for item in value if str(item).strip()]
    if value is None:
        return []
    return [slugify_identifier(str(value))]


def _from_search_result(
    result: RagChunkSearchResult,
    *,
    source: str,
    semantic_score: float = 0.0,
    lexical_score: float = 0.0,
) -> RagRetrievedChunk:
    return RagRetrievedChunk(
        chunk_id=result.chunk_id,
        document_id=result.document_id,
        knowledge_type=result.knowledge_type,
        document_type=result.document_type,
        entity_id=result.entity_id,
        section_title=result.section_title,
        chunk_kind=result.chunk_kind,
        content=result.content,
        metadata=dict(result.metadata),
        token_estimate=result.token_estimate,
        semantic_score=semantic_score,
        lexical_score=lexical_score,
        retrieval_sources=(source,),
    )


def _merge_tuple(values: tuple[str, ...], value: str) -> tuple[str, ...]:
    if value in values:
        return values
    return (*values, value)


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            unique.append(value)
    return unique


__all__ = [
    "CHUNK_KIND_BOOSTS",
    "merge_search_results",
    "rerank_candidates",
]
