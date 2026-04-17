"""Contract tests for the phase A RAG ingestion pipeline."""

from __future__ import annotations

from rag.ingestion.pipeline import build_rag_corpus


def test_rag_corpus_validates_current_sources_without_errors() -> None:
    result = build_rag_corpus()

    assert not result.has_errors, [issue.model_dump() for issue in result.issues]
    assert len(result.documents) == 15
    assert len(result.chunks) == 468
    assert result.relations


def test_rag_validation_fails_for_missing_frontmatter(tmp_path) -> None:
    corpus_root = tmp_path / "study_recommendations"
    raw_techniques = corpus_root / "raw" / "techniques"
    raw_techniques.mkdir(parents=True)
    (raw_techniques / "broken.md").write_text(
        "# Documento sin frontmatter\n\n## 1. Definicion breve\nTexto.",
        encoding="utf-8",
    )

    result = build_rag_corpus(corpus_root)

    assert result.has_errors
    assert [issue.code for issue in result.issues] == ["frontmatter_parse_error"]
