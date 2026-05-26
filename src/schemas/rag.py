"""Stable contracts for the study recommendations RAG layer."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import BaseSchemaModel

RagKnowledgeType = Literal[
    "technique",
    "study_method",
    "study_framework",
    "technique_combination_matrix",
]

RagChunkKind = Literal[
    "definition",
    "objective",
    "use_case",
    "contraindication",
    "steps",
    "quality_control",
    "adaptation",
    "combination",
    "evidence",
    "agent_guidance",
    "answer_ready",
    "comparison",
    "matrix",
    "metadata",
]

RagRetrievalRole = Literal[
    "answerable",
    "supporting_context",
    "structured_metadata",
]

DEFAULT_RAG_RETRIEVAL_ROLE: RagRetrievalRole = "answerable"
RAG_RETRIEVAL_ROLES = frozenset(
    {
        "answerable",
        "supporting_context",
        "structured_metadata",
    }
)

RagRelationType = Literal[
    "recommended_with",
    "contraindicated_with",
    "uses_component",
    "excludes",
    "routes_to",
    "compares_with",
    "supports_signal",
    "best_for_activity",
    "not_ideal_for_activity",
]

RagIssueSeverity = Literal["error", "warning"]


class RagValidationIssue(BaseSchemaModel):
    """Validation issue emitted by corpus ingestion."""

    severity: RagIssueSeverity
    code: str
    message: str
    source_path: str | None = None
    document_id: str | None = None


class RagDocumentMetadata(BaseSchemaModel):
    """Normalized metadata for a source document."""

    document_id: str
    knowledge_type: RagKnowledgeType
    document_type: str
    entity_id: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    aliases_normalized: list[str] = Field(default_factory=list)
    status: str
    version: str
    source_path: str
    checksum: str
    raw_metadata: dict[str, object] = Field(default_factory=dict)
    normalized_metadata: dict[str, object] = Field(default_factory=dict)


class NormalizedRagDocument(BaseSchemaModel):
    """Canonical form used by the local RAG ingestion pipeline."""

    document_id: str
    knowledge_type: RagKnowledgeType
    document_type: str
    entity_id: str
    title: str
    body: str
    metadata: RagDocumentMetadata


class RagChunk(BaseSchemaModel):
    """Recoverable content unit produced from a source document."""

    chunk_id: str
    document_id: str
    knowledge_type: RagKnowledgeType
    document_type: str
    entity_id: str
    section_title: str
    heading_path: list[str] = Field(default_factory=list)
    chunk_kind: RagChunkKind
    retrieval_role: RagRetrievalRole = "answerable"
    content: str
    metadata: dict[str, object] = Field(default_factory=dict)
    position_in_document: int
    token_estimate: int
    checksum: str


class RagRelation(BaseSchemaModel):
    """Light graph-aware relation extracted from metadata or chunks."""

    relation_id: str
    source_type: str
    source_id: str
    relation_type: RagRelationType
    target_type: str
    target_id: str
    weight: float = 1.0
    evidence_text: str
    source_document_id: str
    source_chunk_id: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class RagCorpusBuildResult(BaseSchemaModel):
    """Result of a local corpus build."""

    documents: list[NormalizedRagDocument] = Field(default_factory=list)
    chunks: list[RagChunk] = Field(default_factory=list)
    relations: list[RagRelation] = Field(default_factory=list)
    issues: list[RagValidationIssue] = Field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == "error" for issue in self.issues)


class StudyRecommendationQuery(BaseSchemaModel):
    """Input DTO for later retrieval and business services."""

    query_text: str = ""
    intent: str | None = None
    student_signals: list[str] = Field(default_factory=list)
    top_techniques: list[str] = Field(default_factory=list)
    subject_name: str | None = None
    subject_type: str | None = None
    activity_type: str | None = None
    available_minutes: int | None = None
    difficulty: str | None = None
    urgency: str | None = None
    preferred_language: str = "es"
    max_chunks: int = 5


class StudyRecommendationResult(BaseSchemaModel):
    """Structured output expected from later RAG-backed services."""

    answer: str
    recommended_techniques: list[str] = Field(default_factory=list)
    recommended_methods: list[str] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)
    combinations: list[list[str]] = Field(default_factory=list)
    source_chunks: list[str] = Field(default_factory=list)
    relations_used: list[str] = Field(default_factory=list)
    confidence: str = "baja"
    groundedness_notes: list[str] = Field(default_factory=list)


__all__ = [
    "DEFAULT_RAG_RETRIEVAL_ROLE",
    "NormalizedRagDocument",
    "RAG_RETRIEVAL_ROLES",
    "RagChunk",
    "RagChunkKind",
    "RagCorpusBuildResult",
    "RagDocumentMetadata",
    "RagIssueSeverity",
    "RagKnowledgeType",
    "RagRelation",
    "RagRelationType",
    "RagRetrievalRole",
    "RagValidationIssue",
    "StudyRecommendationQuery",
    "StudyRecommendationResult",
]
