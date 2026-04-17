"""Frontmatter loading for the local RAG corpus."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from .contracts import ParsedMarkdownDocument

_FRONTMATTER_DELIMITER = "---"
_LIST_ITEM_RE = re.compile(r"^(?P<indent>\s*)-\s*(?P<value>.*)$")
_DICT_PAIR_RE = re.compile(r"^(?P<key>[A-Za-z_][\w-]*)\s*:\s*(?P<value>.*)$")


class FrontmatterError(ValueError):
    """Raised when a source document has invalid frontmatter."""


def load_markdown_document(path: Path, *, corpus_root: Path) -> ParsedMarkdownDocument:
    """Load a Markdown file and parse its YAML-like frontmatter."""

    raw_bytes = path.read_bytes()
    text = raw_bytes.decode("utf-8")
    frontmatter_text, body = split_frontmatter(text)
    return ParsedMarkdownDocument(
        source_path=path,
        relative_path=path.relative_to(corpus_root).as_posix(),
        checksum=hashlib.sha256(raw_bytes).hexdigest(),
        frontmatter=parse_frontmatter(frontmatter_text),
        body=body.strip(),
    )


def split_frontmatter(text: str) -> tuple[str, str]:
    """Split a Markdown document into raw frontmatter and body."""

    lines = text.splitlines()
    if not lines or lines[0].strip() != _FRONTMATTER_DELIMITER:
        raise FrontmatterError("El documento debe iniciar con frontmatter YAML.")

    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == _FRONTMATTER_DELIMITER:
            return "\n".join(lines[1:index]), "\n".join(lines[index + 1 :])

    raise FrontmatterError("No se encontro el cierre del frontmatter YAML.")


def parse_frontmatter(raw_frontmatter: str) -> dict[str, object]:
    """Parse the subset of YAML used by the curated corpus."""

    data: dict[str, object] = {}
    lines = raw_frontmatter.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip() or line.lstrip().startswith("#"):
            index += 1
            continue
        if line[:1].isspace():
            raise FrontmatterError(f"Indentacion inesperada en frontmatter: {line!r}")

        key, raw_value = _split_key_value(line)
        if raw_value.strip():
            data[key] = _parse_scalar(raw_value.strip())
            index += 1
            continue

        block: list[str] = []
        index += 1
        while index < len(lines):
            next_line = lines[index]
            if next_line.strip() and not next_line[:1].isspace():
                break
            block.append(next_line)
            index += 1
        data[key] = _parse_block(block)

    return data


def _split_key_value(line: str) -> tuple[str, str]:
    if ":" not in line:
        raise FrontmatterError(f"Linea de frontmatter sin separador ':': {line!r}")
    key, value = line.split(":", 1)
    key = key.strip()
    if not key:
        raise FrontmatterError(f"Clave de frontmatter vacia: {line!r}")
    return key, value


def _parse_block(block: list[str]) -> object:
    meaningful = [line for line in block if line.strip()]
    if not meaningful:
        return []

    if all(_LIST_ITEM_RE.match(line) for line in meaningful if line.lstrip().startswith("-")):
        parsed_list: list[object] = []
        index = 0
        while index < len(meaningful):
            line = meaningful[index]
            match = _LIST_ITEM_RE.match(line)
            if match is None:
                raise FrontmatterError(f"Bloque de lista invalido: {line!r}")

            indent = len(match.group("indent"))
            value = match.group("value").strip()
            dict_match = _DICT_PAIR_RE.match(value)
            if dict_match is None:
                parsed_list.append(_parse_scalar(value))
                index += 1
                continue

            item: dict[str, object] = {
                dict_match.group("key"): _parse_scalar(dict_match.group("value").strip())
            }
            index += 1
            while index < len(meaningful):
                nested_line = meaningful[index]
                nested_match = _LIST_ITEM_RE.match(nested_line)
                if nested_match is not None and len(nested_match.group("indent")) <= indent:
                    break
                nested_key, nested_value = _split_key_value(nested_line.strip())
                item[nested_key] = _parse_scalar(nested_value.strip())
                index += 1
            parsed_list.append(item)
        return parsed_list

    return "\n".join(line.strip() for line in meaningful)


def _parse_scalar(value: str) -> Any:
    if value == "[]":
        return []
    if value in {"{}", "null", "NULL", "~"}:
        return None
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?\d+\.\d+", value):
        return float(value)
    return value


__all__ = [
    "FrontmatterError",
    "load_markdown_document",
    "parse_frontmatter",
    "split_frontmatter",
]
