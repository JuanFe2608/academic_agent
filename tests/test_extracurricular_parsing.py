"""Pruebas para parseo de actividades extracurriculares."""

from __future__ import annotations

import agents.support.nodes.collect_extracurricular_details.node as extras_node


def test_parse_extracurricular_items_uses_llm_normalization(monkeypatch) -> None:
    monkeypatch.setattr(
        extras_node,
        "llm_normalize_extracurricular_items",
        lambda _text: [
            {
                "nombre": "Natacion",
                "es_variable": False,
                "detalle": "Martes y jueves 18:00-19:00",
            }
        ],
    )

    items, missing = extras_node.parse_extracurricular_items("natacion fija martes/jueves")

    assert missing == []
    assert len(items) == 1
    assert items[0].nombre == "Natacion"
    assert items[0].es_variable is False


def test_parse_extracurricular_items_fallback_without_llm(monkeypatch) -> None:
    monkeypatch.setattr(
        extras_node,
        "llm_normalize_extracurricular_items",
        lambda _text: None,
    )

    items, missing = extras_node.parse_extracurricular_items(
        "Futbol variable, martes y jueves 18:00-19:00"
    )

    assert len(items) == 1
    assert missing == []
    assert items[0].nombre == "Futbol"
    assert items[0].es_variable is True


def test_parse_extracurricular_items_compacts_long_activity_name(monkeypatch) -> None:
    monkeypatch.setattr(
        extras_node,
        "llm_normalize_extracurricular_items",
        lambda _text: None,
    )

    items, missing = extras_node.parse_extracurricular_items(
        "Salida con mis amigas a comer helado y de shiping martes a miercoles de 4pm a 6 pm",
        expected_is_variable=False,
    )

    assert missing == []
    assert len(items) == 1
    assert items[0].nombre.lower() == "salida con amigas"
