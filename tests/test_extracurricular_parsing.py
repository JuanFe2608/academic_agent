"""Pruebas para parseo de actividades extracurriculares."""

from __future__ import annotations

import agents.support.nodes.collect_extracurricular_details.parsing as extras_parsing


def test_parse_extracurricular_items_uses_llm_normalization(monkeypatch) -> None:
    monkeypatch.setattr(
        extras_parsing,
        "llm_normalize_extracurricular_items",
        lambda _text: [
            {
                "nombre": "Natacion",
                "es_variable": False,
                "detalle": "Martes y jueves 18:00-19:00",
            }
        ],
    )

    items, missing = extras_parsing.parse_extracurricular_items(
        "natacion fija martes/jueves"
    )

    assert missing == []
    assert len(items) == 1
    assert items[0].nombre == "Natacion"
    assert items[0].es_variable is False


def test_parse_extracurricular_items_fallback_without_llm(monkeypatch) -> None:
    monkeypatch.setattr(
        extras_parsing,
        "llm_normalize_extracurricular_items",
        lambda _text: None,
    )

    items, missing = extras_parsing.parse_extracurricular_items(
        "Futbol variable, martes y jueves 18:00-19:00"
    )

    assert len(items) == 1
    assert missing == []
    assert items[0].nombre == "Futbol"
    assert items[0].es_variable is True


def test_parse_extracurricular_text_normalizes_free_language_all_days(monkeypatch) -> None:
    monkeypatch.setattr(
        extras_parsing,
        "llm_normalize_extracurricular_items",
        lambda _text: None,
    )

    items, missing = extras_parsing.parse_extracurricular_items(
        "Voy todos los dias al gym desde las 5 am hasta las 6 am"
    )

    assert missing == []
    assert len(items) == 1
    assert items[0].nombre == "Gym"
    assert items[0].es_variable is False
    assert items[0].frecuencia == "todos los dias, desde lunes a domingo"
    assert items[0].hora_inicio == "05:00"
    assert items[0].hora_fin == "06:00"
    assert items[0].dias == [
        "Lunes",
        "Martes",
        "Miercoles",
        "Jueves",
        "Viernes",
        "Sabado",
        "Domingo",
    ]


def test_parse_extracurricular_items_splits_multiple_free_text_activities(monkeypatch) -> None:
    monkeypatch.setattr(
        extras_parsing,
        "llm_normalize_extracurricular_items",
        lambda _text: None,
    )

    items, missing = extras_parsing.parse_extracurricular_items(
        "Voy al gym todos los dias de 5 am a 6 am y saco a mi perro solo los lunes martes jueves y viernes de 4 am a 5 am"
    )

    assert missing == []
    assert len(items) == 2
    assert items[0].nombre == "Gym"
    assert items[1].nombre == "Sacar al perro"


def test_parse_extracurricular_items_splits_multiple_activities_by_comma(monkeypatch) -> None:
    monkeypatch.setattr(
        extras_parsing,
        "llm_normalize_extracurricular_items",
        lambda _text: None,
    )

    items, missing = extras_parsing.parse_extracurricular_items(
        "Gym todos los dias de 5 am a 6 am, saco a mi perro lunes martes jueves y viernes de 4 am a 5 am"
    )

    assert missing == []
    assert len(items) == 2
    assert items[0].nombre == "Gym"
    assert items[1].nombre == "Sacar al perro"


def test_parse_extracurricular_items_compacts_long_activity_name(monkeypatch) -> None:
    monkeypatch.setattr(
        extras_parsing,
        "llm_normalize_extracurricular_items",
        lambda _text: None,
    )

    items, missing = extras_parsing.parse_extracurricular_items(
        "Salida con mis amigas a comer helado y de shiping martes a miercoles de 4pm a 6 pm",
        expected_is_variable=False,
    )

    assert missing == []
    assert len(items) == 1
    assert items[0].nombre.lower() == "salida con amigas"


def test_parse_extracurricular_items_accepts_plural_days_and_mixed_24h_with_pm(monkeypatch) -> None:
    monkeypatch.setattr(
        extras_parsing,
        "llm_normalize_extracurricular_items",
        lambda _text: None,
    )

    items, missing = extras_parsing.parse_extracurricular_items(
        "Hago ejercicio todos los dias de 5 am a 6 am y saco a mi perro los lunes de 11 am a 13 pm,voy a bailar los domingos de 1 pm a 3pm"
    )

    assert missing == []
    assert len(items) == 3
    assert items[0].nombre == "Ejercicio"
    assert items[1].dias == ["Lunes"]
    assert items[2].dias == ["Domingo"]


def test_parse_extracurricular_items_keeps_previous_day_for_then_clause_and_requests_missing_time(monkeypatch) -> None:
    monkeypatch.setattr(
        extras_parsing,
        "llm_normalize_extracurricular_items",
        lambda _text: None,
    )

    items, missing = extras_parsing.parse_extracurricular_items(
        "voy los dias sabados al gimnasio de 10 am a 12 pm, luego voy al centro comercial de 2 pm a 4 pm y los domingos voy a la iglesia",
        expected_is_variable=False,
    )

    assert len(items) == 2
    assert items[0].nombre == "Gym"
    assert items[0].dias == ["Sabado"]
    assert items[0].hora_inicio == "10:00"
    assert items[0].hora_fin == "12:00"
    assert items[1].nombre == "Centro Comercial"
    assert items[1].dias == ["Sabado"]
    assert items[1].hora_inicio == "14:00"
    assert items[1].hora_fin == "16:00"
    assert missing == ["Iglesia: hora de inicio y fin"]
