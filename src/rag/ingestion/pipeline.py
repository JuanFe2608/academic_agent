"""Top-level local build pipeline for the study recommendations RAG corpus."""

from __future__ import annotations

import json
from pathlib import Path

from schemas.rag import RagCorpusBuildResult, RagValidationIssue

from .chunking import chunk_document
from .contracts import ParsedMarkdownDocument
from .frontmatter import FrontmatterError, load_markdown_document
from .normalization import normalize_document
from .relations import extract_relations
from .validation import validate_parsed_document

DEFAULT_CORPUS_ROOT = Path("knowledge_base/study_recommendations")
CORPUS_NAME = "study_recommendations"
CORPUS_VERSION = "phase_a_v1"


def build_rag_corpus(
    corpus_root: str | Path = DEFAULT_CORPUS_ROOT,
    *,
    write_artifacts: bool = False,
) -> RagCorpusBuildResult:
    """Validate, normalize, chunk and extract relations without DB access."""

    root = Path(corpus_root)
    raw_root = root / "raw"
    issues: list[RagValidationIssue] = []
    parsed_documents: list[ParsedMarkdownDocument] = []

    if not raw_root.exists():
        return RagCorpusBuildResult(
            issues=[
                RagValidationIssue(
                    severity="error",
                    code="missing_raw_root",
                    message=f"No existe el directorio fuente: {raw_root.as_posix()}",
                    source_path=raw_root.as_posix(),
                )
            ]
        )

    for path in sorted(raw_root.rglob("*.md")):
        try:
            parsed = load_markdown_document(path, corpus_root=root)
        except (FrontmatterError, UnicodeDecodeError) as exc:
            issues.append(
                RagValidationIssue(
                    severity="error",
                    code="frontmatter_parse_error",
                    message=str(exc),
                    source_path=path.relative_to(root).as_posix(),
                )
            )
            continue

        issues.extend(validate_parsed_document(parsed))
        parsed_documents.append(parsed)

    documents = []
    for parsed in parsed_documents:
        if any(issue.severity == "error" and issue.source_path == parsed.relative_path for issue in issues):
            continue
        try:
            documents.append(normalize_document(parsed))
        except Exception as exc:  # noqa: BLE001 - convert ingestion failures into issues
            issues.append(
                RagValidationIssue(
                    severity="error",
                    code="normalization_error",
                    message=str(exc),
                    source_path=parsed.relative_path,
                )
            )

    chunks = [chunk for document in documents for chunk in chunk_document(document)]
    relations = [
        relation for document in documents for relation in extract_relations(document)
    ]

    result = RagCorpusBuildResult(
        documents=documents,
        chunks=chunks,
        relations=relations,
        issues=issues,
    )
    if write_artifacts and not result.has_errors:
        write_corpus_artifacts(root, result)
    return result


def write_corpus_artifacts(
    corpus_root: str | Path,
    result: RagCorpusBuildResult,
) -> dict[str, Path]:
    """Write deterministic inventory, chunk and relation artifacts."""

    root = Path(corpus_root)
    manifests_dir = root / "manifests"
    chunks_dir = root / "processed" / "chunks"
    manifests_dir.mkdir(parents=True, exist_ok=True)
    chunks_dir.mkdir(parents=True, exist_ok=True)

    inventory_path = manifests_dir / "document_inventory.json"
    chunks_path = chunks_dir / "chunks.jsonl"
    chunk_manifest_path = manifests_dir / "chunk_manifest.json"
    relation_manifest_path = manifests_dir / "relation_manifest.json"

    _write_json(
        inventory_path,
        {
            "corpus_name": CORPUS_NAME,
            "corpus_version": CORPUS_VERSION,
            "source_root": root.as_posix(),
            "documents_count": len(result.documents),
            "documents": [
                document.metadata.model_dump(mode="json")
                for document in sorted(
                    result.documents,
                    key=lambda item: item.metadata.source_path,
                )
            ],
        },
    )

    with chunks_path.open("w", encoding="utf-8") as handle:
        for chunk in sorted(result.chunks, key=lambda item: item.chunk_id):
            handle.write(
                json.dumps(chunk.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
            )
            handle.write("\n")

    _write_json(
        chunk_manifest_path,
        {
            "corpus_name": CORPUS_NAME,
            "corpus_version": CORPUS_VERSION,
            "chunks_count": len(result.chunks),
            "chunks": [
                chunk.model_dump(mode="json", exclude={"content"})
                for chunk in sorted(result.chunks, key=lambda item: item.chunk_id)
            ],
        },
    )

    _write_json(
        relation_manifest_path,
        {
            "corpus_name": CORPUS_NAME,
            "corpus_version": CORPUS_VERSION,
            "relations_count": len(result.relations),
            "relations": [
                relation.model_dump(mode="json")
                for relation in sorted(result.relations, key=lambda item: item.relation_id)
            ],
        },
    )

    return {
        "inventory": inventory_path,
        "chunks": chunks_path,
        "chunk_manifest": chunk_manifest_path,
        "relation_manifest": relation_manifest_path,
    }


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


__all__ = [
    "CORPUS_NAME",
    "CORPUS_VERSION",
    "DEFAULT_CORPUS_ROOT",
    "build_rag_corpus",
    "write_corpus_artifacts",
]
