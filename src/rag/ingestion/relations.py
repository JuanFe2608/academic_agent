"""Relation extraction for the lightweight graph-aware RAG layer."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from itertools import combinations

from schemas.rag import NormalizedRagDocument, RagRelation, RagRelationType

from .normalization import (
    KNOWN_TECHNIQUE_IDS,
    normalize_combination_entry,
    normalize_signals,
    normalize_technique_id,
    slugify_identifier,
)

_RELATION_FIELDS: tuple[tuple[str, RagRelationType], ...] = (
    ("best_for_activity_types", "best_for_activity"),
    ("not_ideal_for_activity_types", "not_ideal_for_activity"),
)


def extract_relations(document: NormalizedRagDocument) -> list[RagRelation]:
    """Extract normalized relations from document metadata."""

    metadata = document.metadata.raw_metadata
    relations: list[RagRelation] = []

    relations.extend(_extract_component_relations(document, metadata, "included_techniques"))
    relations.extend(_extract_component_relations(document, metadata, "component_techniques"))
    relations.extend(
        _extract_component_relations(
            document,
            metadata,
            "optional_techniques",
            optional=True,
        )
    )
    relations.extend(_extract_excluded_relations(document, metadata))
    relations.extend(_extract_recommended_relations(document, metadata))
    relations.extend(_extract_contraindication_relations(document, metadata))
    relations.extend(_extract_signal_relations(document, metadata))
    relations.extend(_extract_simple_metadata_relations(document, metadata))
    relations.extend(_extract_framework_routes(document))

    return _dedupe_relations(relations)


def _extract_component_relations(
    document: NormalizedRagDocument,
    metadata: dict[str, object],
    field: str,
    *,
    optional: bool = False,
) -> list[RagRelation]:
    relations: list[RagRelation] = []
    for raw_value in _as_list(metadata.get(field)):
        target_id = normalize_technique_id(str(raw_value))
        target_type = "technique" if target_id in KNOWN_TECHNIQUE_IDS else "component"
        relations.append(
            _relation(
                document,
                relation_type="uses_component",
                target_type=target_type,
                target_id=target_id,
                evidence_text=str(raw_value),
                metadata={"field": field, "optional": optional},
            )
        )
    return relations


def _extract_excluded_relations(
    document: NormalizedRagDocument,
    metadata: dict[str, object],
) -> list[RagRelation]:
    relations: list[RagRelation] = []
    for raw_value in _as_list(metadata.get("excluded_techniques")):
        target_id = normalize_technique_id(str(raw_value))
        relations.append(
            _relation(
                document,
                relation_type="excludes",
                target_type="technique" if target_id in KNOWN_TECHNIQUE_IDS else "concept",
                target_id=target_id,
                evidence_text=str(raw_value),
                metadata={"field": "excluded_techniques"},
            )
        )
    return relations


def _extract_recommended_relations(
    document: NormalizedRagDocument,
    metadata: dict[str, object],
) -> list[RagRelation]:
    relations: list[RagRelation] = []
    for raw_value in _as_list(metadata.get("recommended_combinations")):
        targets = [target for target in normalize_combination_entry(raw_value) if target]
        if not targets:
            continue

        source_is_technique = document.knowledge_type == "technique"
        if source_is_technique and len(targets) == 1:
            target = targets[0]
            relations.append(
                _relation(
                    document,
                    relation_type="recommended_with",
                    target_type="technique" if target in KNOWN_TECHNIQUE_IDS else "concept",
                    target_id=target,
                    evidence_text=str(raw_value),
                    metadata={"field": "recommended_combinations"},
                )
            )
            continue

        known_targets = [target for target in targets if target in KNOWN_TECHNIQUE_IDS]
        for target in known_targets:
            relations.append(
                _relation(
                    document,
                    relation_type="recommended_with",
                    target_type="technique",
                    target_id=target,
                    evidence_text=str(raw_value),
                    metadata={"field": "recommended_combinations", "combination": targets},
                )
            )

        if len(known_targets) >= 2:
            for source_id, target_id in combinations(sorted(set(known_targets)), 2):
                relations.append(
                    _relation(
                        document,
                        source_type="technique",
                        source_id=source_id,
                        relation_type="recommended_with",
                        target_type="technique",
                        target_id=target_id,
                        evidence_text=str(raw_value),
                        metadata={
                            "field": "recommended_combinations",
                            "combination": targets,
                            "inferred_pair": True,
                        },
                    )
                )
    return relations


def _extract_contraindication_relations(
    document: NormalizedRagDocument,
    metadata: dict[str, object],
) -> list[RagRelation]:
    relations: list[RagRelation] = []
    for raw_value in _as_list(metadata.get("contraindicated_combinations")):
        targets = normalize_combination_entry(raw_value)
        target = "_".join(targets) if len(targets) > 1 else (targets[0] if targets else "")
        if not target:
            continue
        relations.append(
            _relation(
                document,
                relation_type="contraindicated_with",
                target_type="technique" if target in KNOWN_TECHNIQUE_IDS else "concept",
                target_id=target,
                evidence_text=str(raw_value),
                metadata={"field": "contraindicated_combinations", "combination": targets},
            )
        )
    return relations


def _extract_signal_relations(
    document: NormalizedRagDocument,
    metadata: dict[str, object],
) -> list[RagRelation]:
    relations: list[RagRelation] = []
    for signal in normalize_signals(_as_list(metadata.get("best_for_signals"))):
        relations.append(
            _relation(
                document,
                relation_type="supports_signal",
                target_type="student_signal",
                target_id=signal,
                evidence_text=signal,
                metadata={"field": "best_for_signals"},
            )
        )
    return relations


def _extract_simple_metadata_relations(
    document: NormalizedRagDocument,
    metadata: dict[str, object],
) -> list[RagRelation]:
    relations: list[RagRelation] = []
    for field, relation_type in _RELATION_FIELDS:
        target_type = "activity_type"
        for raw_value in _as_list(metadata.get(field)):
            target_id = slugify_identifier(str(raw_value))
            if not target_id:
                continue
            relations.append(
                _relation(
                    document,
                    relation_type=relation_type,
                    target_type=target_type,
                    target_id=target_id,
                    evidence_text=str(raw_value),
                    metadata={"field": field},
                )
            )
    return relations


def _extract_framework_routes(document: NormalizedRagDocument) -> list[RagRelation]:
    if document.knowledge_type != "study_framework":
        return []
    if "tecnica_vs_metodo" not in document.entity_id:
        return []
    return [
        _relation(
            document,
            relation_type="routes_to",
            target_type="knowledge_type",
            target_id="technique",
            evidence_text=document.title,
            metadata={"inferred_from": "framework_id"},
        ),
        _relation(
            document,
            relation_type="routes_to",
            target_type="knowledge_type",
            target_id="study_method",
            evidence_text=document.title,
            metadata={"inferred_from": "framework_id"},
        ),
    ]


def _relation(
    document: NormalizedRagDocument,
    *,
    relation_type: RagRelationType,
    target_type: str,
    target_id: str,
    evidence_text: str,
    metadata: dict[str, object] | None = None,
    source_type: str | None = None,
    source_id: str | None = None,
) -> RagRelation:
    source_type = source_type or document.knowledge_type
    source_id = source_id or document.entity_id
    relation_key = "|".join(
        [
            source_type,
            source_id,
            relation_type,
            target_type,
            target_id,
            document.document_id,
            evidence_text,
        ]
    )
    relation_hash = hashlib.sha1(relation_key.encode("utf-8")).hexdigest()[:16]
    return RagRelation(
        relation_id=f"rel.{relation_hash}",
        source_type=source_type,
        source_id=source_id,
        relation_type=relation_type,
        target_type=target_type,
        target_id=target_id,
        weight=1.0,
        evidence_text=evidence_text,
        source_document_id=document.document_id,
        metadata=metadata or {},
    )


def _dedupe_relations(relations: Iterable[RagRelation]) -> list[RagRelation]:
    seen: set[tuple[str, str, str, str, str, str]] = set()
    unique: list[RagRelation] = []
    for relation in relations:
        key = (
            relation.source_type,
            relation.source_id,
            relation.relation_type,
            relation.target_type,
            relation.target_id,
            relation.evidence_text,
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(relation)
    return sorted(unique, key=lambda item: item.relation_id)


def _as_list(value: object) -> list[object]:
    if value is None:
        return []
    if isinstance(value, list):
        return [
            item
            for item in value
            if str(item).strip() not in {"", "no especificado", "no aplica"}
        ]
    if isinstance(value, tuple):
        return list(value)
    if str(value).strip() in {"", "no especificado", "no aplica"}:
        return []
    return [value]


__all__ = ["extract_relations"]
