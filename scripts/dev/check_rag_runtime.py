#!/usr/bin/env python
"""Diagnostico runtime del RAG de recomendaciones de estudio."""

from __future__ import annotations

import os
import sys
from typing import Any

from agents.support.dependencies import get_study_recommendation_service
from bootstrap.settings import database_url_from_env
from repositories.common import postgres_connection


def main() -> int:
    os.environ.setdefault("POSTGRES_CONNECT_TIMEOUT_SECONDS", "5")

    ok = True
    print("RAG runtime check")
    ok = _print_database_summary() and ok
    ok = _print_retrieval_probe() and ok
    return 0 if ok else 1


def _print_database_summary() -> bool:
    database_url = database_url_from_env()
    if not database_url:
        print("- database: missing ACADEMIC_AGENT_DATABASE_URL/PG* configuration")
        return False

    try:
        with postgres_connection(database_url) as conn:
            identity = conn.execute(
                """
                SELECT
                    current_database() AS db,
                    current_user AS db_user,
                    inet_server_addr()::text AS server_addr,
                    inet_server_port() AS server_port
                """
            ).fetchone()
            extension = conn.execute(
                "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') AS ok"
            ).fetchone()
            schema = conn.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.schemata
                    WHERE schema_name = 'rag'
                ) AS ok
                """
            ).fetchone()
            counts = conn.execute(
                """
                SELECT 'documents' AS metric, COUNT(*)::integer AS value FROM rag.documents
                UNION ALL
                SELECT 'chunks', COUNT(*)::integer FROM rag.chunks
                UNION ALL
                SELECT 'chunks_with_embeddings', COUNT(*)::integer
                FROM rag.chunks
                WHERE embedding IS NOT NULL
                UNION ALL
                SELECT 'relations', COUNT(*)::integer FROM rag.relations
                UNION ALL
                SELECT 'ingestion_runs', COUNT(*)::integer FROM rag.ingestion_runs
                """
            ).fetchall()
            latest_run = conn.execute(
                """
                SELECT corpus_name, corpus_version, status, documents_count,
                       chunks_count, relations_count, finished_at
                FROM rag.ingestion_runs
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
    except Exception as exc:  # noqa: BLE001 - diagnostic script should report concrete failure
        print(f"- database: failed ({exc.__class__.__name__}: {exc})")
        return False

    count_map = {str(row["metric"]): int(row["value"]) for row in counts}
    print(
        "- database:"
        f" db={identity['db']}"
        f" user={identity['db_user']}"
        f" server={identity['server_addr']}:{identity['server_port']}"
    )
    print(f"- pgvector: {bool(extension['ok'])}")
    print(f"- rag_schema: {bool(schema['ok'])}")
    for metric in (
        "documents",
        "chunks",
        "chunks_with_embeddings",
        "relations",
        "ingestion_runs",
    ):
        print(f"- {metric}: {count_map.get(metric, 0)}")
    if latest_run:
        print(
            "- latest_ingestion:"
            f" corpus={latest_run['corpus_name']}"
            f" version={latest_run['corpus_version']}"
            f" status={latest_run['status']}"
            f" docs={latest_run['documents_count']}"
            f" chunks={latest_run['chunks_count']}"
            f" relations={latest_run['relations_count']}"
        )

    return bool(
        extension["ok"]
        and schema["ok"]
        and count_map.get("documents", 0) > 0
        and count_map.get("chunks", 0) > 0
        and count_map.get("chunks_with_embeddings", 0) > 0
    )


def _print_retrieval_probe() -> bool:
    try:
        service = get_study_recommendation_service()
        print(
            "- service:"
            f" enabled={service.status.enabled}"
            f" ready={service.status.ready}"
            f" reason={service.status.reason}"
        )
        result = service.recommend_for_student(
            student_signals=["start_and_focus_friction"],
            top_techniques=["pomodoro"],
            max_chunks=3,
        )
    except Exception as exc:  # noqa: BLE001 - diagnostic script should report concrete failure
        print(f"- retrieval: failed ({exc.__class__.__name__}: {exc})")
        return False

    print(f"- retrieval_confidence: {result.confidence}")
    print(f"- source_chunks: {result.source_chunks}")
    print(f"- groundedness_notes: {result.groundedness_notes}")
    print(f"- answer_preview: {_preview(result.answer)}")
    return bool(result.source_chunks and "sources:cited" in result.groundedness_notes)


def _preview(value: Any, *, max_chars: int = 500) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "..."


if __name__ == "__main__":
    sys.exit(main())
