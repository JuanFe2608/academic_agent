"""Structural chunking for the study recommendations corpus."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from schemas.rag import NormalizedRagDocument, RagChunk, RagChunkKind

from .normalization import slugify_identifier

_SECTION_RE = re.compile(r"^##\s+(?P<title>.+)$", re.MULTILINE)


@dataclass(frozen=True)
class MarkdownSection:
    """A second-level Markdown section."""

    title: str
    content: str
    position: int


def chunk_document(document: NormalizedRagDocument) -> list[RagChunk]:
    """Build stable section-level chunks from a normalized document."""

    chunks: list[RagChunk] = []
    for section in split_h2_sections(document.body):
        content = section.content.strip()
        if not content:
            continue
        chunk_kind = infer_chunk_kind(section.title, document.knowledge_type, content)
        chunk_id = _build_chunk_id(document.document_id, section.position, section.title)
        chunks.append(
            RagChunk(
                chunk_id=chunk_id,
                document_id=document.document_id,
                knowledge_type=document.knowledge_type,
                document_type=document.document_type,
                entity_id=document.entity_id,
                section_title=section.title,
                heading_path=[document.title, section.title],
                chunk_kind=chunk_kind,
                content=content,
                metadata={
                    "source_path": document.metadata.source_path,
                    "evidence_level": document.metadata.normalized_metadata.get(
                        "evidence_level"
                    ),
                    "confidence_level": document.metadata.normalized_metadata.get(
                        "confidence_level"
                    ),
                    "best_for_activity_types": document.metadata.normalized_metadata.get(
                        "best_for_activity_types", []
                    ),
                    "best_for_subject_types": document.metadata.normalized_metadata.get(
                        "best_for_subject_types", []
                    ),
                    "best_for_signals": document.metadata.normalized_metadata.get(
                        "best_for_signals_normalized", []
                    ),
                    "not_ideal_for_activity_types": document.metadata.normalized_metadata.get(
                        "not_ideal_for_activity_types", []
                    ),
                    "not_ideal_for_subject_types": document.metadata.normalized_metadata.get(
                        "not_ideal_for_subject_types", []
                    ),
                    "not_ideal_for_signals": document.metadata.normalized_metadata.get(
                        "not_ideal_for_signals_normalized", []
                    ),
                },
                position_in_document=section.position,
                token_estimate=estimate_tokens(content),
                checksum=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            )
        )
    return chunks


def split_h2_sections(markdown_body: str) -> list[MarkdownSection]:
    """Split a document by level-2 headings while preserving subsections."""

    matches = list(_SECTION_RE.finditer(markdown_body))
    if not matches:
        stripped = markdown_body.strip()
        return [MarkdownSection(title="Documento completo", content=stripped, position=1)]

    sections: list[MarkdownSection] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown_body)
        title = match.group("title").strip()
        sections.append(
            MarkdownSection(
                title=title,
                content=markdown_body[start:end].strip(),
                position=index + 1,
            )
        )
    return sections


def infer_chunk_kind(
    section_title: str,
    knowledge_type: str,
    content: str = "",
) -> RagChunkKind:
    """Infer a practical chunk kind from the section title and document type."""

    title = slugify_identifier(section_title)
    body_has_table = any(line.lstrip().startswith("|") for line in content.splitlines())

    if "respuesta_corta_reusable_para_rag" in title or "respuesta_larga_reusable_para_rag" in title:
        return "answer_ready"
    if "definicion" in title:
        return "definition"
    if "objetivo" in title:
        return "objective"
    if "pasos" in title or "paso_a_paso" in title or "protocolo" in title:
        return "steps"
    if "control_de_calidad" in title or "errores_comunes" in title:
        return "quality_control"
    if "adaptacion" in title:
        return "adaptation"
    if "combinaciones_recomendadas" in title or "logica_de_combinacion" in title:
        return "combination"
    if (
        "combinaciones_no_recomendadas" in title
        or "senales_de_que_no" in title
        or "para_que_no_sirve" in title
        or "desventajas" in title
        or "riesgos" in title
    ):
        return "contraindication"
    if "evidencia" in title or "nivel_de_confianza" in title:
        return "evidence"
    if "recomendacion_operativa_para_el_agente" in title or "regla_operativa_para_el_agente" in title:
        return "agent_guidance"
    if "criterios" in title or "tabla_comparativa" in title or "comparacion" in title:
        return "comparison"
    if knowledge_type == "technique_combination_matrix" or body_has_table or "matriz" in title:
        return "matrix"
    if (
        "para_que_sirve" in title
        or "problema_que_resuelve" in title
        or "senales_de_que_conviene" in title
        or "tipo_de_estudiante" in title
        or "tipo_de_actividad" in title
        or "tipo_de_materia" in title
        or "ejemplo_aplicado" in title
        or "mini_caso" in title
    ):
        return "use_case"
    return "agent_guidance"


def estimate_tokens(text: str) -> int:
    """Estimate tokens cheaply for deterministic manifests."""

    return max(1, round(len(re.findall(r"\S+", text)) * 1.3))


def _build_chunk_id(document_id: str, position: int, section_title: str) -> str:
    slug = slugify_identifier(section_title)[:80] or "section"
    return f"{document_id}::s{position:03d}-{slug}"


__all__ = [
    "MarkdownSection",
    "chunk_document",
    "estimate_tokens",
    "infer_chunk_kind",
    "split_h2_sections",
]
