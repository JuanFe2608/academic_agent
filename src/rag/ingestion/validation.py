"""Corpus validation for RAG source documents."""

from __future__ import annotations

from pathlib import Path

from schemas.rag import RagValidationIssue

from .contracts import ParsedMarkdownDocument
from .normalization import EXPECTED_DIR_BY_KNOWLEDGE_TYPE, ID_KEY_BY_KNOWLEDGE_TYPE

_REUSABLE_SECTION_MARKERS = (
    "respuesta corta reusable para rag",
    "respuesta larga reusable para rag",
    "recomendacion operativa para el agente",
    "regla operativa para el agente",
    "pasos de aplicacion",
    "paso a paso detallado",
    "control de calidad",
)


def validate_parsed_document(parsed: ParsedMarkdownDocument) -> list[RagValidationIssue]:
    """Validate the corpus contract before chunking or persistence."""

    issues: list[RagValidationIssue] = []
    metadata = parsed.frontmatter
    source_path = parsed.relative_path
    knowledge_type = str(metadata.get("knowledge_type") or "").strip()

    _require(metadata, "knowledge_type", issues, source_path)
    _require(metadata, "name", issues, source_path)
    _require(metadata, "status", issues, source_path)
    _require(metadata, "version", issues, source_path)

    id_key = ID_KEY_BY_KNOWLEDGE_TYPE.get(knowledge_type)
    if id_key is None:
        issues.append(
            RagValidationIssue(
                severity="error",
                code="unsupported_knowledge_type",
                message=f"knowledge_type no soportado: {knowledge_type!r}",
                source_path=source_path,
            )
        )
    else:
        _require(metadata, id_key, issues, source_path)

    expected_dir = EXPECTED_DIR_BY_KNOWLEDGE_TYPE.get(knowledge_type)
    if expected_dir is not None:
        parts = Path(parsed.relative_path).parts
        actual_dir = parts[1] if len(parts) > 1 and parts[0] == "raw" else None
        if actual_dir != expected_dir:
            issues.append(
                RagValidationIssue(
                    severity="error",
                    code="source_path_mismatch",
                    message=(
                        f"La ruta debe estar en raw/{expected_dir}/ para "
                        f"knowledge_type={knowledge_type!r}."
                    ),
                    source_path=source_path,
                )
            )

    if not _has_h1(parsed.body):
        issues.append(
            RagValidationIssue(
                severity="error",
                code="missing_h1",
                message="El documento debe tener un heading principal '# '.",
                source_path=source_path,
            )
        )

    if not _has_h2(parsed.body):
        issues.append(
            RagValidationIssue(
                severity="error",
                code="missing_h2_sections",
                message="El documento debe tener secciones '##' reutilizables.",
                source_path=source_path,
            )
        )

    if not _has_reusable_or_operational_section(parsed.body):
        issues.append(
            RagValidationIssue(
                severity="error",
                code="missing_operational_section",
                message="Debe existir una seccion reusable o de guia operacional.",
                source_path=source_path,
            )
        )

    return issues


def _require(
    metadata: dict[str, object],
    key: str,
    issues: list[RagValidationIssue],
    source_path: str,
) -> None:
    value = metadata.get(key)
    if value is None or str(value).strip() == "":
        issues.append(
            RagValidationIssue(
                severity="error",
                code="missing_required_frontmatter",
                message=f"Falta el campo requerido de frontmatter: {key}.",
                source_path=source_path,
            )
        )


def _has_h1(body: str) -> bool:
    return any(line.startswith("# ") for line in body.splitlines())


def _has_h2(body: str) -> bool:
    return any(line.startswith("## ") for line in body.splitlines())


def _has_reusable_or_operational_section(body: str) -> bool:
    lowered = body.lower()
    return any(marker in lowered for marker in _REUSABLE_SECTION_MARKERS)


__all__ = ["validate_parsed_document"]
