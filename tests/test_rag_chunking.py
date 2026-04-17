"""Chunking tests for the phase A RAG corpus build."""

from __future__ import annotations

from rag.ingestion.pipeline import build_rag_corpus


def test_chunks_have_stable_unique_ids_and_metadata() -> None:
    result = build_rag_corpus()
    chunk_ids = [chunk.chunk_id for chunk in result.chunks]

    assert len(chunk_ids) == len(set(chunk_ids))
    assert all(chunk.document_id for chunk in result.chunks)
    assert all(chunk.checksum for chunk in result.chunks)
    assert all(chunk.token_estimate > 0 for chunk in result.chunks)


def test_active_recall_chunks_use_canonical_entity_id() -> None:
    result = build_rag_corpus()
    active_recall_chunks = [
        chunk for chunk in result.chunks if chunk.document_id == "technique.active_recall"
    ]

    assert active_recall_chunks
    assert {chunk.entity_id for chunk in active_recall_chunks} == {"active_recall"}
    assert "recuperacion_activa" not in {
        chunk.entity_id for chunk in active_recall_chunks
    }


def test_chunk_kind_detection_keeps_reusable_and_matrix_sections() -> None:
    result = build_rag_corpus()

    assert any(
        chunk.document_id == "technique.active_recall"
        and chunk.chunk_kind == "answer_ready"
        for chunk in result.chunks
    )
    assert any(
        chunk.document_id
        == "technique_combination_matrix.matriz_de_combinacion_de_tecnicas_para_metodos_de_estudio"
        and chunk.chunk_kind == "matrix"
        and "|" in chunk.content
        for chunk in result.chunks
    )
