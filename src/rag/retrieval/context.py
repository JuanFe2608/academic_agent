"""Grounded context packaging for retrieval output."""

from __future__ import annotations

from schemas.rag import RagRelation, StudyRecommendationQuery

from .models import (
    GroundedContextPackage,
    QueryUnderstanding,
    RagCitation,
    RagRetrievedChunk,
)


def build_grounded_context_package(
    *,
    query: StudyRecommendationQuery,
    understanding: QueryUnderstanding,
    chunks: list[RagRetrievedChunk],
    relations: list[RagRelation],
    notes: list[str] | None = None,
) -> GroundedContextPackage:
    """Create the structured context package consumed by later prompting/services."""

    citations = [
        RagCitation(
            document_id=chunk.document_id,
            chunk_id=chunk.chunk_id,
            section_title=chunk.section_title,
            source_path=str(chunk.metadata.get("source_path") or "") or None,
        )
        for chunk in chunks
    ]
    groundedness_notes = list(notes or [])
    if not chunks:
        groundedness_notes.append("fallback:no_chunks")
    else:
        groundedness_notes.append(f"sources:{len(chunks)}")
    if relations:
        groundedness_notes.append(f"relations:{len(relations)}")
    return GroundedContextPackage(
        query=query,
        understanding=understanding,
        selected_chunks=chunks,
        relations=relations,
        citations=citations,
        groundedness_notes=_unique(groundedness_notes),
    )


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            unique.append(value)
    return unique


__all__ = ["build_grounded_context_package"]
