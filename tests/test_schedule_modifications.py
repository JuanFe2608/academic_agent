"""Pruebas para modificaciones del horario desde lenguaje natural."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from agents.support.nodes.apply_modifications.node import apply_modifications
from agents.support.nodes.validate_schedule.node import validate_schedule
from agents.support.state import AgentState, Event, ExtracurricularItem, new_event_id


def test_validate_schedule_detects_direct_extracurricular_change_request() -> None:
    state = AgentState(
        phase="validate",
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="Quiero cambiar la actividad de Golf a martes y jueves de 6 pm a 7 pm")],
        extracurricular=[
            ExtracurricularItem(nombre="Golf", es_variable=False, detalle="Lunes 18:00-19:00"),
            ExtracurricularItem(nombre="Gym", es_variable=False, detalle="Martes 05:00-06:00"),
        ],
    )

    update = validate_schedule(state)

    assert update["awaiting_user_input"] is False
    assert update["replan"]["change_request"]["target"] == "extracurricular"
    assert update["replan"]["change_request"]["activity_name"] == "Golf"
    assert update["replan"]["change_request"]["operation"] == "update"


def test_validate_schedule_option_one_opens_target_menu() -> None:
    state = AgentState(
        phase="validate",
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="1")],
    )

    update = validate_schedule(state)

    assert update["awaiting_user_input"] is True
    assert update["replan"]["change_request"]["operation"] == "update"
    assert update["replan"]["change_request"]["stage"] == "awaiting_target"
    assert "horario academico" in update["replan"]["pending_prompt"].lower()
    assert "horario academico" in update["messages"][0].content.lower()


def test_validate_schedule_option_two_opens_add_target_menu() -> None:
    state = AgentState(
        phase="validate",
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="2")],
    )

    update = validate_schedule(state)

    assert update["awaiting_user_input"] is True
    assert update["replan"]["change_request"]["operation"] == "add"
    assert update["replan"]["change_request"]["stage"] == "awaiting_target"
    assert "actividad extracurricular" in update["messages"][0].content.lower()


def test_validate_schedule_target_menu_advances_to_details_prompt() -> None:
    state = AgentState(
        phase="validate",
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="3")],
        replan={"change_request": {"operation": "update", "stage": "awaiting_target"}},
    )

    update = validate_schedule(state)

    assert update["awaiting_user_input"] is True
    assert update["replan"]["change_request"]["target"] == "extracurricular"
    assert update["replan"]["change_request"]["stage"] == "awaiting_details"
    assert "actividad extracurricular" in update["replan"]["pending_prompt"].lower()
    assert "actividad extracurricular" in update["messages"][0].content.lower()


def test_validate_schedule_detects_delete_extracurricular_request() -> None:
    state = AgentState(
        phase="validate",
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="Quiero eliminar la actividad de Golf")],
        extracurricular=[
            ExtracurricularItem(nombre="Golf", es_variable=False, detalle="Lunes 18:00-19:00"),
            ExtracurricularItem(nombre="Gym", es_variable=False, detalle="Martes 05:00-06:00"),
        ],
    )

    update = validate_schedule(state)

    assert update["awaiting_user_input"] is False
    assert update["replan"]["change_request"]["target"] == "extracurricular"
    assert update["replan"]["change_request"]["activity_name"] == "Golf"
    assert update["replan"]["change_request"]["operation"] == "delete"


def test_apply_modifications_reports_unknown_extracurricular() -> None:
    state = AgentState(
        phase="validate",
        extracurricular=[
            ExtracurricularItem(nombre="Gym", es_variable=False, detalle="Lunes 05:00-06:00")
        ],
        replan={
            "change_request": {
                "target": "extracurricular",
                "operation": "update",
                "activity_name": "Golf",
                "details": "Quiero cambiar la actividad de Golf",
            }
        },
    )

    update = apply_modifications(state)

    assert update["awaiting_user_input"] is True
    assert "no existe" in update["replan"]["pending_prompt"].lower()
    assert "gym" in update["replan"]["pending_prompt"].lower()


def test_apply_modifications_updates_specific_extracurricular_and_preserves_others() -> None:
    state = AgentState(
        phase="validate",
        timezone="America/Bogota",
        extracurricular=[
            ExtracurricularItem(nombre="Golf", es_variable=False, detalle="Lunes 18:00-19:00"),
            ExtracurricularItem(nombre="Gym", es_variable=False, detalle="Martes 05:00-06:00"),
        ],
        events=[
            Event(
                id=new_event_id(),
                dia="Lunes",
                inicio="18:00",
                fin="19:00",
                titulo="Golf",
                tipo="confirmado",
                categoria="extracurricular",
                origen="user_text",
                timezone="America/Bogota",
            ),
            Event(
                id=new_event_id(),
                dia="Martes",
                inicio="05:00",
                fin="06:00",
                titulo="Gym",
                tipo="confirmado",
                categoria="extracurricular",
                origen="user_text",
                timezone="America/Bogota",
            ),
        ],
        replan={
            "change_request": {
                "target": "extracurricular",
                "operation": "update",
                "activity_name": "Golf",
                "details": "Quiero cambiar la actividad de Golf a martes y jueves de 6 pm a 7 pm",
            }
        },
    )

    update = apply_modifications(state)

    assert update["awaiting_user_input"] is False
    assert len(update["extracurricular"]) == 2
    assert any(item.nombre == "Golf" and "Martes" in item.detalle for item in update["extracurricular"])
    assert any(item.nombre == "Gym" for item in update["extracurricular"])
    golf_events = [event for event in update["events"] if event.titulo == "Golf"]
    gym_events = [event for event in update["events"] if event.titulo == "Gym"]
    assert {event.dia for event in golf_events} == {"Martes", "Jueves"}
    assert {event.dia for event in gym_events} == {"Martes"}


def test_apply_modifications_deletes_specific_extracurricular_and_its_events() -> None:
    state = AgentState(
        phase="validate",
        timezone="America/Bogota",
        extracurricular=[
            ExtracurricularItem(nombre="Golf", es_variable=False, detalle="Lunes 18:00-19:00"),
            ExtracurricularItem(nombre="Gym", es_variable=False, detalle="Martes 05:00-06:00"),
        ],
        events=[
            Event(
                id=new_event_id(),
                dia="Lunes",
                inicio="18:00",
                fin="19:00",
                titulo="Golf",
                tipo="confirmado",
                categoria="extracurricular",
                origen="user_text",
                timezone="America/Bogota",
            ),
            Event(
                id=new_event_id(),
                dia="Martes",
                inicio="05:00",
                fin="06:00",
                titulo="Gym",
                tipo="confirmado",
                categoria="extracurricular",
                origen="user_text",
                timezone="America/Bogota",
            ),
        ],
        replan={
            "change_request": {
                "target": "extracurricular",
                "operation": "delete",
                "activity_name": "Golf",
                "details": "Quiero eliminar la actividad de Golf",
            }
        },
    )

    update = apply_modifications(state)

    assert update["awaiting_user_input"] is False
    assert [item.nombre for item in update["extracurricular"]] == ["Gym"]
    assert all(event.titulo != "Golf" for event in update["events"])
    assert any(event.titulo == "Gym" for event in update["events"])


def test_apply_modifications_requests_delete_confirmation_for_single_match() -> None:
    state = AgentState(
        phase="validate",
        timezone="America/Bogota",
        extracurricular=[
            ExtracurricularItem(nombre="Golf", es_variable=False, detalle="Lunes 18:00-19:00"),
        ],
        events=[
            Event(
                id=new_event_id(),
                dia="Lunes",
                inicio="18:00",
                fin="19:00",
                titulo="Golf",
                tipo="confirmado",
                categoria="extracurricular",
                origen="user_text",
                timezone="America/Bogota",
            ),
        ],
        replan={
            "change_request": {
                "target": "delete",
                "operation": "delete",
                "details": "Eliminar Golf",
            }
        },
    )

    update = apply_modifications(state)

    assert update["awaiting_user_input"] is True
    assert update["replan"]["change_request"]["stage"] == "awaiting_delete_confirmation"
    assert "esta seguro" in update["replan"]["pending_prompt"].lower()


def test_apply_modifications_updates_academic_schedule() -> None:
    state = AgentState(
        phase="validate",
        timezone="America/Bogota",
        events=[
            Event(
                id=new_event_id(),
                dia="Lunes",
                inicio="08:00",
                fin="10:00",
                titulo="Algebra",
                tipo="confirmado",
                categoria="academico",
                origen="user_text",
                timezone="America/Bogota",
            )
        ],
        raw_inputs={"horario_academico_text": "Lunes 08:00-10:00 Algebra"},
        replan={
            "change_request": {
                "target": "academico",
                "details": "Martes 10:00-12:00 Fisica",
            }
        },
    )

    update = apply_modifications(state)

    assert update["awaiting_user_input"] is False
    assert update["raw_inputs"]["horario_academico_text"] == "Martes 10:00-12:00 Fisica"
    assert len(update["events"]) == 1
    assert update["events"][0].dia == "Martes"
    assert update["events"][0].titulo == "Fisica"
