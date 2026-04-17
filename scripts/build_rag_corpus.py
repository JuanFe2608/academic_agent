#!/usr/bin/env python
"""Build local RAG artifacts for the study recommendations corpus."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bootstrap.settings import database_url_from_env, load_rag_settings
from integrations.embeddings import (
    EmbeddingClient,
    build_azure_openai_embedding_client_from_env,
    build_openai_embedding_client_from_env,
)
from integrations.embeddings.client import EmbeddingClientError
from rag.ingestion.embedding_pipeline import embed_changed_chunks
from rag.ingestion.pipeline import (
    CORPUS_VERSION,
    DEFAULT_CORPUS_ROOT,
    build_rag_corpus,
)
from repositories.rag import build_rag_repository


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate and build local RAG corpus artifacts without DB access."
    )
    parser.add_argument(
        "--corpus-root",
        default=DEFAULT_CORPUS_ROOT.as_posix(),
        help="Path to knowledge_base/study_recommendations.",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate and summarize the corpus without writing generated artifacts.",
    )
    parser.add_argument(
        "--write-artifacts",
        action="store_true",
        help="Write inventory, chunks and relation manifests.",
    )
    parser.add_argument(
        "--sync-db",
        action="store_true",
        help="Persist documents, chunks and relations into PostgreSQL schema rag.",
    )
    parser.add_argument(
        "--embed-changed",
        action="store_true",
        help="Generate embeddings for DB chunks with missing embeddings.",
    )
    parser.add_argument(
        "--embedding-batch-size",
        type=int,
        default=32,
        help="Batch size used with --embed-changed.",
    )
    parser.add_argument(
        "--embedding-limit",
        type=int,
        default=None,
        help="Optional maximum number of chunks to embed in this run.",
    )
    args = parser.parse_args()

    write_artifacts = bool(args.write_artifacts)
    if (
        not args.validate_only
        and not args.write_artifacts
        and not args.sync_db
        and not args.embed_changed
    ):
        args.validate_only = True

    result = build_rag_corpus(Path(args.corpus_root), write_artifacts=write_artifacts)
    _print_summary(result, wrote_artifacts=write_artifacts)
    if result.has_errors:
        return 1

    rag_settings = load_rag_settings()
    repository = None

    if args.sync_db:
        repository = build_rag_repository(database_url_from_env())
        persisted = repository.sync_corpus_snapshot(
            corpus_name=rag_settings.corpus_name,
            corpus_version=CORPUS_VERSION,
            source_root=Path(args.corpus_root).as_posix(),
            documents=result.documents,
            chunks=result.chunks,
            relations=result.relations,
            metadata={"source": "scripts/build_rag_corpus.py"},
        )
        print("- db_sync: completed")
        print(f"- ingestion_run_id: {persisted.ingestion_run_id}")
        print(f"- run_id: {persisted.run_id}")

    if args.embed_changed:
        repository = repository or build_rag_repository(database_url_from_env())
        try:
            embedding_client = _build_embedding_client(rag_settings)
        except EmbeddingClientError as exc:
            print(f"- embed_changed: failed ({exc})")
            return 1
        embedding_result = embed_changed_chunks(
            repository=repository,
            embedding_client=embedding_client,
            batch_size=args.embedding_batch_size,
            limit=args.embedding_limit,
        )
        print("- embed_changed: completed")
        print(f"- requested_chunks: {embedding_result.requested_chunks}")
        print(f"- embedded_chunks: {embedding_result.embedded_chunks}")
        print(f"- updated_chunks: {embedding_result.updated_chunks}")
        print(f"- skipped_chunks: {embedding_result.skipped_chunks}")

    return 0


def _print_summary(result, *, wrote_artifacts: bool) -> None:
    print("RAG corpus build")
    print(f"- documents: {len(result.documents)}")
    print(f"- chunks: {len(result.chunks)}")
    print(f"- relations: {len(result.relations)}")
    print(f"- issues: {len(result.issues)}")
    if wrote_artifacts and not result.has_errors:
        print("- artifacts: written")
    elif wrote_artifacts:
        print("- artifacts: skipped because validation failed")

    for issue in result.issues:
        print(
            f"[{issue.severity}] {issue.code} "
            f"{issue.source_path or '-'}: {issue.message}"
        )


def _build_embedding_client(settings) -> EmbeddingClient:
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


if __name__ == "__main__":
    sys.exit(main())
