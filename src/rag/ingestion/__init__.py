"""Pipelines locales para ingestion RAG."""

from .embedding_pipeline import embed_changed_chunks
from .pipeline import build_rag_corpus, write_corpus_artifacts

__all__ = ["build_rag_corpus", "embed_changed_chunks", "write_corpus_artifacts"]
