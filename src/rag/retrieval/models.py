"""Internal contracts for RAG retrieval."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from schemas.rag import RagRelation, StudyRecommendationQuery

RagQueryIntent = Literal[
    "explain_technique",
    "recommend_technique",
    "recommend_method",
    "compare_options",
    "technique_vs_method",
    "combine_techniques",
    "adapt_method",
    "session_guidance",
    "contraindication_check",
]

KNOWN_QUERY_INTENTS: set[str] = {
    "explain_technique",
    "recommend_technique",
    "recommend_method",
    "compare_options",
    "technique_vs_method",
    "combine_techniques",
    "adapt_method",
    "session_guidance",
    "contraindication_check",
}


@dataclass(frozen=True)
class QueryUnderstanding:
    """Rule-based interpretation of a RAG query."""

    intent: str
    query_text: str
    filters: dict[str, list[str]] = field(default_factory=dict)
    detected_entities: list[str] = field(default_factory=list)
    detected_techniques: list[str] = field(default_factory=list)
    detected_methods: list[str] = field(default_factory=list)
    detected_signals: list[str] = field(default_factory=list)
    desired_chunk_kinds: list[str] = field(default_factory=list)
    relation_types: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RagRetrievedChunk:
    """Candidate chunk with merged retrieval and ranking signals."""

    chunk_id: str
    document_id: str
    knowledge_type: str
    document_type: str
    entity_id: str
    section_title: str
    chunk_kind: str
    content: str
    metadata: dict[str, object]
    token_estimate: int
    retrieval_role: str = "answerable"
    semantic_score: float = 0.0
    lexical_score: float = 0.0
    metadata_score: float = 0.0
    chunk_kind_boost: float = 0.0
    relation_boost: float = 0.0
    evidence_boost: float = 0.0
    contraindication_penalty: float = 0.0
    final_score: float = 0.0
    retrieval_sources: tuple[str, ...] = field(default_factory=tuple)
    ranking_notes: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RagCitation:
    """Minimal citation for grounded assembly."""

    document_id: str
    chunk_id: str
    section_title: str
    source_path: str | None = None


@dataclass(frozen=True)
class GroundedContextPackage:
    """Context selected by retrieval before response generation."""

    query: StudyRecommendationQuery
    understanding: QueryUnderstanding
    selected_chunks: list[RagRetrievedChunk] = field(default_factory=list)
    relations: list[RagRelation] = field(default_factory=list)
    citations: list[RagCitation] = field(default_factory=list)
    groundedness_notes: list[str] = field(default_factory=list)

    @property
    def has_sufficient_sources(self) -> bool:
        return bool(self.selected_chunks)


__all__ = [
    "GroundedContextPackage",
    "KNOWN_QUERY_INTENTS",
    "QueryUnderstanding",
    "RagCitation",
    "RagQueryIntent",
    "RagRetrievedChunk",
]
