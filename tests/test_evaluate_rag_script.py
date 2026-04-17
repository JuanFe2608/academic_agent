"""Tests for the RAG evaluation CLI helpers."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def test_write_report_accepts_directory_output(tmp_path: Path) -> None:
    module = _load_script_module()

    output_path = module._write_report(
        tmp_path,
        {"backend": "postgres", "ok": True},
        backend="postgres",
    )

    assert output_path == tmp_path / "postgres_report.json"
    assert json.loads(output_path.read_text(encoding="utf-8"))["ok"] is True


def test_write_report_preserves_explicit_file_output(tmp_path: Path) -> None:
    module = _load_script_module()
    requested = tmp_path / "custom_report.json"

    output_path = module._write_report(
        requested,
        {"backend": "local", "ok": True},
        backend="local",
    )

    assert output_path == requested
    assert json.loads(requested.read_text(encoding="utf-8"))["backend"] == "local"


def _load_script_module():
    script_path = Path("scripts/evaluate_rag.py")
    spec = importlib.util.spec_from_file_location("evaluate_rag_script", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
