"""Normalization rules for the study recommendations corpus."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

from schemas.rag import NormalizedRagDocument, RagDocumentMetadata

from .contracts import ParsedMarkdownDocument

ID_KEY_BY_KNOWLEDGE_TYPE = {
    "technique": "technique_id",
    "study_method": "method_id",
    "study_framework": "framework_id",
    "technique_combination_matrix": "matrix_id",
}

EXPECTED_DIR_BY_KNOWLEDGE_TYPE = {
    "technique": "techniques",
    "study_method": "methods",
    "study_framework": "frameworks",
    "technique_combination_matrix": "matrices",
}

TECHNIQUE_ALIASES = {
    "active_recall": "active_recall",
    "recuperacion_activa": "active_recall",
    "recuperacion_activa_rag": "active_recall",
    "practica_de_recuperacion": "active_recall",
    "practica_recuperacion": "active_recall",
    "retrieval_practice": "active_recall",
    "autoevaluacion": "active_recall",
    "evaluacion_de_la_practica": "active_recall",
    "preguntas_de_autoevaluacion": "active_recall",
    "pomodoro": "pomodoro",
    "tecnica_pomodoro": "pomodoro",
    "metodo_pomodoro": "pomodoro",
    "feynman": "feynman",
    "tecnica_feynman": "feynman",
    "metodo_feynman": "feynman",
    "autoexplicacion": "feynman",
    "explicacion_simple": "feynman",
    "cornell": "cornell",
    "metodo_cornell": "cornell",
    "notas_cornell": "cornell",
    "toma_de_apuntes_cornell": "cornell",
    "mapas_conceptuales": "mapas_conceptuales",
    "mapa_conceptual": "mapas_conceptuales",
    "concept_mapping": "mapas_conceptuales",
    "mnemotecnia": "mnemotecnia",
    "mnemoctenia": "mnemotecnia",
    "nemotecnia": "mnemotecnia",
    "mnemonics": "mnemotecnia",
    "repeticion_espaciada": "repeticion_espaciada",
    "practica_espaciada": "repeticion_espaciada",
    "practica_distribuida": "repeticion_espaciada",
    "repaso_distribuido": "repeticion_espaciada",
    "repaso_espaciado": "repeticion_espaciada",
    "spaced_repetition": "repeticion_espaciada",
    "interleaving": "interleaving",
    "intercalado": "interleaving",
    "estudio_intercalado": "interleaving",
    "practica_intercalada": "interleaving",
}

KNOWN_TECHNIQUE_IDS = {
    "active_recall",
    "cornell",
    "feynman",
    "interleaving",
    "mapas_conceptuales",
    "mnemotecnia",
    "pomodoro",
    "repeticion_espaciada",
}

SIGNAL_ALIASES = {
    "procrastina": ["procrastination"],
    "procrastinacion": ["procrastination"],
    "se_distrae_facil": ["distraction"],
    "distraccion": ["distraction"],
    "no_puede_explicar": ["explanation_gap"],
    "dificultad_para_explicar": ["explanation_gap"],
    "relee_mucho": ["passive_review_dependence"],
    "relectura_pasiva": ["passive_review_dependence"],
    "no_se_autoevalua": ["passive_review_dependence"],
    "siente_familiaridad_pero_no_recuerda": ["passive_review_dependence"],
    "olvida_rapido": ["rapid_forgetting"],
    "olvido_rapido": ["rapid_forgetting"],
    "apuntes_desordenados": ["note_organization"],
    "notas_desordenadas": ["note_organization"],
    "apuntes_poco_utiles": ["note_organization"],
    "necesita_estructura": ["procrastination", "note_organization"],
    "no_sostiene_sesiones_largas": ["distraction"],
    "confunde_tipos_de_ejercicio": ["difficulty_switching_topics"],
    "cambia_mal_de_tema": ["difficulty_switching_topics"],
    "no_conecta_ideas": ["concept_connections"],
    "conceptos_desconectados": ["concept_connections"],
    "memoria_exacta": ["exact_memory"],
    "detalle_exactos": ["exact_memory"],
}


def normalize_document(parsed: ParsedMarkdownDocument) -> NormalizedRagDocument:
    """Convert parsed frontmatter into the canonical RAG document contract."""

    metadata = parsed.frontmatter
    knowledge_type = str(metadata.get("knowledge_type") or "").strip()
    id_key = ID_KEY_BY_KNOWLEDGE_TYPE.get(knowledge_type, "")
    raw_entity_id = str(metadata.get(id_key) or "").strip() if id_key else ""
    entity_id = normalize_entity_id(knowledge_type, raw_entity_id)
    document_type = normalize_document_type(knowledge_type, metadata)
    document_id = f"{knowledge_type}.{entity_id}"
    title = extract_title(parsed.body) or str(metadata.get("name") or entity_id)

    aliases = _normalize_aliases(metadata.get("aliases"))
    if raw_entity_id and raw_entity_id != entity_id:
        aliases.append(raw_entity_id)
    if entity_id == "active_recall":
        aliases.extend(["recuperacion_activa", "recuperacion activa", "practica de recuperacion"])
    aliases = _unique_strings(aliases)

    normalized_metadata = normalize_metadata_fields(metadata)
    normalized_metadata.update(
        {
            "document_id": document_id,
            "document_type": document_type,
            "entity_id": entity_id,
            "id_key": id_key,
            "raw_entity_id": raw_entity_id,
            "source_path": parsed.relative_path,
        }
    )

    return NormalizedRagDocument(
        document_id=document_id,
        knowledge_type=knowledge_type,  # type: ignore[arg-type]
        document_type=document_type,
        entity_id=entity_id,
        title=title,
        body=parsed.body,
        metadata=RagDocumentMetadata(
            document_id=document_id,
            knowledge_type=knowledge_type,  # type: ignore[arg-type]
            document_type=document_type,
            entity_id=entity_id,
            name=str(metadata.get("name") or title),
            aliases=aliases,
            aliases_normalized=_unique_strings(slugify_identifier(alias) for alias in aliases),
            status=str(metadata.get("status") or ""),
            version=str(metadata.get("version") or ""),
            source_path=parsed.relative_path,
            checksum=parsed.checksum,
            raw_metadata=dict(metadata),
            normalized_metadata=normalized_metadata,
        ),
    )


def normalize_metadata_fields(metadata: dict[str, object]) -> dict[str, object]:
    """Normalize known fields while preserving raw frontmatter separately."""

    normalized: dict[str, object] = {}
    for key, value in metadata.items():
        if key in {"best_for_signals", "not_ideal_for_signals"}:
            normalized[f"{key}_normalized"] = normalize_signals(_as_list(value))
        elif key in {
            "recommended_combinations",
            "contraindicated_combinations",
            "component_techniques",
            "optional_techniques",
            "excluded_techniques",
            "included_techniques",
        }:
            normalized[f"{key}_normalized"] = [
                normalize_combination_entry(item) for item in _as_list(value)
            ]
        else:
            normalized[key] = value
    return normalized


def normalize_document_type(
    knowledge_type: str,
    metadata: dict[str, object],
) -> str:
    """Return an explicit document type even when frontmatter omits it."""

    explicit = str(metadata.get("document_type") or "").strip()
    if explicit:
        return slugify_identifier(explicit)
    if knowledge_type == "technique":
        return "study_technique"
    if knowledge_type == "study_method":
        return "study_method"
    if knowledge_type == "study_framework":
        return "study_framework"
    if knowledge_type == "technique_combination_matrix":
        return "technique_combination_matrix"
    return slugify_identifier(knowledge_type)


def normalize_entity_id(knowledge_type: str, value: str) -> str:
    """Normalize entity identifiers without changing operational method IDs."""

    slug = slugify_identifier(value)
    if knowledge_type == "technique":
        return TECHNIQUE_ALIASES.get(slug, slug)
    return slug


def normalize_technique_id(value: str) -> str:
    """Normalize a possible technique ID or alias."""

    slug = slugify_identifier(value)
    return TECHNIQUE_ALIASES.get(slug, slug)


def is_known_technique(value: str) -> bool:
    return normalize_technique_id(value) in KNOWN_TECHNIQUE_IDS


def normalize_signals(values: Iterable[object]) -> list[str]:
    """Map corpus signal vocabulary into the Radar weakness tag vocabulary."""

    normalized: list[str] = []
    for value in values:
        slug = slugify_identifier(str(value))
        normalized.extend(SIGNAL_ALIASES.get(slug, [slug]))
    return _unique_strings(normalized)


def normalize_combination_entry(value: object) -> list[str]:
    """Normalize one relation/combo entry into canonical IDs where possible."""

    text = str(value or "").strip()
    if not text or slugify_identifier(text) in {"no_especificado", "no_aplica"}:
        return []
    parts = split_combination_text(text)
    return _unique_strings(_normalize_relation_token(part) for part in parts if part.strip())


def split_combination_text(text: str) -> list[str]:
    """Split simple combination strings while keeping descriptive phrases useful."""

    normalized = text.replace("→", "+").replace("/", "+")
    if "+" in normalized:
        return [part.strip() for part in normalized.split("+")]
    return [normalized.strip()]


def extract_title(markdown_body: str) -> str | None:
    for line in markdown_body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def slugify_identifier(value: str) -> str:
    """Create accent-insensitive identifiers aligned with current code IDs."""

    normalized = unicodedata.normalize("NFKD", str(value).strip().lower())
    ascii_value = "".join(char for char in normalized if not unicodedata.combining(char))
    ascii_value = ascii_value.replace("&", " y ")
    ascii_value = re.sub(r"[^a-z0-9]+", "_", ascii_value)
    return re.sub(r"_+", "_", ascii_value).strip("_")


def _normalize_relation_token(value: str) -> str:
    slug = slugify_identifier(value)
    return TECHNIQUE_ALIASES.get(slug, slug)


def _normalize_aliases(value: object) -> list[str]:
    return [str(item).strip() for item in _as_list(value) if str(item).strip()]


def _as_list(value: object) -> list[object]:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    if str(value).strip() in {"", "no especificado", "no aplica"}:
        return []
    return [value]


def _unique_strings(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            unique.append(value)
    return unique


__all__ = [
    "EXPECTED_DIR_BY_KNOWLEDGE_TYPE",
    "ID_KEY_BY_KNOWLEDGE_TYPE",
    "KNOWN_TECHNIQUE_IDS",
    "SIGNAL_ALIASES",
    "TECHNIQUE_ALIASES",
    "extract_title",
    "is_known_technique",
    "normalize_combination_entry",
    "normalize_document",
    "normalize_document_type",
    "normalize_entity_id",
    "normalize_metadata_fields",
    "normalize_signals",
    "normalize_technique_id",
    "slugify_identifier",
    "split_combination_text",
]
