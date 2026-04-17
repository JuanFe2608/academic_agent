"""Prompt-facing context derived from retrieval packages."""

from __future__ import annotations

import re
from dataclasses import dataclass

from rag.ingestion.normalization import slugify_identifier
from rag.retrieval.models import GroundedContextPackage, RagRetrievedChunk
from schemas.rag import RagRelation

DISPLAY_NAMES = {
    "active_recall": "recuperacion activa",
    "cornell": "Cornell",
    "feynman": "Feynman",
    "interleaving": "interleaving",
    "mapas_conceptuales": "mapas conceptuales",
    "mnemotecnia": "mnemotecnia",
    "pomodoro": "Pomodoro",
    "repeticion_espaciada": "repeticion espaciada",
    "metodo_evaluacion_numerica_breve": "metodo de evaluacion numerica breve",
    "metodo_lectura_y_sintesis": "metodo de lectura y sintesis",
    "metodo_parcial_teorico": "metodo para parcial teorico",
    "metodo_repaso_semanal": "metodo de repaso semanal",
}

_CHUNK_PRIORITY = {
    "answer_ready": 0,
    "agent_guidance": 1,
    "steps": 2,
    "use_case": 3,
    "adaptation": 4,
    "combination": 5,
    "contraindication": 6,
    "definition": 7,
    "comparison": 8,
    "matrix": 9,
    "objective": 10,
    "quality_control": 11,
    "evidence": 12,
}


@dataclass(frozen=True)
class GroundedPromptContext:
    """Internal evidence package used by deterministic answer templates."""

    primary_chunk: RagRetrievedChunk | None
    primary_text: str
    supporting_facts: list[str]
    cautions: list[str]
    recommended_techniques: list[str]
    recommended_methods: list[str]
    combinations: list[list[str]]
    source_chunks: list[str]
    relations_used: list[str]
    confidence: str
    has_blocking_contraindication: bool
    groundedness_notes: list[str]


def build_grounded_prompt_context(
    package: GroundedContextPackage,
) -> GroundedPromptContext:
    """Convert retrieval output into grounded facts and inferred payload."""

    primary_chunk = _select_primary_chunk(package.selected_chunks)
    primary_text = _chunk_summary(primary_chunk, max_chars=780) if primary_chunk else ""
    supporting_facts = _supporting_facts(package.selected_chunks, primary_chunk)
    blocked_pairs = _blocked_pairs(package.relations)
    has_blocking_contraindication = _has_blocking_pair(
        package.understanding.detected_entities,
        blocked_pairs,
    )
    cautions, caution_relation_ids = _extract_cautions(package, blocked_pairs)
    (
        recommended_techniques,
        recommended_methods,
        combinations,
        recommendation_relation_ids,
    ) = _extract_recommendation_payload(package, blocked_pairs)
    confidence = _derive_confidence(
        package.selected_chunks,
        cautions=cautions,
        has_blocking_contraindication=has_blocking_contraindication,
    )
    low_evidence_caution = _low_evidence_caution(package.selected_chunks)
    if low_evidence_caution:
        cautions = _unique([*cautions, low_evidence_caution])
        if confidence != "baja":
            confidence = "baja"

    source_chunks = [
        citation.chunk_id for citation in package.citations
    ] or [chunk.chunk_id for chunk in package.selected_chunks]
    relations_used = _unique([*caution_relation_ids, *recommendation_relation_ids])
    groundedness_notes = _unique(
        [
            *package.groundedness_notes,
            "prompt_context:built",
            f"prompt_context:sources:{len(source_chunks)}",
            "facts:retrieved_chunks",
            "inferences:recommendation_payload",
        ]
    )
    if has_blocking_contraindication:
        groundedness_notes.append("combination:blocked_by_relation")

    return GroundedPromptContext(
        primary_chunk=primary_chunk,
        primary_text=primary_text,
        supporting_facts=supporting_facts,
        cautions=cautions[:4],
        recommended_techniques=recommended_techniques[:6],
        recommended_methods=recommended_methods[:4],
        combinations=combinations[:6],
        source_chunks=source_chunks,
        relations_used=relations_used[:20],
        confidence=confidence,
        has_blocking_contraindication=has_blocking_contraindication,
        groundedness_notes=groundedness_notes,
    )


def format_entity_name(entity_id: str) -> str:
    """Return a readable Spanish label for internal entity IDs."""

    return DISPLAY_NAMES.get(entity_id, entity_id.replace("_", " "))


def clean_chunk_text(text: str, *, max_chars: int = 900) -> str:
    """Strip Markdown structure and keep a concise grounded excerpt."""

    cleaned_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("")
            continue
        if line.startswith("#"):
            continue
        line = re.sub(r"^\s*[-*]\s+", "", line)
        line = re.sub(r"\*\*(.*?)\*\*", r"\1", line)
        line = re.sub(r"`([^`]+)`", r"\1", line)
        cleaned_lines.append(line)
    cleaned = " ".join(line for line in cleaned_lines if line).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return _shorten(cleaned, max_chars=max_chars)


def _select_primary_chunk(chunks: list[RagRetrievedChunk]) -> RagRetrievedChunk | None:
    if not chunks:
        return None
    indexed = list(enumerate(chunks))
    _, chunk = min(
        indexed,
        key=lambda item: (
            _CHUNK_PRIORITY.get(item[1].chunk_kind, 99),
            -item[1].final_score,
            item[0],
        ),
    )
    return chunk


def _supporting_facts(
    chunks: list[RagRetrievedChunk],
    primary_chunk: RagRetrievedChunk | None,
) -> list[str]:
    facts: list[str] = []
    for chunk in chunks:
        if primary_chunk is not None and chunk.chunk_id == primary_chunk.chunk_id:
            continue
        if chunk.chunk_kind in {"evidence", "objective"}:
            continue
        summary = _chunk_summary(chunk, max_chars=320)
        if summary:
            facts.append(summary)
        if len(facts) >= 3:
            break
    return _unique(facts)


def _chunk_summary(chunk: RagRetrievedChunk | None, *, max_chars: int) -> str:
    if chunk is None:
        return ""
    return clean_chunk_text(chunk.content, max_chars=max_chars)


def _extract_cautions(
    package: GroundedContextPackage,
    blocked_pairs: set[frozenset[str]],
) -> tuple[list[str], list[str]]:
    cautions: list[str] = []
    relation_ids: list[str] = []
    activity_type = slugify_identifier(package.query.activity_type or "")
    detected_entities = set(package.understanding.detected_entities)
    for relation in package.relations:
        caution = _relation_caution(
            relation,
            activity_type=activity_type,
            detected_entities=detected_entities,
            blocked_pairs=blocked_pairs,
        )
        if caution:
            cautions.append(caution)
            relation_ids.append(relation.relation_id)

    for chunk in package.selected_chunks:
        if chunk.chunk_kind == "contraindication":
            cautions.append(_chunk_summary(chunk, max_chars=280))
        if chunk.contraindication_penalty > 0:
            cautions.append(
                f"Revisar limites de {format_entity_name(chunk.entity_id)} antes de recomendarlo."
            )
    return _unique([caution for caution in cautions if caution]), _unique(relation_ids)


def _relation_caution(
    relation: RagRelation,
    *,
    activity_type: str,
    detected_entities: set[str],
    blocked_pairs: set[frozenset[str]],
) -> str | None:
    source = format_entity_name(relation.source_id)
    target = format_entity_name(relation.target_id)
    evidence = clean_chunk_text(relation.evidence_text, max_chars=180)
    pair = frozenset([relation.source_id, relation.target_id])
    if relation.relation_type in {"contraindicated_with", "excludes"}:
        if pair in blocked_pairs or not detected_entities or pair & detected_entities:
            return f"Evitar combinar {source} con {target}: {evidence}."
    if relation.relation_type == "not_ideal_for_activity":
        if not activity_type or relation.target_id == activity_type:
            return f"{source} no es ideal para {target}: {evidence}."
    return None


def _extract_recommendation_payload(
    package: GroundedContextPackage,
    blocked_pairs: set[frozenset[str]],
) -> tuple[list[str], list[str], list[list[str]], list[str]]:
    techniques: list[str] = []
    methods: list[str] = []
    combinations: list[list[str]] = []
    relation_ids: list[str] = []
    selected_entities = {
        chunk.entity_id for chunk in package.selected_chunks
    } | set(package.understanding.detected_entities)
    signal_targets = set(package.understanding.detected_signals)
    activity_type = slugify_identifier(package.query.activity_type or "")
    allow_relation_recommendations = package.understanding.intent in {
        "recommend_technique",
        "recommend_method",
        "combine_techniques",
        "adapt_method",
        "session_guidance",
    }
    allow_pair_recommendations = package.understanding.intent in {
        "recommend_method",
        "combine_techniques",
        "adapt_method",
        "session_guidance",
    }

    if package.understanding.intent != "contraindication_check":
        for chunk in package.selected_chunks:
            if chunk.contraindication_penalty > 0:
                continue
            if chunk.knowledge_type == "technique":
                techniques.append(chunk.entity_id)
            if chunk.knowledge_type == "study_method":
                methods.append(chunk.entity_id)

    for relation in package.relations:
        if not allow_relation_recommendations:
            continue
        if relation.relation_type == "recommended_with":
            if not allow_pair_recommendations:
                continue
            pair = [relation.source_id, relation.target_id]
            if frozenset(pair) not in blocked_pairs and (
                relation.source_id in selected_entities
                or relation.target_id in selected_entities
            ):
                if relation.source_type == "technique" and relation.target_type == "technique":
                    combinations.append(pair)
                    techniques.extend(pair)
                    relation_ids.append(relation.relation_id)
        elif relation.relation_type == "uses_component":
            if relation.source_type == "study_method":
                methods.append(relation.source_id)
            if relation.target_type == "technique":
                techniques.append(relation.target_id)
            relation_ids.append(relation.relation_id)
        elif relation.relation_type == "supports_signal":
            if relation.target_id in signal_targets and relation.source_id in selected_entities:
                _append_by_source_type(relation, techniques, methods)
                relation_ids.append(relation.relation_id)
        elif relation.relation_type == "best_for_activity":
            if (
                activity_type
                and relation.target_id == activity_type
                and relation.source_id in selected_entities
            ):
                _append_by_source_type(relation, techniques, methods)
                relation_ids.append(relation.relation_id)

    return (
        _unique(techniques),
        _unique(methods),
        _dedupe_combinations(combinations),
        _unique(relation_ids),
    )


def _append_by_source_type(
    relation: RagRelation,
    techniques: list[str],
    methods: list[str],
) -> None:
    if relation.source_type == "technique":
        techniques.append(relation.source_id)
    elif relation.source_type == "study_method":
        methods.append(relation.source_id)


def _blocked_pairs(relations: list[RagRelation]) -> set[frozenset[str]]:
    return {
        frozenset([relation.source_id, relation.target_id])
        for relation in relations
        if relation.relation_type in {"contraindicated_with", "excludes"}
    }


def _has_blocking_pair(
    detected_entities: list[str],
    blocked_pairs: set[frozenset[str]],
) -> bool:
    detected = set(detected_entities)
    return any(pair <= detected for pair in blocked_pairs if len(pair) == 2)


def _low_evidence_caution(chunks: list[RagRetrievedChunk]) -> str:
    for chunk in chunks:
        evidence_level = slugify_identifier(str(chunk.metadata.get("evidence_level") or ""))
        confidence_level = slugify_identifier(str(chunk.metadata.get("confidence_level") or ""))
        if evidence_level in {"bajo", "baja"} or confidence_level in {"bajo", "baja"}:
            return (
                "La evidencia o confianza interna recuperada aparece marcada como baja; "
                "usar la recomendacion con cautela."
            )
    return ""


def _derive_confidence(
    chunks: list[RagRetrievedChunk],
    *,
    cautions: list[str],
    has_blocking_contraindication: bool,
) -> str:
    if not chunks or has_blocking_contraindication:
        return "baja"
    if any(chunk.contraindication_penalty > 0 for chunk in chunks):
        return "baja"
    levels = [
        slugify_identifier(str(chunk.metadata.get("confidence_level") or ""))
        for chunk in chunks
    ]
    evidence = [
        slugify_identifier(str(chunk.metadata.get("evidence_level") or ""))
        for chunk in chunks
    ]
    if any(level in {"bajo", "baja"} for level in [*levels, *evidence]):
        return "baja"
    if len(chunks) >= 2 and any(level in {"alto", "alta"} for level in [*levels, *evidence]):
        return "alta"
    if cautions:
        return "media"
    return "media"


def _dedupe_combinations(combinations: list[list[str]]) -> list[list[str]]:
    unique: list[list[str]] = []
    seen: set[frozenset[str]] = set()
    for combination in combinations:
        key = frozenset(combination)
        if len(key) < 2 or key in seen:
            continue
        seen.add(key)
        unique.append(combination)
    return unique


def _shorten(text: str, *, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    cutoff = text.rfind(".", 0, max_chars)
    if cutoff < int(max_chars * 0.55):
        cutoff = max_chars
    return text[:cutoff].rstrip(" .,;:") + "..."


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            unique.append(value)
    return unique


__all__ = [
    "GroundedPromptContext",
    "build_grounded_prompt_context",
    "clean_chunk_text",
    "format_entity_name",
]
