"""Pruebas para modificaciones del horario desde lenguaje natural."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from agents.support.nodes.apply_modifications.node import apply_modifications
from agents.support.nodes.validate_schedule.node import validate_schedule
from agents.support.state import AgentState, Event, ExtracurricularItem, StudentProfile, new_event_id


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


def test_validate_schedule_main_menu_no_longer_mentions_direct_free_text_changes() -> None:
    state = AgentState(
        phase="validate",
        awaiting_user_input=True,
        user_message_count=0,
    )

    update = validate_schedule(state)

    assert "tambien puedes escribir directamente el cambio en lenguaje natural" not in (
        update["messages"][0].content.lower()
    )


def test_validate_schedule_update_menu_hides_laboral_for_solo_estudio() -> None:
    state = AgentState(
        phase="validate",
        awaiting_user_input=True,
        user_message_count=0,
        student_profile=StudentProfile(occupation="solo_estudio"),
        messages=[HumanMessage(content="1")],
    )

    update = validate_schedule(state)

    prompt = update["messages"][0].content.lower()
    assert "horario academico" in prompt
    assert "actividad extracurricular" in prompt
    assert "horario laboral" not in prompt


def test_validate_schedule_update_menu_hides_academico_for_solo_trabajo() -> None:
    state = AgentState(
        phase="validate",
        awaiting_user_input=True,
        user_message_count=0,
        student_profile=StudentProfile(occupation="solo_trabajo"),
        messages=[HumanMessage(content="1")],
    )

    update = validate_schedule(state)

    prompt = update["messages"][0].content.lower()
    assert "horario laboral" in prompt
    assert "actividad extracurricular" in prompt
    assert "horario academico" not in prompt


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


def test_validate_schedule_target_menu_uses_dynamic_numbering_for_solo_estudio() -> None:
    state = AgentState(
        phase="validate",
        awaiting_user_input=True,
        user_message_count=0,
        student_profile=StudentProfile(occupation="solo_estudio"),
        messages=[HumanMessage(content="2")],
        replan={"change_request": {"operation": "update", "stage": "awaiting_target"}},
    )

    update = validate_schedule(state)

    assert update["awaiting_user_input"] is True
    assert update["replan"]["change_request"]["target"] == "extracurricular"
    assert update["replan"]["change_request"]["stage"] == "awaiting_details"


def test_validate_schedule_update_academic_prompt_uses_new_text() -> None:
    state = AgentState(
        phase="validate",
        awaiting_user_input=True,
        user_message_count=0,
        student_profile=StudentProfile(occupation="solo_estudio"),
        messages=[HumanMessage(content="1")],
        replan={"change_request": {"operation": "update", "stage": "awaiting_target"}},
    )

    update = validate_schedule(state)

    assert update["awaiting_user_input"] is True
    assert update["replan"]["change_request"]["target"] == "academico"
    assert update["messages"][0].content == "Que actividad academica deseas modificar?"


def test_validate_schedule_option_three_requests_activity_name() -> None:
    state = AgentState(
        phase="validate",
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="3")],
    )

    update = validate_schedule(state)

    assert update["awaiting_user_input"] is True
    assert update["replan"]["change_request"]["operation"] == "delete"
    assert "cual es la actividad que deseas eliminar" in update["messages"][0].content.lower()


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
    assert "que actividad extracurricular deseas modificar" in update["replan"]["pending_prompt"].lower()
    assert "que actividad extracurricular deseas modificar" in update["messages"][0].content.lower()


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
    assert update["replan"]["change_request"]["target"] == "delete"
    assert update["replan"]["change_request"]["activity_name"] == "Golf"
    assert update["replan"]["change_request"]["operation"] == "delete"


def test_validate_schedule_detects_direct_activity_addition_request() -> None:
    state = AgentState(
        phase="validate",
        awaiting_user_input=True,
        user_message_count=0,
        messages=[
            HumanMessage(
                content="Hago patinaje de lunes a domingo de 9 am a 10 am y estudio para parciales los viernes de 11 am a 12 pm"
            )
        ],
    )

    update = validate_schedule(state)

    assert update["awaiting_user_input"] is False
    assert update["replan"]["change_request"]["target"] == "activity"
    assert update["replan"]["change_request"]["operation"] == "add"


def test_validate_schedule_detects_title_only_academic_activity_from_existing_schedule() -> None:
    state = AgentState(
        phase="validate",
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="Data Science Fundamentals")],
        events=[
            Event(
                id=new_event_id(),
                dia="Lunes",
                inicio="09:00",
                fin="10:00",
                titulo="Data Science Fundamentals",
                tipo="confirmado",
                categoria="academico",
                origen="user_text",
                timezone="America/Bogota",
            )
        ],
    )

    update = validate_schedule(state)

    assert update["awaiting_user_input"] is False
    assert update["replan"]["change_request"]["target"] == "academico"
    assert update["replan"]["change_request"]["activity_name"] == "Data Science Fundamentals"
    assert update["replan"]["change_request"]["operation"] == "update"


def test_validate_schedule_detects_partial_academic_title_from_existing_schedule() -> None:
    state = AgentState(
        phase="validate",
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="DATA SCIENCE")],
        events=[
            Event(
                id=new_event_id(),
                dia="Lunes",
                inicio="09:00",
                fin="10:00",
                titulo="Data Science Fundamentals",
                tipo="confirmado",
                categoria="academico",
                origen="user_text",
                timezone="America/Bogota",
            )
        ],
    )

    update = validate_schedule(state)

    assert update["awaiting_user_input"] is False
    assert update["replan"]["change_request"]["target"] == "academico"
    assert update["replan"]["change_request"]["activity_name"] == "Data Science Fundamentals"


def test_validate_schedule_uses_llm_fallback_for_similar_activity_title(monkeypatch) -> None:
    monkeypatch.setattr(
        "agents.support.tools.activity_matching.llm_extract_json",
        lambda _prompt: {"title": "Data Science Fundamentals"},
    )

    state = AgentState(
        phase="validate",
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="ciencia de datos fundamentals")],
        events=[
            Event(
                id=new_event_id(),
                dia="Lunes",
                inicio="09:00",
                fin="10:00",
                titulo="Data Science Fundamentals",
                tipo="confirmado",
                categoria="academico",
                origen="user_text",
                timezone="America/Bogota",
            )
        ],
    )

    update = validate_schedule(state)

    assert update["awaiting_user_input"] is False
    assert update["replan"]["change_request"]["target"] == "academico"
    assert update["replan"]["change_request"]["activity_name"] == "Data Science Fundamentals"


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
    assert "no encontre ninguna actividad con ese nombre en tu horario" in (
        update["replan"]["pending_prompt"].lower()
    )
    assert "gym" in update["replan"]["pending_prompt"].lower()
    assert "lunes" in update["replan"]["pending_prompt"].lower()


def test_apply_modifications_title_only_single_match_requests_new_day_and_time() -> None:
    state = AgentState(
        phase="validate",
        timezone="America/Bogota",
        events=[
            Event(
                id=new_event_id(),
                dia="Lunes",
                inicio="09:00",
                fin="10:00",
                titulo="Data Science Fundamentals",
                tipo="confirmado",
                categoria="academico",
                origen="user_text",
                timezone="America/Bogota",
            )
        ],
        replan={
            "change_request": {
                "target": "academico",
                "operation": "update",
                "activity_name": "Data Science Fundamentals",
                "details": "Data Science Fundamentals",
            }
        },
    )

    update = apply_modifications(state)

    assert update["awaiting_user_input"] is True
    assert update["replan"]["change_request"]["stage"] == "awaiting_update_new_details"
    assert "encontre la actividad 'data science fundamentals'" in update["replan"]["pending_prompt"].lower()
    assert "indica que dias y horarios deseas modificar" in update["replan"]["pending_prompt"].lower()


def test_apply_modifications_partial_title_matches_similar_existing_activity() -> None:
    state = AgentState(
        phase="validate",
        timezone="America/Bogota",
        events=[
            Event(
                id=new_event_id(),
                dia="Lunes",
                inicio="09:00",
                fin="10:00",
                titulo="Data Science Fundamentals",
                tipo="confirmado",
                categoria="academico",
                origen="user_text",
                timezone="America/Bogota",
            )
        ],
        replan={
            "change_request": {
                "target": "activity_lookup",
                "operation": "update",
                "activity_name": "DATA SCIENCE",
                "details": "DATA SCIENCE",
            }
        },
    )

    update = apply_modifications(state)

    assert update["awaiting_user_input"] is True
    assert update["replan"]["change_request"]["stage"] == "awaiting_update_candidate_confirmation"
    prompt = update["replan"]["pending_prompt"].lower()
    assert "data science fundamentals" in prompt
    assert "09:00-10:00" in prompt


def test_apply_modifications_title_only_unknown_activity_reports_not_found() -> None:
    state = AgentState(
        phase="validate",
        timezone="America/Bogota",
        events=[
            Event(
                id=new_event_id(),
                dia="Lunes",
                inicio="09:00",
                fin="10:00",
                titulo="Data Science Fundamentals",
                tipo="confirmado",
                categoria="academico",
                origen="user_text",
                timezone="America/Bogota",
            )
        ],
        replan={
            "change_request": {
                "target": "activity_lookup",
                "operation": "update",
                "activity_name": "Biologia",
                "details": "Biologia",
            }
        },
    )

    update = apply_modifications(state)

    assert update["awaiting_user_input"] is True
    prompt = update["replan"]["pending_prompt"].lower()
    assert "no encontre ninguna actividad con ese nombre en tu horario" in prompt
    assert "por favor verifica el nombre de la actividad" in prompt
    assert "data science fundamentals" in prompt


def test_apply_modifications_partial_reference_confirms_specific_existing_activity() -> None:
    state = AgentState(
        phase="validate",
        timezone="America/Bogota",
        events=[
            Event(
                id=new_event_id(),
                dia="Lunes",
                inicio="09:00",
                fin="10:00",
                titulo="Data Science Fundamentals",
                tipo="confirmado",
                categoria="academico",
                origen="user_text",
                timezone="America/Bogota",
            ),
            Event(
                id=new_event_id(),
                dia="Martes",
                inicio="11:00",
                fin="12:00",
                titulo="Data Science Fundamentals",
                tipo="confirmado",
                categoria="academico",
                origen="user_text",
                timezone="America/Bogota",
            ),
        ],
        replan={
            "change_request": {
                "target": "academico",
                "operation": "update",
                "activity_name": "Data Science Fundamentals",
                "details": "Cambiar Data Science Fundamentals los lunes de 9 am a 10 am",
            }
        },
    )

    update = apply_modifications(state)

    assert update["awaiting_user_input"] is True
    assert update["replan"]["change_request"]["stage"] == "awaiting_update_candidate_confirmation"
    prompt = update["replan"]["pending_prompt"].lower()
    assert "data science fundamentals" in prompt
    assert "lunes" in prompt
    assert "09:00-10:00" in prompt


def test_apply_modifications_explicit_all_request_does_not_force_single_selection() -> None:
    state = AgentState(
        phase="validate",
        timezone="America/Bogota",
        events=[
            Event(
                id=new_event_id(),
                dia="Lunes",
                inicio="09:00",
                fin="10:00",
                titulo="Data Science Fundamentals",
                tipo="confirmado",
                categoria="academico",
                origen="user_text",
                timezone="America/Bogota",
            ),
            Event(
                id=new_event_id(),
                dia="Martes",
                inicio="11:00",
                fin="12:00",
                titulo="Data Science Fundamentals",
                tipo="confirmado",
                categoria="academico",
                origen="user_text",
                timezone="America/Bogota",
            ),
        ],
        replan={
            "change_request": {
                "target": "academico",
                "operation": "update",
                "activity_name": "Data Science Fundamentals",
                "details": "Cambiar todas las actividades de Data Science Fundamentals",
                "apply_to_all": True,
            }
        },
    )

    update = apply_modifications(state)

    assert update["awaiting_user_input"] is True
    assert update["replan"]["change_request"]["stage"] == "awaiting_update_all_details"
    assert "indica los nuevos dias y horarios que deseas aplicar a todas" in (
        update["replan"]["pending_prompt"].lower()
    )


def test_apply_modifications_lists_available_activities_when_update_reference_is_unknown() -> None:
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
            ),
            Event(
                id=new_event_id(),
                dia="Martes",
                inicio="14:00",
                fin="16:00",
                titulo="Fisica",
                tipo="confirmado",
                categoria="academico",
                origen="user_text",
                timezone="America/Bogota",
            ),
        ],
        replan={
            "change_request": {
                "target": "academico",
                "operation": "update",
                "details": "Biologia",
            }
        },
    )

    update = apply_modifications(state)

    assert update["awaiting_user_input"] is True
    prompt = update["replan"]["pending_prompt"].lower()
    assert "no encontre ninguna actividad con ese nombre en tu horario" in prompt
    assert "algebra" in prompt
    assert "lunes" in prompt
    assert "fisica" in prompt


def test_apply_modifications_update_single_match_requests_candidate_confirmation() -> None:
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

    assert update["awaiting_user_input"] is True
    assert update["replan"]["change_request"]["stage"] == "awaiting_update_candidate_confirmation"
    assert "golf" in update["replan"]["pending_prompt"].lower()
    assert "lunes" in update["replan"]["pending_prompt"].lower()


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


def test_apply_modifications_update_same_name_requests_day_or_time() -> None:
    state = AgentState(
        phase="validate",
        timezone="America/Bogota",
        events=[
            Event(
                id=new_event_id(),
                dia="Lunes",
                inicio="08:00",
                fin="10:00",
                titulo="Matematicas",
                tipo="confirmado",
                categoria="academico",
                origen="user_text",
                timezone="America/Bogota",
            ),
            Event(
                id=new_event_id(),
                dia="Miercoles",
                inicio="14:00",
                fin="16:00",
                titulo="Matematicas",
                tipo="confirmado",
                categoria="academico",
                origen="user_text",
                timezone="America/Bogota",
            ),
        ],
        replan={
            "change_request": {
                "target": "academico",
                "operation": "update",
                "details": "Matematicas",
            }
        },
    )

    update = apply_modifications(state)

    assert update["awaiting_user_input"] is True
    assert update["replan"]["change_request"]["stage"] == "awaiting_update_identifier"
    assert "varias actividades con el nombre matematicas" in update["replan"]["pending_prompt"].lower()
    assert "1. matematicas - lunes 08:00-10:00" in update["replan"]["pending_prompt"].lower()


def test_apply_modifications_update_data_science_name_only_requests_more_detail() -> None:
    state = AgentState(
        phase="validate",
        timezone="America/Bogota",
        events=[
            Event(
                id=new_event_id(),
                dia="Lunes",
                inicio="08:00",
                fin="10:00",
                titulo="Data Science",
                tipo="confirmado",
                categoria="academico",
                origen="user_text",
                timezone="America/Bogota",
            ),
            Event(
                id=new_event_id(),
                dia="Martes",
                inicio="11:00",
                fin="13:00",
                titulo="Data Science",
                tipo="confirmado",
                categoria="academico",
                origen="user_text",
                timezone="America/Bogota",
            ),
            Event(
                id=new_event_id(),
                dia="Miercoles",
                inicio="15:00",
                fin="17:00",
                titulo="Data Science",
                tipo="confirmado",
                categoria="academico",
                origen="user_text",
                timezone="America/Bogota",
            ),
        ],
        replan={
            "change_request": {
                "target": "academico",
                "operation": "update",
                "details": "Data science",
            }
        },
    )

    update = apply_modifications(state)

    assert update["awaiting_user_input"] is True
    assert update["replan"]["change_request"]["stage"] == "awaiting_update_identifier"
    assert "data science" in update["replan"]["pending_prompt"].lower()
    assert "lunes 08:00-10:00" in update["replan"]["pending_prompt"].lower()
    assert "martes 11:00-13:00" in update["replan"]["pending_prompt"].lower()
    assert "miercoles 15:00-17:00" in update["replan"]["pending_prompt"].lower()


def test_apply_modifications_update_same_name_with_time_hint_only_confirms_candidate() -> None:
    state = AgentState(
        phase="validate",
        timezone="America/Bogota",
        events=[
            Event(
                id=new_event_id(),
                dia="Lunes",
                inicio="08:00",
                fin="10:00",
                titulo="Data Science",
                tipo="confirmado",
                categoria="academico",
                origen="user_text",
                timezone="America/Bogota",
            ),
            Event(
                id=new_event_id(),
                dia="Martes",
                inicio="11:00",
                fin="15:00",
                titulo="Data Science",
                tipo="confirmado",
                categoria="academico",
                origen="user_text",
                timezone="America/Bogota",
            ),
            Event(
                id=new_event_id(),
                dia="Miercoles",
                inicio="17:00",
                fin="19:00",
                titulo="Data Science",
                tipo="confirmado",
                categoria="academico",
                origen="user_text",
                timezone="America/Bogota",
            ),
        ],
        replan={
            "change_request": {
                "target": "academico",
                "operation": "update",
                "details": "Data Science de 11 am a 3 pm",
            }
        },
    )

    update = apply_modifications(state)

    assert update["awaiting_user_input"] is True
    assert update["replan"]["change_request"]["stage"] == "awaiting_update_candidate_confirmation"
    assert "data science" in update["replan"]["pending_prompt"].lower()
    assert "martes" in update["replan"]["pending_prompt"].lower()
    assert "11:00-15:00" in update["replan"]["pending_prompt"].lower()


def test_apply_modifications_update_restarts_when_candidate_is_not_correct() -> None:
    selected = Event(
        id=new_event_id(),
        dia="Lunes",
        inicio="18:00",
        fin="19:00",
        titulo="Golf",
        tipo="confirmado",
        categoria="extracurricular",
        origen="user_text",
        timezone="America/Bogota",
    )
    state = AgentState(
        phase="validate",
        timezone="America/Bogota",
        events=[selected],
        replan={
            "change_request": {
                "target": "extracurricular",
                "operation": "update",
                "stage": "awaiting_update_candidate_confirmation",
                "selected_event_id": selected.id,
            }
        },
        messages=[HumanMessage(content="No")],
        awaiting_user_input=True,
        user_message_count=0,
    )

    update = apply_modifications(state)

    assert update["awaiting_user_input"] is True
    assert update["replan"]["change_request"]["stage"] == "awaiting_update_reference"
    assert "vuelve a escribirla indicando nombre, dia o horario" in (
        update["replan"]["pending_prompt"].lower()
    )
    assert "golf" in update["replan"]["pending_prompt"].lower()


def test_apply_modifications_updates_specific_extracurricular_and_preserves_others() -> None:
    base_state = AgentState(
        phase="validate",
        timezone="America/Bogota",
        extracurricular=[
            ExtracurricularItem(nombre="Golf", es_variable=False, detalle="Lunes 18:00-19:00", dias=["Lunes"], hora_inicio="18:00", hora_fin="19:00"),
            ExtracurricularItem(nombre="Gym", es_variable=False, detalle="Martes 05:00-06:00", dias=["Martes"], hora_inicio="05:00", hora_fin="06:00"),
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

    first = apply_modifications(base_state)
    assert first["awaiting_user_input"] is True
    assert first["replan"]["change_request"]["stage"] == "awaiting_update_candidate_confirmation"

    second = apply_modifications(
        base_state.model_copy(
            update={
                "messages": [HumanMessage(content="Si")],
                "awaiting_user_input": True,
                "user_message_count": 0,
                "replan": first["replan"],
            }
        )
    )
    assert second["awaiting_user_input"] is True
    assert second["replan"]["change_request"]["stage"] == "awaiting_update_apply_confirmation"

    final = apply_modifications(
        base_state.model_copy(
            update={
                "messages": [HumanMessage(content="Si")],
                "awaiting_user_input": True,
                "user_message_count": 0,
                "replan": second["replan"],
            }
        )
    )

    assert final["awaiting_user_input"] is False
    assert len(final["extracurricular"]) == 2
    assert any(item.nombre == "Golf" and "Martes" in item.detalle for item in final["extracurricular"])
    assert any(item.nombre == "Gym" for item in final["extracurricular"])
    golf_events = [event for event in final["events"] if event.titulo == "Golf"]
    gym_events = [event for event in final["events"] if event.titulo == "Gym"]
    assert {event.dia for event in golf_events} == {"Martes", "Jueves"}
    assert {event.dia for event in gym_events} == {"Martes"}


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
    assert "estas seguro" in update["replan"]["pending_prompt"].lower()


def test_apply_modifications_adds_multiple_activities_without_touching_existing_events() -> None:
    state = AgentState(
        phase="validate",
        timezone="America/Bogota",
        extracurricular=[
            ExtracurricularItem(nombre="Gym", es_variable=False, detalle="Martes 05:00-06:00", dias=["Martes"], hora_inicio="05:00", hora_fin="06:00"),
        ],
        events=[
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
                "target": "activity",
                "operation": "add",
                "details": "Hago patinaje de lunes a domingo de 9 am a 10 am y estudio para parciales los viernes de 11 am a 12 pm",
            }
        },
    )

    update = apply_modifications(state)

    assert update["awaiting_user_input"] is False
    assert any(item.nombre == "Gym" for item in update["extracurricular"])
    assert any(item.nombre == "Patinaje" for item in update["extracurricular"])
    gym_events = [event for event in update["events"] if event.titulo == "Gym"]
    skating_events = [event for event in update["events"] if event.titulo == "Patinaje"]
    study_events = [
        event
        for event in update["events"]
        if event.categoria == "academico" and event.inicio == "11:00" and event.fin == "12:00"
    ]
    assert len(gym_events) == 1
    assert {event.dia for event in skating_events} == {
        "Lunes",
        "Martes",
        "Miercoles",
        "Jueves",
        "Viernes",
        "Sabado",
        "Domingo",
    }
    assert {event.dia for event in study_events} == {"Viernes"}


def test_apply_modifications_adds_extracurricular_activities_with_same_tolerance_as_extras_flow() -> None:
    state = AgentState(
        phase="validate",
        timezone="America/Bogota",
        replan={
            "change_request": {
                "target": "activity",
                "operation": "add",
                "details": "Hago ejercicio todos los dias de 5 am a 6 am y saco a mi perro los lunes de 11 am a 13 pm,voy a bailar los domingos de 1 pm a 3pm",
            }
        },
    )

    update = apply_modifications(state)

    assert update["awaiting_user_input"] is False
    extracurricular = update["extracurricular"]
    assert [item.nombre for item in extracurricular] == ["Ejercicio", "Sacar al perro", "Bailar"]
    assert extracurricular[1].dias == ["Lunes"]
    assert extracurricular[1].hora_inicio == "11:00"
    assert extracurricular[1].hora_fin == "13:00"
    assert extracurricular[2].dias == ["Domingo"]
    assert extracurricular[2].hora_inicio == "13:00"
    assert extracurricular[2].hora_fin == "15:00"


def test_apply_modifications_requests_days_when_adding_activity_without_them() -> None:
    state = AgentState(
        phase="validate",
        timezone="America/Bogota",
        replan={
            "change_request": {
                "target": "activity",
                "operation": "add",
                "details": "Patinaje de 9 am a 10 am",
            }
        },
    )

    update = apply_modifications(state)

    assert update["awaiting_user_input"] is True
    assert "dias exactos" in update["replan"]["pending_prompt"].lower()


def test_apply_modifications_delete_flow_asks_scope_for_same_name() -> None:
    state = AgentState(
        phase="validate",
        timezone="America/Bogota",
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
                dia="Jueves",
                inicio="20:00",
                fin="21:00",
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
    assert update["replan"]["change_request"]["stage"] == "awaiting_delete_scope"
    assert "eliminar todas" in update["replan"]["pending_prompt"].lower()


def test_apply_modifications_delete_specific_match_requires_confirmation_before_delete() -> None:
    golf_monday = Event(
        id=new_event_id(),
        dia="Lunes",
        inicio="18:00",
        fin="19:00",
        titulo="Golf",
        tipo="confirmado",
        categoria="extracurricular",
        origen="user_text",
        timezone="America/Bogota",
    )
    golf_thursday = Event(
        id=new_event_id(),
        dia="Jueves",
        inicio="20:00",
        fin="21:00",
        titulo="Golf",
        tipo="confirmado",
        categoria="extracurricular",
        origen="user_text",
        timezone="America/Bogota",
    )
    state = AgentState(
        phase="validate",
        timezone="America/Bogota",
        extracurricular=[
            ExtracurricularItem(nombre="Golf", es_variable=False, detalle="Lunes, Jueves 18:00-19:00", dias=["Lunes", "Jueves"], hora_inicio="18:00", hora_fin="19:00"),
        ],
        events=[golf_monday, golf_thursday],
        replan={
            "change_request": {
                "target": "delete",
                "operation": "delete",
                "stage": "awaiting_delete_scope",
                "activity_name": "Golf",
                "candidate_event_ids": [golf_monday.id, golf_thursday.id],
            }
        },
    )

    update = apply_modifications(
        state.model_copy(
            update={
                "messages": [HumanMessage(content="2")],
                "awaiting_user_input": True,
                "user_message_count": 0,
            }
        )
    )

    assert update["awaiting_user_input"] is True
    assert update["replan"]["change_request"]["stage"] == "awaiting_delete_identifier"

    state_confirm = state.model_copy(
        update={
            "messages": [HumanMessage(content="jueves 20:00-21:00")],
            "awaiting_user_input": True,
            "user_message_count": 0,
            "replan": update["replan"],
        }
    )
    confirm_update = apply_modifications(state_confirm)

    assert confirm_update["awaiting_user_input"] is True
    assert confirm_update["replan"]["change_request"]["stage"] == "awaiting_delete_confirmation"
    assert "jueves 20:00-21:00" in confirm_update["replan"]["pending_prompt"].lower()


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
                "operation": "update",
                "details": "Algebra",
            }
        },
    )

    first = apply_modifications(state)
    assert first["awaiting_user_input"] is True
    assert first["replan"]["change_request"]["stage"] == "awaiting_update_new_details"
    assert "indica que dias y horarios deseas modificar" in first["replan"]["pending_prompt"].lower()

    second = apply_modifications(
        state.model_copy(
            update={
                "messages": [HumanMessage(content="Martes 10:00-12:00 Fisica")],
                "awaiting_user_input": True,
                "user_message_count": 0,
                "replan": first["replan"],
            }
        )
    )
    assert second["awaiting_user_input"] is True
    assert second["replan"]["change_request"]["stage"] == "awaiting_update_apply_confirmation"

    third = apply_modifications(
        state.model_copy(
            update={
                "messages": [HumanMessage(content="Si")],
                "awaiting_user_input": True,
                "user_message_count": 0,
                "replan": second["replan"],
            }
        )
    )
    assert third["awaiting_user_input"] is False
    assert "Martes 10:00-12:00 Fisica" in third["raw_inputs"]["horario_academico_text"]
    assert len(third["events"]) == 1
    assert third["events"][0].dia == "Martes"
    assert third["events"][0].titulo == "Fisica"
