"""Business service for RAG-backed study recommendations."""

from __future__ import annotations

from typing import Iterable

from bootstrap.errors import RepositoryConfigurationError
from bootstrap.settings import (
    RagSettings,
    database_url_from_env,
    load_rag_settings,
)
from integrations.embeddings import (
    EmbeddingClientError,
    build_azure_openai_embedding_client_from_env,
    build_openai_embedding_client_from_env,
)
from rag.ingestion.normalization import normalize_signals, normalize_technique_id, slugify_identifier
from rag.prompting import (
    GroundedAnswerGenerator,
    build_grounded_study_recommendation_result,
    build_llm_grounded_answer_generator_from_env,
    render_fallback_answer,
)
from rag.retrieval.hybrid import HybridRagRetriever
from repositories.rag import RagRepositoryError, build_rag_repository
from schemas.rag import StudyRecommendationQuery, StudyRecommendationResult

from .models import StudyRecommendationRetriever, StudyRecommendationServiceStatus

_DIRECT_STUDY_RECOMMENDATION_TERMS = {
    "active_recall",
    "recuperacion_activa",
    "recuperacion",
    "pomodoro",
    "feynman",
    "cornell",
    "mapas_conceptuales",
    "mapa_conceptual",
    "mnemotecnia",
    "repeticion_espaciada",
    "repaso_espaciado",
    "interleaving",
    "intercalado",
    "tecnica_de_estudio",
    "tecnicas_de_estudio",
    "metodo_de_estudio",
    "metodos_de_estudio",
    "como_estudio",
    "como_estudiar",
    "estudiar_para",
    "combinar",
    "combinacion",
}


class StudyRecommendationService:
    """Facade consumed by future agent flows instead of importing RAG internals."""

    def __init__(
        self,
        *,
        settings: RagSettings,
        retriever: StudyRecommendationRetriever | None = None,
        answer_generator: GroundedAnswerGenerator | None = None,
        unavailable_reason: str | None = None,
    ) -> None:
        self.settings = settings
        self._retriever = retriever
        self._answer_generator = answer_generator
        self._unavailable_reason = unavailable_reason

    @property
    def status(self) -> StudyRecommendationServiceStatus:
        """Expose whether the service can use RAG sources right now."""

        ready = bool(self.settings.enabled and self._retriever is not None)
        reason = None if ready else self._unavailable_reason or "rag_disabled"
        return StudyRecommendationServiceStatus(
            enabled=bool(self.settings.enabled),
            ready=ready,
            reason=reason,
        )

    def answer_query(self, query: StudyRecommendationQuery) -> StudyRecommendationResult:
        """Run retrieval and grounded assembly for a prepared query DTO."""

        if not self.status.ready or self._retriever is None:
            return _fallback_result(
                query,
                reason=self.status.reason or "rag_unavailable",
            )
        try:
            package = self._retriever.retrieve(query)
            return build_grounded_study_recommendation_result(
                package,
                answer_generator=self._answer_generator,
            )
        except Exception as exc:  # noqa: BLE001 - RAG must not break operational flows
            return _fallback_result(
                query,
                reason="rag_runtime_error",
                detail=exc.__class__.__name__,
            )

    def explain_technique(
        self,
        technique_id: str,
        *,
        query_text: str | None = None,
        preferred_language: str = "es",
        max_chunks: int = 3,
    ) -> StudyRecommendationResult:
        """Explain a single technique using internal sources."""

        technique = normalize_technique_id(technique_id)
        return self.answer_query(
            StudyRecommendationQuery(
                query_text=query_text
                or f"Que es {technique.replace('_', ' ')} y cuando conviene?",
                intent="explain_technique",
                top_techniques=[technique] if technique else [],
                preferred_language=preferred_language,
                max_chunks=max_chunks,
            )
        )

    def recommend_for_student(
        self,
        *,
        student_signals: Iterable[str] | None = None,
        top_techniques: Iterable[str] | None = None,
        subject_name: str | None = None,
        subject_type: str | None = None,
        activity_type: str | None = None,
        difficulty: str | None = None,
        urgency: str | None = None,
        preferred_language: str = "es",
        max_chunks: int = 5,
    ) -> StudyRecommendationResult:
        """Recommend a technique from a narrow student-study context."""

        signals = normalize_signals(list(student_signals or []))
        techniques = _normalize_techniques(top_techniques or [])
        return self.answer_query(
            StudyRecommendationQuery(
                query_text=_student_recommendation_query_text(
                    subject_name=subject_name,
                    activity_type=activity_type,
                    signals=signals,
                    top_techniques=techniques,
                ),
                intent="recommend_technique",
                student_signals=signals,
                top_techniques=techniques,
                subject_name=subject_name,
                subject_type=slugify_identifier(subject_type or "") or None,
                activity_type=slugify_identifier(activity_type or "") or None,
                difficulty=difficulty,
                urgency=urgency,
                preferred_language=preferred_language,
                max_chunks=max_chunks,
            )
        )

    def recommend_for_session(
        self,
        *,
        technique_id: str | None = None,
        subject_name: str | None = None,
        subject_type: str | None = None,
        activity_type: str | None = None,
        available_minutes: int | None = None,
        student_signals: Iterable[str] | None = None,
        top_techniques: Iterable[str] | None = None,
        preferred_language: str = "es",
        max_chunks: int = 5,
    ) -> StudyRecommendationResult:
        """Return grounded guidance for one study session."""

        techniques = _normalize_techniques(top_techniques or [])
        if technique_id:
            primary = normalize_technique_id(technique_id)
            techniques = _unique([primary, *techniques])
        return self.answer_query(
            StudyRecommendationQuery(
                query_text=_session_query_text(
                    technique_id=techniques[0] if techniques else None,
                    subject_name=subject_name,
                    activity_type=activity_type,
                    available_minutes=available_minutes,
                ),
                intent="session_guidance",
                student_signals=normalize_signals(list(student_signals or [])),
                top_techniques=techniques,
                subject_name=subject_name,
                subject_type=slugify_identifier(subject_type or "") or None,
                activity_type=slugify_identifier(activity_type or "") or None,
                available_minutes=available_minutes,
                preferred_language=preferred_language,
                max_chunks=max_chunks,
            )
        )

    def adapt_method_for_subject(
        self,
        *,
        method_id: str,
        subject_name: str | None = None,
        subject_type: str | None = None,
        activity_type: str | None = None,
        student_signals: Iterable[str] | None = None,
        preferred_language: str = "es",
        max_chunks: int = 5,
    ) -> StudyRecommendationResult:
        """Adapt a documented study method to a subject or activity context."""

        method = slugify_identifier(method_id)
        return self.answer_query(
            StudyRecommendationQuery(
                query_text=_method_query_text(
                    method_id=method,
                    subject_name=subject_name,
                    activity_type=activity_type,
                ),
                intent="adapt_method",
                student_signals=normalize_signals(list(student_signals or [])),
                top_techniques=[],
                subject_name=subject_name,
                subject_type=slugify_identifier(subject_type or "") or None,
                activity_type=slugify_identifier(activity_type or "") or None,
                preferred_language=preferred_language,
                max_chunks=max_chunks,
            )
        )

    def validate_technique_combination(
        self,
        technique_ids: Iterable[str],
        *,
        activity_type: str | None = None,
        student_signals: Iterable[str] | None = None,
        preferred_language: str = "es",
        max_chunks: int = 5,
    ) -> StudyRecommendationResult:
        """Check whether a technique combination has documented cautions."""

        techniques = _normalize_techniques(technique_ids)
        return self.answer_query(
            StudyRecommendationQuery(
                query_text=(
                    "Validar combinacion de tecnicas: "
                    + ", ".join(technique.replace("_", " ") for technique in techniques)
                ),
                intent="contraindication_check",
                student_signals=normalize_signals(list(student_signals or [])),
                top_techniques=techniques,
                activity_type=slugify_identifier(activity_type or "") or None,
                preferred_language=preferred_language,
                max_chunks=max_chunks,
            )
        )


def build_study_recommendation_service() -> StudyRecommendationService:
    """Build the RAG-backed recommendation service from environment settings."""

    settings = load_rag_settings()
    if not settings.enabled:
        return StudyRecommendationService(
            settings=settings,
            retriever=None,
            unavailable_reason="rag_disabled",
        )
    try:
        repository = build_rag_repository(database_url_from_env())
        embedding_client = _build_embedding_client(settings)
    except (
        EmbeddingClientError,
        RagRepositoryError,
        RepositoryConfigurationError,
        ValueError,
    ) as exc:
        return StudyRecommendationService(
            settings=settings,
            retriever=None,
            unavailable_reason=f"rag_configuration_error:{exc.__class__.__name__}",
        )

    return StudyRecommendationService(
        settings=settings,
        retriever=HybridRagRetriever(
            repository=repository,
            embedding_client=embedding_client,
            settings=settings,
        ),
        answer_generator=build_llm_grounded_answer_generator_from_env(settings),
    )


def is_study_recommendation_message(text: str | None) -> bool:
    """Detect direct user questions about study techniques or methods."""

    normalized = slugify_identifier(str(text or ""))
    if not normalized:
        return False
    if any(term in normalized for term in _DIRECT_STUDY_RECOMMENDATION_TERMS):
        return True
    return (
        "que_me_recomiendas" in normalized
        and any(token in normalized for token in {"estudiar", "parcial", "quiz", "repasar"})
    )


def _build_embedding_client(settings: RagSettings):
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
    raise EmbeddingClientError(f"Unsupported embedding provider: {settings.embedding_provider}")


def _fallback_result(
    query: StudyRecommendationQuery,
    *,
    reason: str,
    detail: str | None = None,
) -> StudyRecommendationResult:
    intent = query.intent or "recommend_technique"
    notes = ["service:fallback", f"service:{reason}"]
    if detail:
        notes.append(f"service_error:{detail}")
    return StudyRecommendationResult(
        answer=render_fallback_answer(query, intent=intent),
        confidence="baja",
        groundedness_notes=notes,
    )


def _normalize_techniques(values: Iterable[str]) -> list[str]:
    return _unique([normalize_technique_id(value) for value in values if str(value).strip()])


def _student_recommendation_query_text(
    *,
    subject_name: str | None,
    activity_type: str | None,
    signals: list[str],
    top_techniques: list[str],
) -> str:
    parts = ["Que tecnica de estudio conviene"]
    if subject_name:
        parts.append(f"para {subject_name}")
    if activity_type:
        parts.append(f"en actividad {activity_type}")
    if signals:
        parts.append("con senales " + ", ".join(signals))
    if top_techniques:
        parts.append("considerando " + ", ".join(top_techniques))
    return " ".join(parts) + "?"


def _session_query_text(
    *,
    technique_id: str | None,
    subject_name: str | None,
    activity_type: str | None,
    available_minutes: int | None,
) -> str:
    parts = ["Como aplicar"]
    parts.append(technique_id.replace("_", " ") if technique_id else "una tecnica de estudio")
    if subject_name:
        parts.append(f"en una sesion de {subject_name}")
    if activity_type:
        parts.append(f"para {activity_type}")
    if available_minutes:
        parts.append(f"en {available_minutes} minutos")
    return " ".join(parts) + "?"


def _method_query_text(
    *,
    method_id: str,
    subject_name: str | None,
    activity_type: str | None,
) -> str:
    parts = [f"Como adaptar el metodo {method_id.replace('_', ' ')}"]
    if subject_name:
        parts.append(f"a {subject_name}")
    if activity_type:
        parts.append(f"para {activity_type}")
    return " ".join(parts) + "?"


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            unique.append(value)
    return unique


__all__ = [
    "StudyRecommendationService",
    "build_study_recommendation_service",
    "is_study_recommendation_message",
]
