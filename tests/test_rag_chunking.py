"""Chunking tests for the phase A RAG corpus build."""

from __future__ import annotations

from collections import Counter, defaultdict

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


def test_chunk_content_contains_only_its_own_section() -> None:
    result = build_rag_corpus()

    for chunk in result.chunks:
        assert chunk.content.startswith(f"## {chunk.section_title}")
        headings = [
            line
            for line in chunk.content.splitlines()
            if line.startswith("## ") and not line.startswith("### ")
        ]
        assert headings == [f"## {chunk.section_title}"]


def test_chunk_navigation_metadata_links_document_neighbors() -> None:
    result = build_rag_corpus()
    chunks_by_document = defaultdict(list)
    for chunk in result.chunks:
        chunks_by_document[chunk.document_id].append(chunk)

    for document_chunks in chunks_by_document.values():
        ordered_chunks = sorted(document_chunks, key=lambda chunk: chunk.position_in_document)
        document_section_count = len(ordered_chunks)

        for index, chunk in enumerate(ordered_chunks):
            previous_chunk = ordered_chunks[index - 1] if index > 0 else None
            next_chunk = (
                ordered_chunks[index + 1] if index + 1 < document_section_count else None
            )

            assert chunk.metadata["section_index"] == index + 1
            assert chunk.metadata["document_section_count"] == document_section_count
            assert chunk.metadata["previous_chunk_id"] == (
                previous_chunk.chunk_id if previous_chunk else None
            )
            assert chunk.metadata["next_chunk_id"] == (
                next_chunk.chunk_id if next_chunk else None
            )


def test_chunks_define_retrieval_roles_and_structured_metadata_flags() -> None:
    result = build_rag_corpus()
    metadata_chunks = [
        chunk
        for chunk in result.chunks
        if "metadatos_de_recuperacion_sugeridos" in chunk.chunk_id
    ]
    answerable_chunks = [
        chunk
        for chunk in result.chunks
        if "metadatos_de_recuperacion_sugeridos" not in chunk.chunk_id
    ]

    assert len(metadata_chunks) == 15
    assert Counter(chunk.retrieval_role for chunk in result.chunks) == {
        "answerable": 453,
        "structured_metadata": 15,
    }
    assert {chunk.chunk_kind for chunk in metadata_chunks} == {"metadata"}

    for chunk in answerable_chunks:
        assert chunk.metadata["retrieval_role"] == "answerable"
        assert chunk.metadata["semantic_retrieval_enabled"] is True
        assert chunk.metadata["prompt_context_enabled"] is True
        assert chunk.metadata["embedding_enabled"] is True

    for chunk in metadata_chunks:
        assert chunk.metadata["retrieval_role"] == "structured_metadata"
        assert chunk.metadata["semantic_retrieval_enabled"] is False
        assert chunk.metadata["prompt_context_enabled"] is False
        assert chunk.metadata["embedding_enabled"] is False


def test_chunk_kind_uses_section_content_without_neighbor_overlap() -> None:
    result = build_rag_corpus()

    target = next(
        chunk
        for chunk in result.chunks
        if chunk.chunk_id
        == "study_framework.marco_conceptual_tecnica_vs_metodo_de_estudio::s019-19_implicaciones_para_diseno_de_recomendaciones"
    )

    assert target.chunk_kind == "agent_guidance"
