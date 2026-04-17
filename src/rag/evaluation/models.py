"""Contracts for offline RAG evaluation."""

from __future__ import annotations

from pydantic import Field

from schemas.common import BaseSchemaModel
from schemas.rag import StudyRecommendationQuery


class RagEvalCase(BaseSchemaModel):
    """One curated evaluation case for study recommendation RAG."""

    eval_id: str
    category: str
    query: str
    intent: str | None = None
    student_signals: list[str] = Field(default_factory=list)
    top_techniques: list[str] = Field(default_factory=list)
    subject_name: str | None = None
    subject_type: str | None = None
    activity_type: str | None = None
    available_minutes: int | None = None
    difficulty: str | None = None
    urgency: str | None = None
    expected_entities: list[str] = Field(default_factory=list)
    expected_chunk_kinds: list[str] = Field(default_factory=list)
    expected_relation_types: list[str] = Field(default_factory=list)
    expected_answer_terms: list[str] = Field(default_factory=list)
    forbidden_entities: list[str] = Field(default_factory=list)
    forbidden_answer_terms: list[str] = Field(default_factory=list)
    require_sources: bool = True
    expect_caution: bool = False
    notes: str = ""

    def to_query(self) -> StudyRecommendationQuery:
        """Convert the eval row to the public service DTO."""

        return StudyRecommendationQuery(
            query_text=self.query,
            intent=self.intent,
            student_signals=list(self.student_signals),
            top_techniques=list(self.top_techniques),
            subject_name=self.subject_name,
            subject_type=self.subject_type,
            activity_type=self.activity_type,
            available_minutes=self.available_minutes,
            difficulty=self.difficulty,
            urgency=self.urgency,
            max_chunks=5,
        )


class RagEvalCaseResult(BaseSchemaModel):
    """Measured result for one eval case."""

    eval_id: str
    category: str
    intent: str
    passed: bool
    latency_ms: float
    expected_entities: list[str] = Field(default_factory=list)
    retrieved_entities: list[str] = Field(default_factory=list)
    recommended_entities: list[str] = Field(default_factory=list)
    expected_entity_hits: list[str] = Field(default_factory=list)
    forbidden_entity_hits: list[str] = Field(default_factory=list)
    selected_chunk_ids: list[str] = Field(default_factory=list)
    selected_chunk_kinds: list[str] = Field(default_factory=list)
    expected_chunk_kind_hits: list[str] = Field(default_factory=list)
    relation_types: list[str] = Field(default_factory=list)
    expected_relation_type_hits: list[str] = Field(default_factory=list)
    source_chunks: list[str] = Field(default_factory=list)
    confidence: str = "baja"
    groundedness_notes: list[str] = Field(default_factory=list)
    answer: str = ""
    expect_caution: bool = False
    entity_recall_at_k: float = 0.0
    entity_precision_at_k: float = 0.0
    reciprocal_rank: float = 0.0
    chunk_kind_recall: float = 0.0
    groundedness_ok: bool = False
    caution_ok: bool = True
    answer_terms_ok: bool = True
    forbidden_terms_ok: bool = True
    failure_reasons: list[str] = Field(default_factory=list)


class RagEvalMetrics(BaseSchemaModel):
    """Aggregate metrics for a RAG evaluation run."""

    total_cases: int = 0
    passed_cases: int = 0
    pass_rate: float = 0.0
    entity_recall_at_k: float = 0.0
    entity_precision_at_k: float = 0.0
    mrr: float = 0.0
    chunk_kind_recall: float = 0.0
    groundedness_rate: float = 0.0
    caution_success_rate: float = 0.0
    forbidden_entity_violations: int = 0
    forbidden_answer_term_violations: int = 0
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    latency_max_ms: float = 0.0
    by_category: dict[str, dict[str, float]] = Field(default_factory=dict)


class RagEvaluationReport(BaseSchemaModel):
    """Full serializable report emitted by the offline runner."""

    backend: str
    dataset_path: str
    metrics: RagEvalMetrics
    cases: list[RagEvalCaseResult] = Field(default_factory=list)
    disabled_fallback: dict[str, float | int] | None = None


__all__ = [
    "RagEvalCase",
    "RagEvalCaseResult",
    "RagEvalMetrics",
    "RagEvaluationReport",
]
