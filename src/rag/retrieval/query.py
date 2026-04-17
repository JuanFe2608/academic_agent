"""Rule-based query understanding for study recommendation RAG."""

from __future__ import annotations

from schemas.rag import StudyRecommendationQuery

from rag.ingestion.normalization import (
    SIGNAL_ALIASES,
    TECHNIQUE_ALIASES,
    normalize_signals,
    normalize_technique_id,
    slugify_identifier,
)

from .filters import CHUNK_KINDS_BY_INTENT, build_structural_filters
from .models import KNOWN_QUERY_INTENTS, QueryUnderstanding
from .relations import relation_types_for_intent

METHOD_ALIASES: dict[str, list[str]] = {
    "metodo_parcial_teorico": [
        "metodo_parcial_teorico",
        "parcial_teorico",
        "examen_teorico",
        "prueba_teorica",
        "parcial",
    ],
    "metodo_lectura_y_sintesis": [
        "metodo_lectura_y_sintesis",
        "lectura_y_sintesis",
        "lectura_sintesis",
        "lectura",
        "sintesis",
    ],
    "metodo_repaso_semanal": [
        "metodo_repaso_semanal",
        "repaso_semanal",
        "repaso",
    ],
    "metodo_evaluacion_numerica_breve": [
        "metodo_evaluacion_numerica_breve",
        "evaluacion_numerica",
        "ejercicios_numericos",
        "problemas_numericos",
        "numerica",
    ],
}

PRIMARY_TECHNIQUES_BY_SIGNAL: dict[str, list[str]] = {
    "procrastination": ["pomodoro"],
    "distraction": ["pomodoro"],
    "passive_review_dependence": ["active_recall"],
    "rapid_forgetting": ["repeticion_espaciada"],
    "explanation_gap": ["feynman"],
    "note_organization": ["cornell"],
    "concept_connections": ["mapas_conceptuales"],
    "exact_memory": ["mnemotecnia"],
    "difficulty_switching_topics": ["interleaving"],
}


def understand_query(query: StudyRecommendationQuery) -> QueryUnderstanding:
    """Interpret a retrieval query using deterministic project vocabulary."""

    text = query.query_text.strip()
    slug_text = slugify_identifier(text)
    detected_techniques = _detect_techniques(slug_text, query.top_techniques)
    detected_methods = _detect_methods(slug_text)
    detected_signals = _detect_signals(slug_text, query.student_signals)
    intent = _resolve_intent(query.intent, slug_text, detected_techniques, detected_methods)
    if not detected_techniques and intent == "recommend_technique":
        detected_techniques = _techniques_for_signals(detected_signals)
    detected_entities = _unique([*detected_techniques, *detected_methods])
    understanding = QueryUnderstanding(
        intent=intent,
        query_text=text,
        detected_entities=detected_entities,
        detected_techniques=detected_techniques,
        detected_methods=detected_methods,
        detected_signals=detected_signals,
        desired_chunk_kinds=CHUNK_KINDS_BY_INTENT.get(intent, []),
        relation_types=relation_types_for_intent(intent),
        notes=_notes_for_query(query, intent, detected_entities, detected_signals),
    )
    return QueryUnderstanding(
        intent=understanding.intent,
        query_text=understanding.query_text,
        filters=build_structural_filters(query, understanding, strict=True),
        detected_entities=understanding.detected_entities,
        detected_techniques=understanding.detected_techniques,
        detected_methods=understanding.detected_methods,
        detected_signals=understanding.detected_signals,
        desired_chunk_kinds=understanding.desired_chunk_kinds,
        relation_types=understanding.relation_types,
        notes=understanding.notes,
    )


def retrieval_search_text(
    query: StudyRecommendationQuery,
    understanding: QueryUnderstanding,
) -> str:
    """Build a search string that still works when query_text is sparse."""

    parts = [
        query.query_text.strip(),
        query.subject_name or "",
        query.subject_type or "",
        query.activity_type or "",
        " ".join(understanding.detected_entities),
        " ".join(understanding.detected_signals),
        " ".join(query.top_techniques),
    ]
    return " ".join(part for part in parts if part).strip()


def _resolve_intent(
    explicit_intent: str | None,
    slug_text: str,
    detected_techniques: list[str],
    detected_methods: list[str],
) -> str:
    if explicit_intent and explicit_intent in KNOWN_QUERY_INTENTS:
        return explicit_intent

    if _contains_any(
        slug_text,
        [
            "contraindic",
            "no_conviene",
            "no_recomend",
            "evitar",
            "mala_idea",
            "riesgo",
        ],
    ):
        return "contraindication_check"
    if _contains_any(slug_text, ["combinar", "combinacion", "juntas", "junto", "mezclar"]):
        return "combine_techniques"
    if _contains_any(slug_text, ["vs", "versus", "diferencia", "tecnica_vs_metodo"]):
        return "technique_vs_method"
    if _contains_any(slug_text, ["comparar", "comparacion", "cual_es_mejor"]):
        return "compare_options"
    if _contains_any(
        slug_text,
        ["sesion", "paso_a_paso", "instrucciones", "como_aplico", "como_usar"],
    ):
        return "session_guidance"
    if _contains_any(slug_text, ["adaptar", "ajustar", "adecuar"]):
        return "adapt_method"
    if _contains_any(slug_text, ["que_es", "definicion", "explica", "explicame"]):
        return "explain_technique"
    if detected_methods or "metodo" in slug_text:
        return "recommend_method"
    if detected_techniques and _contains_any(slug_text, ["que_es", "explica"]):
        return "explain_technique"
    if _contains_any(slug_text, ["recomienda", "recomendacion", "conviene", "me_cuesta"]):
        return "recommend_technique"
    return "recommend_technique"


def _detect_techniques(slug_text: str, top_techniques: list[str]) -> list[str]:
    detected: list[str] = []
    for technique in top_techniques:
        normalized = normalize_technique_id(technique)
        if normalized:
            detected.append(normalized)
    for alias, canonical in TECHNIQUE_ALIASES.items():
        if _slug_contains(slug_text, alias):
            detected.append(canonical)
    return _unique(detected)


def _detect_methods(slug_text: str) -> list[str]:
    detected: list[str] = []
    for method_id, aliases in METHOD_ALIASES.items():
        if any(_slug_contains(slug_text, alias) for alias in aliases):
            detected.append(method_id)
    return _unique(detected)


def _detect_signals(slug_text: str, explicit_signals: list[str]) -> list[str]:
    detected = normalize_signals(explicit_signals)
    for alias, canonical_values in SIGNAL_ALIASES.items():
        if _slug_contains(slug_text, alias):
            detected.extend(canonical_values)
    return _unique(detected)


def _techniques_for_signals(signals: list[str]) -> list[str]:
    techniques: list[str] = []
    for signal in signals:
        techniques.extend(PRIMARY_TECHNIQUES_BY_SIGNAL.get(signal, []))
    return _unique(techniques)


def _notes_for_query(
    query: StudyRecommendationQuery,
    intent: str,
    detected_entities: list[str],
    detected_signals: list[str],
) -> list[str]:
    notes = [f"intent:{intent}"]
    if detected_entities:
        notes.append("entities:" + ",".join(detected_entities))
    if detected_signals:
        notes.append("signals:" + ",".join(detected_signals))
    if query.activity_type:
        notes.append(f"activity:{slugify_identifier(query.activity_type)}")
    if query.subject_type:
        notes.append(f"subject:{slugify_identifier(query.subject_type)}")
    return notes


def _contains_any(slug_text: str, needles: list[str]) -> bool:
    for needle in needles:
        slug = slugify_identifier(needle)
        if not slug:
            continue
        if len(slug) <= 2 and _slug_contains(slug_text, slug):
            return True
        if len(slug) > 2 and slug in slug_text:
            return True
    return False


def _slug_contains(slug_text: str, needle: str) -> bool:
    slug = slugify_identifier(needle)
    if not slug:
        return False
    padded_text = f"_{slug_text}_"
    padded_slug = f"_{slug}_"
    return padded_slug in padded_text or slug_text.startswith(f"{slug}_") or slug_text.endswith(f"_{slug}")


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            unique.append(value)
    return unique


__all__ = [
    "METHOD_ALIASES",
    "PRIMARY_TECHNIQUES_BY_SIGNAL",
    "retrieval_search_text",
    "understand_query",
]
