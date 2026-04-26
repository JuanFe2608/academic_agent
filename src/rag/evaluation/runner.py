"""Offline evaluation runner for the study recommendations RAG."""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

from bootstrap.settings import RagSettings, database_url_from_env, load_rag_settings
from integrations.embeddings import (
    EmbeddingClient,
    build_azure_openai_embedding_client_from_env,
    build_openai_embedding_client_from_env,
)
from rag.ingestion.normalization import normalize_technique_id, slugify_identifier
from rag.ingestion.pipeline import CORPUS_NAME, CORPUS_VERSION, build_rag_corpus
from rag.retrieval.hybrid import HybridRagRetriever
from rag.retrieval.models import GroundedContextPackage
from repositories.rag import (
    InMemoryRagRepository,
    RagEmbeddingUpdate,
    build_rag_repository,
)
from schemas.rag import StudyRecommendationQuery, StudyRecommendationResult
from services.study_recommendations import StudyRecommendationService

from .models import (
    RagEvalCase,
    RagEvalCaseResult,
    RagEvalMetrics,
    RagEvaluationReport,
)

DEFAULT_EVAL_DATASET_PATH = Path(
    "knowledge_base/study_recommendations/processed/evals/study_recommendation_eval_dataset.jsonl"
)

_CAUTION_TERMS = {
    "cuidado",
    "evitar",
    "no_conviene",
    "no_recomiendo",
    "no_es_ideal",
    "contraindic",
    "limite",
}


@dataclass
class EvaluationTarget:
    """Service and optional retrieval capture used by the runner."""

    backend: str
    service: StudyRecommendationService
    capture: "CapturingStudyRecommendationRetriever | None" = None


class CapturingStudyRecommendationRetriever:
    """Retriever wrapper that preserves the last package for retrieval metrics."""

    def __init__(self, retriever) -> None:
        self._retriever = retriever
        self.last_package: GroundedContextPackage | None = None

    def retrieve(self, query: StudyRecommendationQuery) -> GroundedContextPackage:
        self.last_package = self._retriever.retrieve(query)
        return self.last_package

    def reset(self) -> None:
        self.last_package = None


class DeterministicEvaluationEmbeddingClient:
    """Small local embedding client for reproducible evals without provider calls."""

    provider = "local_eval"
    model = "hash-bow"

    def __init__(self, *, dimensions: int = 64) -> None:
        self.dimensions = dimensions

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [_hash_bow_vector(text, self.dimensions) for text in texts]


def load_eval_cases(path: str | Path = DEFAULT_EVAL_DATASET_PATH) -> list[RagEvalCase]:
    """Load eval cases from JSONL or a JSON array."""

    dataset_path = Path(path)
    raw = dataset_path.read_text(encoding="utf-8").strip()
    if not raw:
        return []
    if raw.startswith("["):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON array in {dataset_path}: {exc}") from exc
        return [RagEvalCase.model_validate(item) for item in payload]
    cases: list[RagEvalCase] = []
    for line_number, line in enumerate(raw.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            cases.append(RagEvalCase.model_validate_json(stripped))
        except ValueError as exc:
            raise ValueError(
                f"Invalid eval case JSON at {dataset_path}:{line_number}: {exc}"
            ) from exc
    return cases


def build_local_evaluation_target(
    *,
    corpus_root: str | Path = "knowledge_base/study_recommendations",
    settings: RagSettings | None = None,
) -> EvaluationTarget:
    """Build a fully local RAG target using the same retrieval and service layers."""

    result = build_rag_corpus(corpus_root)
    if result.has_errors:
        messages = "; ".join(issue.message for issue in result.issues)
        raise ValueError(f"Cannot evaluate invalid RAG corpus: {messages}")

    repository = InMemoryRagRepository()
    repository.sync_corpus_snapshot(
        corpus_name=CORPUS_NAME,
        corpus_version=CORPUS_VERSION,
        source_root=Path(corpus_root).as_posix(),
        documents=result.documents,
        chunks=result.chunks,
        relations=result.relations,
        run_id="local-evaluation",
        metadata={"source": "rag.evaluation"},
    )
    embedding_client = DeterministicEvaluationEmbeddingClient()
    _embed_local_repository(repository, embedding_client)

    eval_settings = settings or RagSettings(
        enabled=True,
        embedding_provider=embedding_client.provider,
        embedding_model=embedding_client.model,
        embedding_dimensions=embedding_client.dimensions,
        top_k_vector=10,
        top_k_lexical=10,
        top_k_final=5,
        min_score=0.0,
    )
    capture = CapturingStudyRecommendationRetriever(
        HybridRagRetriever(
            repository=repository,
            embedding_client=embedding_client,
            settings=eval_settings,
        )
    )
    return EvaluationTarget(
        backend="local",
        service=StudyRecommendationService(settings=eval_settings, retriever=capture),
        capture=capture,
    )


def build_postgres_evaluation_target() -> EvaluationTarget:
    """Build a PostgreSQL-backed evaluation target with the configured provider."""

    settings = replace(load_rag_settings(), enabled=True)
    repository = build_rag_repository(database_url_from_env())
    embedding_client = _build_embedding_client(settings)
    capture = CapturingStudyRecommendationRetriever(
        HybridRagRetriever(
            repository=repository,
            embedding_client=embedding_client,
            settings=settings,
        )
    )
    return EvaluationTarget(
        backend="postgres",
        service=StudyRecommendationService(settings=settings, retriever=capture),
        capture=capture,
    )


def evaluate_cases(
    cases: list[RagEvalCase],
    *,
    target: EvaluationTarget,
    dataset_path: str | Path = DEFAULT_EVAL_DATASET_PATH,
) -> RagEvaluationReport:
    """Run curated cases through the service and compute retrieval-quality metrics."""

    results: list[RagEvalCaseResult] = []
    for case in cases:
        if target.capture is not None:
            target.capture.reset()
        query = case.to_query()
        started = time.perf_counter()
        result = target.service.answer_query(query)
        latency_ms = (time.perf_counter() - started) * 1000
        package = target.capture.last_package if target.capture is not None else None
        results.append(_evaluate_case(case, result, package, latency_ms=latency_ms))
    return RagEvaluationReport(
        backend=target.backend,
        dataset_path=Path(dataset_path).as_posix(),
        metrics=_aggregate_metrics(results),
        cases=results,
    )


def evaluate_disabled_fallback(cases: list[RagEvalCase]) -> dict[str, float | int]:
    """Verify that RAG-disabled mode returns controlled fallbacks."""

    service = StudyRecommendationService(
        settings=RagSettings(enabled=False),
        retriever=None,
        unavailable_reason="rag_disabled",
    )
    passed = 0
    for case in cases:
        result = service.answer_query(case.to_query())
        if (
            not result.source_chunks
            and result.confidence == "baja"
            and "service:rag_disabled" in result.groundedness_notes
            and "No tengo informacion suficiente" in result.answer
        ):
            passed += 1
    total = len(cases)
    return {
        "total_cases": total,
        "passed_cases": passed,
        "pass_rate": _safe_div(passed, total),
    }


def _evaluate_case(
    case: RagEvalCase,
    result: StudyRecommendationResult,
    package: GroundedContextPackage | None,
    *,
    latency_ms: float,
) -> RagEvalCaseResult:
    selected_chunks = list(package.selected_chunks if package else [])
    selected_entities = _unique(chunk.entity_id for chunk in selected_chunks)
    recommended_entities = _unique(
        [*result.recommended_techniques, *result.recommended_methods]
    )
    retrieved_entities = _unique([*selected_entities, *recommended_entities])
    expected_entities = [_canonical_entity(entity) for entity in case.expected_entities]
    forbidden_entities = [_canonical_entity(entity) for entity in case.forbidden_entities]
    expected_hits = [entity for entity in expected_entities if entity in retrieved_entities]
    forbidden_hits = [entity for entity in forbidden_entities if entity in retrieved_entities]
    selected_chunk_kinds = _unique(chunk.chunk_kind for chunk in selected_chunks)
    expected_chunk_kind_hits = [
        kind for kind in case.expected_chunk_kinds if kind in selected_chunk_kinds
    ]
    relation_types = _unique(
        str(relation.relation_type)
        for relation in (package.relations if package else [])
    )
    expected_relation_type_hits = [
        relation_type
        for relation_type in case.expected_relation_types
        if relation_type in relation_types
    ]
    entity_recall = _safe_div(len(expected_hits), len(expected_entities))
    entity_precision = _safe_div(
        len([entity for entity in retrieved_entities if entity in expected_entities]),
        len(retrieved_entities),
    )
    reciprocal_rank = _reciprocal_rank(selected_chunks, expected_entities)
    chunk_kind_recall = _safe_div(
        len(expected_chunk_kind_hits),
        len(case.expected_chunk_kinds),
    )
    groundedness_ok = (not case.require_sources) or bool(result.source_chunks)
    caution_ok = (not case.expect_caution) or bool(result.cautions) or _answer_has_caution(
        result.answer
    )
    answer_terms_ok = all(
        _contains_term(result.answer, term) for term in case.expected_answer_terms
    )
    forbidden_terms_ok = not any(
        _contains_term(result.answer, term) for term in case.forbidden_answer_terms
    )
    failure_reasons = _failure_reasons(
        case=case,
        expected_hits=expected_hits,
        forbidden_hits=forbidden_hits,
        expected_chunk_kind_hits=expected_chunk_kind_hits,
        expected_relation_type_hits=expected_relation_type_hits,
        groundedness_ok=groundedness_ok,
        caution_ok=caution_ok,
        answer_terms_ok=answer_terms_ok,
        forbidden_terms_ok=forbidden_terms_ok,
    )
    return RagEvalCaseResult(
        eval_id=case.eval_id,
        category=case.category,
        intent=(package.understanding.intent if package else case.intent or "unknown"),
        passed=not failure_reasons,
        latency_ms=round(latency_ms, 3),
        expected_entities=expected_entities,
        retrieved_entities=retrieved_entities,
        recommended_entities=recommended_entities,
        expected_entity_hits=expected_hits,
        forbidden_entity_hits=forbidden_hits,
        selected_chunk_ids=[chunk.chunk_id for chunk in selected_chunks],
        selected_chunk_kinds=selected_chunk_kinds,
        expected_chunk_kind_hits=expected_chunk_kind_hits,
        relation_types=relation_types,
        expected_relation_type_hits=expected_relation_type_hits,
        source_chunks=list(result.source_chunks),
        confidence=result.confidence,
        groundedness_notes=list(result.groundedness_notes),
        answer=result.answer,
        expect_caution=case.expect_caution,
        entity_recall_at_k=round(entity_recall, 6),
        entity_precision_at_k=round(entity_precision, 6),
        reciprocal_rank=round(reciprocal_rank, 6),
        chunk_kind_recall=round(chunk_kind_recall, 6),
        groundedness_ok=groundedness_ok,
        caution_ok=caution_ok,
        answer_terms_ok=answer_terms_ok,
        forbidden_terms_ok=forbidden_terms_ok,
        failure_reasons=failure_reasons,
    )


def _failure_reasons(
    *,
    case: RagEvalCase,
    expected_hits: list[str],
    forbidden_hits: list[str],
    expected_chunk_kind_hits: list[str],
    expected_relation_type_hits: list[str],
    groundedness_ok: bool,
    caution_ok: bool,
    answer_terms_ok: bool,
    forbidden_terms_ok: bool,
) -> list[str]:
    reasons: list[str] = []
    if case.expected_entities and len(expected_hits) < len(case.expected_entities):
        reasons.append("expected_entities_missing")
    if forbidden_hits:
        reasons.append("forbidden_entity_retrieved")
    if case.expected_chunk_kinds and not expected_chunk_kind_hits:
        reasons.append("expected_chunk_kind_missing")
    if case.expected_relation_types and len(expected_relation_type_hits) < len(
        case.expected_relation_types
    ):
        reasons.append("expected_relation_type_missing")
    if not groundedness_ok:
        reasons.append("sources_missing")
    if not caution_ok:
        reasons.append("expected_caution_missing")
    if not answer_terms_ok:
        reasons.append("expected_answer_terms_missing")
    if not forbidden_terms_ok:
        reasons.append("forbidden_answer_term_present")
    return reasons


def _aggregate_metrics(results: list[RagEvalCaseResult]) -> RagEvalMetrics:
    total = len(results)
    passed = sum(1 for result in results if result.passed)
    entity_results = [result for result in results if result.expected_entities]
    chunk_kind_results = [
        result for result in results if result.selected_chunk_kinds
    ]
    caution_expected = [result for result in results if result.expect_caution]
    latencies = sorted(result.latency_ms for result in results)
    categories = sorted({result.category for result in results})
    by_category: dict[str, dict[str, float]] = {}
    for category in categories:
        items = [result for result in results if result.category == category]
        entity_items = [result for result in items if result.expected_entities]
        by_category[category] = {
            "cases": float(len(items)),
            "pass_rate": _safe_div(sum(1 for result in items if result.passed), len(items)),
            "entity_recall_at_k": _mean(
                result.entity_recall_at_k for result in entity_items
            ),
            "groundedness_rate": _safe_div(
                sum(1 for result in items if result.groundedness_ok),
                len(items),
            ),
        }
    return RagEvalMetrics(
        total_cases=total,
        passed_cases=passed,
        pass_rate=round(_safe_div(passed, total), 6),
        entity_recall_at_k=round(
            _mean(result.entity_recall_at_k for result in entity_results),
            6,
        ),
        entity_precision_at_k=round(
            _mean(result.entity_precision_at_k for result in entity_results),
            6,
        ),
        mrr=round(_mean(result.reciprocal_rank for result in entity_results), 6),
        chunk_kind_recall=round(
            _mean(result.chunk_kind_recall for result in chunk_kind_results),
            6,
        ),
        groundedness_rate=round(
            _safe_div(sum(1 for result in results if result.groundedness_ok), total),
            6,
        ),
        caution_success_rate=round(
            _safe_div(
                sum(1 for result in caution_expected if result.caution_ok),
                len(caution_expected),
            ),
            6,
        )
        if caution_expected
        else 1.0,
        forbidden_entity_violations=sum(
            1 for result in results if result.forbidden_entity_hits
        ),
        forbidden_answer_term_violations=sum(
            1 for result in results if not result.forbidden_terms_ok
        ),
        latency_p50_ms=_percentile(latencies, 50),
        latency_p95_ms=_percentile(latencies, 95),
        latency_max_ms=round(max(latencies), 3) if latencies else 0.0,
        by_category=by_category,
    )


def _embed_local_repository(
    repository: InMemoryRagRepository,
    embedding_client: DeterministicEvaluationEmbeddingClient,
) -> None:
    candidates = repository.list_chunks_missing_embeddings(limit=100_000)
    embeddings = embedding_client.embed_texts([candidate.content for candidate in candidates])
    updates = [
        RagEmbeddingUpdate(
            chunk_id=candidate.chunk_id,
            checksum=candidate.checksum,
            embedding=embedding,
            provider=embedding_client.provider,
            model=embedding_client.model,
            dimensions=embedding_client.dimensions,
        )
        for candidate, embedding in zip(candidates, embeddings)
    ]
    repository.update_chunk_embeddings(updates)


def _build_embedding_client(settings: RagSettings) -> EmbeddingClient:
    provider = settings.embedding_provider.strip().lower()
    if provider in {"azure", "azure_openai"}:
        return build_azure_openai_embedding_client_from_env(
            deployment_name=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )
    if provider == "openai":
        return build_openai_embedding_client_from_env(
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )
    raise ValueError(f"Unsupported embedding provider: {settings.embedding_provider}")


def _hash_bow_vector(text: str, dimensions: int) -> list[float]:
    vector = [0.0] * dimensions
    for token in _tokens(text):
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        index = int(digest[:8], 16) % dimensions
        vector[index] += 1.0
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 0:
        return vector
    return [round(value / norm, 8) for value in vector]


def _tokens(text: str) -> list[str]:
    slug = slugify_identifier(text)
    return [token for token in re.split(r"_+", slug) if len(token) > 2]


def _canonical_entity(entity: str) -> str:
    normalized_technique = normalize_technique_id(entity)
    if normalized_technique:
        return normalized_technique
    return slugify_identifier(entity)


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            unique.append(value)
    return unique


def _reciprocal_rank(selected_chunks, expected_entities: list[str]) -> float:
    if not expected_entities:
        return 0.0
    expected = set(expected_entities)
    for index, chunk in enumerate(selected_chunks, start=1):
        if chunk.entity_id in expected:
            return 1.0 / index
    return 0.0


def _answer_has_caution(answer: str) -> bool:
    slug = slugify_identifier(answer)
    return any(term in slug for term in _CAUTION_TERMS)


def _contains_term(text: str, term: str) -> bool:
    return slugify_identifier(term) in slugify_identifier(text)


def _safe_div(numerator: int | float, denominator: int | float) -> float:
    if denominator == 0:
        return 0.0
    return float(numerator) / float(denominator)


def _mean(values: Iterable[float]) -> float:
    items = list(values)
    if not items:
        return 0.0
    return sum(items) / len(items)


def _percentile(values: list[float], percentile: int) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return round(values[0], 3)
    position = (len(values) - 1) * (percentile / 100)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(values[int(position)], 3)
    weight = position - lower
    return round(values[lower] * (1 - weight) + values[upper] * weight, 3)


__all__ = [
    "DEFAULT_EVAL_DATASET_PATH",
    "CapturingStudyRecommendationRetriever",
    "DeterministicEvaluationEmbeddingClient",
    "EvaluationTarget",
    "build_local_evaluation_target",
    "build_postgres_evaluation_target",
    "evaluate_cases",
    "evaluate_disabled_fallback",
    "load_eval_cases",
]
