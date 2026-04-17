"""Local contracts for the RAG ingestion pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from schemas.rag import (
    NormalizedRagDocument,
    RagChunk,
    RagCorpusBuildResult,
    RagDocumentMetadata,
    RagRelation,
    RagValidationIssue,
)


@dataclass(frozen=True)
class ParsedMarkdownDocument:
    """Markdown document split into frontmatter and body."""

    source_path: Path
    relative_path: str
    checksum: str
    frontmatter: dict[str, object]
    body: str


__all__ = [
    "NormalizedRagDocument",
    "ParsedMarkdownDocument",
    "RagChunk",
    "RagCorpusBuildResult",
    "RagDocumentMetadata",
    "RagRelation",
    "RagValidationIssue",
]
