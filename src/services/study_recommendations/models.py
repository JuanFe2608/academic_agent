"""Internal models for the study recommendation service boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from rag.retrieval.models import GroundedContextPackage
from schemas.rag import StudyRecommendationQuery


class StudyRecommendationRetriever(Protocol):
    """Minimal retrieval dependency consumed by the business service."""

    def retrieve(self, query: StudyRecommendationQuery) -> GroundedContextPackage: ...


@dataclass(frozen=True)
class StudyRecommendationServiceStatus:
    """Runtime availability of RAG-backed study recommendations."""

    enabled: bool
    ready: bool
    reason: str | None = None


__all__ = [
    "StudyRecommendationRetriever",
    "StudyRecommendationServiceStatus",
]
