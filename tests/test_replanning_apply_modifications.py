"""Cobertura especifica del flujo de replanificacion apply_modifications."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from agents.support.flows.replanning import apply_modifications
from agents.support.state import AgentState
from schemas.scheduling import Event, ExtracurricularItem


def _event(
    event_id: str,
    *,
    dia: str,
    inicio: str,
    fin: str,
    titulo: str,
    categoria: str,
) -> Event:
    return Event(
        id=event_id,
        dia=dia,
        inicio=inicio,
        fin=fin,
        titulo=titulo,
        tipo="confirmado",
        categoria=categoria,
        origen="user_text",
        timezone="America/Bogota",
    )


def _follow_up_state(previous_state: AgentState, update: dict, user_text: str) -> AgentState:
    payload = previous_state.model_dump(mode="python")
    payload.update(update)
    payload["messages"] = list(previous_state.messages) + [HumanMessage(content=user_text)]
    return AgentState(**payload)


def test_apply_modifications_name_only_update_requests_new_details() -> None:
    state = AgentState(
        phase="validate",
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="modificar algebra")],
        replan={"change_request": {"target": "academico", "operation": "update"}},
        events=[
            _event(
                "academic-1",
                dia="Lunes",
                inicio="08:00",
                fin="10:00",
                titulo="Algebra",
                categoria="academico",
            )
        ],
    )

    update = apply_modifications(state)

    assert update["awaiting_user_input"] is True
    assert update["replan"]["change_request"]["stage"] == "awaiting_update_new_details"
    assert update["replan"]["change_request"]["selected_event_id"] == "academic-1"
    assert "indica que dias y horarios deseas modificar" in update["replan"]["pending_prompt"].lower()


def test_apply_modifications_updates_single_laboral_activity_after_confirmations() -> None:
    initial_state = AgentState(
        phase="validate",
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="modificar trabajo a martes 10:00-18:00")],
        raw_inputs={"horario_laboral_text": "Martes 09:00-17:00"},
        replan={"change_request": {"target": "laboral", "operation": "update"}},
        events=[
            _event(
                "work-1",
                dia="Martes",
                inicio="09:00",
                fin="17:00",
                titulo="Trabajo",
                categoria="laboral",
            ),
            _event(
                "academic-1",
                dia="Jueves",
                inicio="08:00",
                fin="10:00",
                titulo="Fisica",
                categoria="academico",
            ),
        ],
    )

    first_update = apply_modifications(initial_state)

    assert first_update["replan"]["change_request"]["stage"] == "awaiting_update_candidate_confirmation"

    candidate_confirmation_state = _follow_up_state(initial_state, first_update, "si")
    second_update = apply_modifications(candidate_confirmation_state)

    assert second_update["replan"]["change_request"]["stage"] == "awaiting_update_apply_confirmation"
    assert "quedara asi" in second_update["replan"]["pending_prompt"].lower()

    final_confirmation_state = _follow_up_state(candidate_confirmation_state, second_update, "si")
    third_update = apply_modifications(final_confirmation_state)

    laboral_events = [event for event in third_update["events"] if event.get("categoria") == "laboral"]
    academic_events = [event for event in third_update["events"] if event.get("categoria") == "academico"]

    assert third_update["awaiting_user_input"] is False
    assert third_update["replan"]["change_request"] is None
    assert len(laboral_events) == 1
    assert laboral_events[0].dia == "Martes"
    assert laboral_events[0].inicio == "10:00"
    assert laboral_events[0].fin == "18:00"
    assert len(academic_events) == 1
    assert academic_events[0].titulo == "Fisica"
    assert third_update["raw_inputs"]["horario_laboral_text"] == "Martes 10:00-18:00"


def test_apply_modifications_requests_identifier_for_ambiguous_update() -> None:
    state = AgentState(
        phase="validate",
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="modificar calculo a viernes 10:00-12:00")],
        replan={"change_request": {"target": "academico", "operation": "update"}},
        events=[
            _event(
                "academic-1",
                dia="Lunes",
                inicio="08:00",
                fin="10:00",
                titulo="Calculo",
                categoria="academico",
            ),
            _event(
                "academic-2",
                dia="Miercoles",
                inicio="08:00",
                fin="10:00",
                titulo="Calculo",
                categoria="academico",
            ),
        ],
    )

    update = apply_modifications(state)

    assert update["awaiting_user_input"] is True
    assert update["replan"]["change_request"]["stage"] == "awaiting_update_identifier"
    assert len(update["replan"]["change_request"]["candidate_event_ids"]) == 2
    assert "encontre varias actividades" in update["replan"]["pending_prompt"].lower()


def test_apply_modifications_delete_specific_match_updates_extracurricular_days() -> None:
    gym_item = ExtracurricularItem(
        nombre="Gimnasio",
        es_variable=False,
        detalle="Martes, Jueves 18:00-19:00",
        dias=["Martes", "Jueves"],
        hora_inicio="18:00",
        hora_fin="19:00",
    )
    initial_state = AgentState(
        phase="validate",
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="eliminar gimnasio")],
        replan={"change_request": {"target": "delete", "operation": "delete"}},
        extracurricular=[gym_item],
        events=[
            _event(
                "gym-1",
                dia="Martes",
                inicio="18:00",
                fin="19:00",
                titulo="Gimnasio",
                categoria="extracurricular",
            ),
            _event(
                "gym-2",
                dia="Jueves",
                inicio="18:00",
                fin="19:00",
                titulo="Gimnasio",
                categoria="extracurricular",
            ),
            _event(
                "academic-1",
                dia="Viernes",
                inicio="07:00",
                fin="09:00",
                titulo="Quimica",
                categoria="academico",
            ),
        ],
    )

    first_update = apply_modifications(initial_state)
    assert first_update["replan"]["change_request"]["stage"] == "awaiting_delete_scope"

    scope_state = _follow_up_state(initial_state, first_update, "2")
    second_update = apply_modifications(scope_state)
    assert second_update["replan"]["change_request"]["stage"] == "awaiting_delete_identifier"

    identifier_state = _follow_up_state(scope_state, second_update, "jueves 18:00-19:00")
    third_update = apply_modifications(identifier_state)
    assert third_update["replan"]["change_request"]["stage"] == "awaiting_delete_confirmation"
    assert third_update["replan"]["change_request"]["candidate_event_ids"] == ["gym-2"]

    confirmation_state = _follow_up_state(identifier_state, third_update, "si")
    final_update = apply_modifications(confirmation_state)

    extracurricular_events = [
        event for event in final_update["events"] if event.get("categoria") == "extracurricular"
    ]

    assert final_update["awaiting_user_input"] is False
    assert final_update["replan"]["change_request"] is None
    assert len(extracurricular_events) == 1
    assert extracurricular_events[0].dia == "Martes"
    assert len(final_update["extracurricular"]) == 1
    assert final_update["extracurricular"][0].dias == ["Martes"]


def test_apply_modifications_adds_multiple_activities_from_single_message() -> None:
    state = AgentState(
        phase="validate",
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="gimnasio martes 18:00-19:00; trabajo sabado 08:00-12:00")],
        replan={"change_request": {"target": "activity", "operation": "add"}},
    )

    update = apply_modifications(state)

    extracurricular_titles = [item.nombre for item in update["extracurricular"]]
    event_categories = sorted(event.categoria for event in update["events"])

    assert update["awaiting_user_input"] is False
    assert update["replan"]["change_request"] is None
    assert extracurricular_titles == ["Gimnasio"]
    assert event_categories == ["extracurricular", "laboral"]
