"""Relation extraction tests for the lightweight graph-aware RAG layer."""

from __future__ import annotations

from rag.ingestion.pipeline import build_rag_corpus


def test_relations_use_canonical_active_recall_id() -> None:
    result = build_rag_corpus()

    assert all(relation.source_id != "recuperacion_activa" for relation in result.relations)
    assert all(relation.target_id != "recuperacion_activa" for relation in result.relations)
    assert any(
        relation.source_id == "active_recall"
        and relation.relation_type == "recommended_with"
        and relation.target_id == "repeticion_espaciada"
        for relation in result.relations
    )


def test_relations_include_student_signals_and_contraindications() -> None:
    result = build_rag_corpus()

    assert any(
        relation.source_id == "active_recall"
        and relation.relation_type == "supports_signal"
        and relation.target_id == "passive_review_dependence"
        for relation in result.relations
    )
    assert any(
        relation.source_id == "active_recall"
        and relation.relation_type == "contraindicated_with"
        and relation.target_id == "ausencia_de_feedback"
        for relation in result.relations
    )


def test_combination_matrix_extracts_pairwise_recommendations() -> None:
    result = build_rag_corpus()

    assert any(
        relation.source_document_id
        == "technique_combination_matrix.matriz_de_combinacion_de_tecnicas_para_metodos_de_estudio"
        and relation.source_id == "active_recall"
        and relation.relation_type == "recommended_with"
        and relation.target_id == "repeticion_espaciada"
        and relation.metadata.get("inferred_pair") is True
        for relation in result.relations
    )
