"""Normalization tests for RAG study recommendation documents."""

from __future__ import annotations

from rag.ingestion.normalization import (
    normalize_combination_entry,
    normalize_signals,
    normalize_technique_id,
)
from rag.ingestion.pipeline import build_rag_corpus


def test_active_recall_is_the_canonical_id_for_recuperacion_activa() -> None:
    result = build_rag_corpus()
    document = next(
        doc
        for doc in result.documents
        if doc.metadata.source_path == "raw/techniques/tecnica_recuperacion_activa_rag.md"
    )

    assert document.document_id == "technique.active_recall"
    assert document.entity_id == "active_recall"
    assert document.metadata.raw_metadata["technique_id"] == "recuperacion_activa"
    assert "recuperacion_activa" in document.metadata.aliases
    assert "recuperacion_activa" in document.metadata.aliases_normalized


def test_signal_aliases_are_normalized_to_radar_weakness_tags() -> None:
    assert normalize_signals(
        [
            "se_distrae_facil",
            "procrastina",
            "no_puede_explicar",
            "olvida_rapido",
            "confunde_tipos_de_ejercicio",
        ]
    ) == [
        "distraction",
        "procrastination",
        "explanation_gap",
        "rapid_forgetting",
        "difficulty_switching_topics",
    ]


def test_combination_entries_normalize_known_technique_aliases() -> None:
    assert normalize_technique_id("practica_de_recuperacion") == "active_recall"
    assert normalize_combination_entry(
        "practica_de_recuperacion + repeticion_espaciada"
    ) == ["active_recall", "repeticion_espaciada"]
