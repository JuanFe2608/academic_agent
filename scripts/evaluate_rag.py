#!/usr/bin/env python
"""Compatibility entrypoint for the RAG evaluation CLI."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_DEV_SCRIPT_PATH = Path(__file__).resolve().parent / "dev" / "evaluate_rag.py"
_SPEC = importlib.util.spec_from_file_location("_evaluate_rag_dev", _DEV_SCRIPT_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"No se pudo cargar {_DEV_SCRIPT_PATH}")
_DEV_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_DEV_MODULE)

_filter_cases = _DEV_MODULE._filter_cases
_print_summary = _DEV_MODULE._print_summary
_quality_gate_status = _DEV_MODULE._quality_gate_status
_resolve_output_path = _DEV_MODULE._resolve_output_path
_write_report = _DEV_MODULE._write_report
main = _DEV_MODULE.main

__all__ = [
    "_filter_cases",
    "_print_summary",
    "_quality_gate_status",
    "_resolve_output_path",
    "_write_report",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
