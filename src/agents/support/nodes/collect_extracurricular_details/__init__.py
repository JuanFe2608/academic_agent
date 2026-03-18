"""API pública perezosa del flujo extracurricular."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "collect_extracurricular_details",
    "parse_extracurricular_text",
    "parse_extracurricular_items",
]

_MODULE_BY_NAME = {
    "collect_extracurricular_details": "agents.support.nodes.collect_extracurricular_details.node",
    "parse_extracurricular_text": "agents.support.nodes.collect_extracurricular_details.parsing",
    "parse_extracurricular_items": "agents.support.nodes.collect_extracurricular_details.parsing",
}


def __getattr__(name: str) -> Any:
    module_name = _MODULE_BY_NAME.get(name)
    if not module_name:
        raise AttributeError(name)
    module = import_module(module_name)
    return getattr(module, name)
