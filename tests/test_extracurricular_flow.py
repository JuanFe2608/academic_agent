"""Pruebas del flujo por pasos de actividades extracurriculares."""

from __future__ import annotations

from pathlib import Path

from langchain_core.messages import HumanMessage

from agents.support.nodes.ask_extracurricular.node import ask_extracurricular
from agents.support.nodes.collect_extracurricular_details.node import collect_extracurricular_details
from agents.support.nodes.utils import parse_yes_no
from agents.support.state import AgentState


def _message_text(update: dict, idx: int = 0) -> str:
    content = update["messages"][idx].content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                return str(block.get("text", ""))
    return ""


def _message_image_url(update: dict, idx: int = 0) -> str:
    content = update["messages"][idx].content
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "image_url":
                image_url = block.get("image_url")
                if isinstance(image_url, dict):
                    return str(image_url.get("url") or "")
    return ""


def test_ask_extracurricular_yes_moves_to_type_stage() -> None:
    state = AgentState(
        phase="extras",
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="si")],
    )

    update = ask_extracurricular(state)

    assert update["extras_collect_stage"] == "awaiting_details"
    assert update["phase"] == "extras"
    assert update["awaiting_user_input"] is True


def test_ask_extracurricular_accepts_numeric_yes() -> None:
    state = AgentState(
        phase="extras",
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="1")],
    )

    update = ask_extracurricular(state)

    assert update["extras_collect_stage"] == "awaiting_details"
    assert update["awaiting_user_input"] is True


def test_collect_extracurricular_requests_free_text_details() -> None:
    state = AgentState(
        phase="extras",
        extras_collect_stage="awaiting_details",
    )

    update = collect_extracurricular_details(state)

    assert update["extras_collect_stage"] == "awaiting_details"
    prompt = update["messages"][0].content.lower()
    assert "actividades extracurriculares" in prompt
    assert "indica siempre el día y la hora de inicio y fin" in prompt
    assert "asumiré que usas horario militar" in prompt


def test_collect_extracurricular_details_adds_item_and_moves_to_more() -> None:
    state = AgentState(
        phase="extras",
        extras_collect_stage="awaiting_details",
        extras_pending_is_variable=False,
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="Natacion, martes y jueves 18:00-19:00")],
    )

    update = collect_extracurricular_details(state)

    assert update["extras_collect_stage"] == "awaiting_more"
    assert update["extras_pending_is_variable"] is None
    assert len(update["extracurricular"]) == 1
    assert update["extracurricular"][0].es_variable is False
    assert update["extracurricular"][0].hora_inicio == "18:00"
    assert update["extracurricular"][0].hora_fin == "19:00"
    assert any(block.block_type == "extracurricular" for block in update["schedule"]["blocks"])


def test_collect_extracurricular_details_splits_midnight_ranges_before_draft_preview() -> None:
    state = AgentState(
        phase="extras",
        extras_collect_stage="awaiting_details",
        extras_pending_is_variable=False,
        awaiting_user_input=True,
        user_message_count=0,
        messages=[
            HumanMessage(
                content="Voy al gimnasio los lunes martes domingos y sabados de 10 pm a 12 am"
            )
        ],
    )

    update = collect_extracurricular_details(state)

    assert update["extras_collect_stage"] == "awaiting_more"
    blocks = [block for block in update["schedule"]["blocks"] if block.block_type == "extracurricular"]
    assert [(block.title, block.day_of_week, block.start_time, block.end_time) for block in blocks] == [
        ("Gimnasio", "monday", "22:00", "23:59"),
        ("Gimnasio", "tuesday", "22:00", "23:59"),
        ("Gimnasio", "sunday", "22:00", "23:59"),
        ("Gimnasio", "saturday", "22:00", "23:59"),
    ]


def test_collect_extracurricular_awaiting_more_no_uses_preview_message() -> None:
    state = AgentState(
        phase="extras",
        extras_collect_stage="awaiting_more",
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="no")],
    )

    update = collect_extracurricular_details(state)

    assert update["phase"] == "draft"
    assert update["awaiting_user_input"] is False
    message = update["messages"][0].content.lower()
    assert "resumen" in message


def test_parse_yes_no_does_not_treat_gimnasio_as_yes() -> None:
    assert parse_yes_no("Voy a gimnasio los martes de 3 pm a 5 pm") is None


def test_collect_extracurricular_awaiting_more_accepts_new_activity_content_directly() -> None:
    first_state = AgentState(
        phase="extras",
        extras_collect_stage="awaiting_details",
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="Saco a mi perro todos los dias de 9 am a 10 am")],
    )

    first_update = collect_extracurricular_details(first_state)

    state = AgentState(
        phase="extras",
        extras_collect_stage=first_update["extras_collect_stage"],
        extracurricular=first_update["extracurricular"],
        schedule=first_update["schedule"],
        awaiting_user_input=True,
        user_message_count=first_update["user_message_count"],
        last_user_text=first_update["last_user_text"],
        messages=[HumanMessage(content="Voy a gimnasio los martes de 3 pm a 5 pm")],
    )

    update = collect_extracurricular_details(state)

    assert update["phase"] == "extras"
    assert update["extras_collect_stage"] == "awaiting_more"
    assert update["awaiting_user_input"] is True
    assert [item.nombre for item in update["extracurricular"]] == ["Sacar al perro", "Gimnasio"]
    blocks = [block for block in update["schedule"]["blocks"] if block.block_type == "extracurricular"]
    assert any(
        block.title == "Gimnasio"
        and block.day_of_week == "tuesday"
        and block.start_time == "15:00"
        and block.end_time == "17:00"
        for block in blocks
    )
    prompt = update["messages"][0].content.lower()
    assert "agregar más actividades" in prompt


def test_collect_extracurricular_awaiting_more_strips_option_text_from_inline_payload() -> None:
    state = AgentState(
        phase="extras",
        extras_collect_stage="awaiting_more",
        awaiting_user_input=True,
        user_message_count=0,
        messages=[
            HumanMessage(
                content="1\nVoy a gimnasio los martes de 3 pm a 5 pm"
            )
        ],
    )

    update = collect_extracurricular_details(state)

    assert update["phase"] == "extras"
    assert [item.nombre for item in update["extracurricular"]] == ["Gimnasio"]


def test_collect_extracurricular_opens_section_review_before_draft() -> None:
    state = AgentState(
        phase="extras",
        extras_collect_stage="awaiting_more",
        extracurricular=[
            {
                "nombre": "Gimnasio",
                "es_variable": False,
                "detalle": "Martes 19:00-20:30",
                "dias": ["Martes"],
                "hora_inicio": "19:00",
                "hora_fin": "20:30",
            }
        ],
        schedule={
            "blocks": [
                {
                    "block_type": "extracurricular",
                    "title": "Gimnasio",
                    "day_of_week": "tuesday",
                    "start_time": "19:00",
                    "end_time": "20:30",
                    "source_text": "Martes 19:00-20:30 Gimnasio",
                }
            ]
        },
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="2")],
    )

    update = collect_extracurricular_details(state)

    assert update["phase"] == "extras"
    assert update["awaiting_user_input"] is True
    assert update["schedule"]["review_stage"] == "section_awaiting_confirmation"
    prompt = _message_text(update).lower()
    assert "horario extracurricular actual" in prompt
    assert "está bien así" in prompt
    assert "escribe el número de la opción" in prompt
    assert Path(_message_image_url(update)).exists()


def test_collect_extracurricular_section_confirmation_yes_moves_to_draft() -> None:
    state = AgentState(
        phase="extras",
        extras_collect_stage="awaiting_more",
        extracurricular=[
            {
                "nombre": "Gimnasio",
                "es_variable": False,
                "detalle": "Martes 19:00-20:30",
                "dias": ["Martes"],
                "hora_inicio": "19:00",
                "hora_fin": "20:30",
            }
        ],
        schedule={
            "blocks": [
                {
                    "block_type": "extracurricular",
                    "title": "Gimnasio",
                    "day_of_week": "tuesday",
                    "start_time": "19:00",
                    "end_time": "20:30",
                    "source_text": "Martes 19:00-20:30 Gimnasio",
                }
            ],
            "review_stage": "section_awaiting_confirmation",
            "correction_target": "extracurricular",
        },
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="1")],
    )

    update = collect_extracurricular_details(state)

    assert update["phase"] == "draft"
    assert update["awaiting_user_input"] is False
    assert update["extras_collect_stage"] == "done"
    assert "resumen" in update["messages"][0].content.lower()


def test_collect_extracurricular_multi_item_time_edit_updates_items_and_preview(
    monkeypatch,
    tmp_path,
) -> None:
    rendered_path = tmp_path / "schedule.png"
    rendered_path.write_bytes(b"fake image")
    monkeypatch.setattr(
        "agents.support.flows.scheduling.section_confirmation_service.build_rendered_schedule_message_content",
        lambda text, _blocks, **_kwargs: (
            [
                {"type": "text", "text": text},
                {"type": "image_url", "image_url": {"url": str(rendered_path)}},
            ],
            str(rendered_path),
        ),
    )
    state = AgentState(
        phase="extras",
        extras_collect_stage="awaiting_more",
        extracurricular=[
            {
                "nombre": "Gimnasio",
                "es_variable": False,
                "detalle": "Martes 19:00-20:00",
                "dias": ["Martes"],
                "hora_inicio": "19:00",
                "hora_fin": "20:00",
            },
            {
                "nombre": "Gimnasio",
                "es_variable": False,
                "detalle": "Jueves 19:00-20:00",
                "dias": ["Jueves"],
                "hora_inicio": "19:00",
                "hora_fin": "20:00",
            },
        ],
        schedule={
            "blocks": [
                {
                    "block_type": "extracurricular",
                    "title": "Gimnasio",
                    "day_of_week": "tuesday",
                    "start_time": "19:00",
                    "end_time": "20:00",
                    "source_text": "Martes 19:00-20:00 Gimnasio",
                    "block_id": "extra-1",
                },
                {
                    "block_type": "extracurricular",
                    "title": "Gimnasio",
                    "day_of_week": "thursday",
                    "start_time": "19:00",
                    "end_time": "20:00",
                    "source_text": "Jueves 19:00-20:00 Gimnasio",
                    "block_id": "extra-2",
                },
            ],
            "review_stage": "section_awaiting_field_value",
            "correction_target": "extracurricular",
            "editing_block_id": "extra-1",
            "editing_block_ids": ["extra-1", "extra-2"],
            "editing_field": "time_range",
        },
        awaiting_user_input=True,
        user_message_count=0,
        messages=[HumanMessage(content="8 pm a 9 pm")],
    )

    update = collect_extracurricular_details(state)

    updated_blocks = {block.block_id: block for block in update["schedule"]["blocks"]}
    assert updated_blocks["extra-1"].start_time == "20:00"
    assert updated_blocks["extra-2"].start_time == "20:00"
    assert updated_blocks["extra-1"].end_time == "21:00"
    assert updated_blocks["extra-2"].end_time == "21:00"
    assert len(update["extracurricular"]) == 1
    assert update["extracurricular"][0].dias == ["Martes", "Jueves"]
    assert update["extracurricular"][0].hora_inicio == "20:00"
    assert update["extracurricular"][0].hora_fin == "21:00"
    text = update["messages"][0].content[0]["text"].lower()
    assert "así quedaron actualizados estos registros" in text
    assert rendered_path.exists()


def test_collect_extracurricular_details_keeps_valid_items_and_requests_only_missing_data() -> None:
    state = AgentState(
        phase="extras",
        extras_collect_stage="awaiting_details",
        extras_pending_is_variable=False,
        awaiting_user_input=True,
        user_message_count=0,
        messages=[
            HumanMessage(
                content=(
                    "voy los dias sabados al gimnasio de 10 am a 12 pm, "
                    "luego voy al centro comercial de 2 pm a 4 pm y los domingos voy a la iglesia"
                )
            )
        ],
    )

    update = collect_extracurricular_details(state)

    assert update["phase"] == "extras"
    assert update["extras_collect_stage"] == "awaiting_details"
    assert update["awaiting_user_input"] is True
    assert len(update["extracurricular"]) == 2
    assert [item.nombre for item in update["extracurricular"]] == ["Gimnasio", "Centro Comercial"]
    blocks = [block for block in update["schedule"]["blocks"] if block.block_type == "extracurricular"]
    assert [(block.title, block.day_of_week, block.start_time, block.end_time) for block in blocks] == [
        ("Gimnasio", "saturday", "10:00", "12:00"),
        ("Centro Comercial", "saturday", "14:00", "16:00"),
    ]
    prompt = update["messages"][0].content.lower()
    assert "ya registré" in prompt
    assert "iglesia" in prompt
    assert "hora de inicio y fin" in prompt
    assert "responder solo con el rango horario" in prompt
    assert update["interaction"]["pending_entity_type"] == "extracurricular_item"
    assert update["interaction"]["pending_action"] == "complete_extracurricular_item"
    assert update["interaction"]["pending_entity_payload"]["name"] == "Iglesia"
    assert update["interaction"]["missing_fields_json"] == ["time_range"]


def test_collect_extracurricular_details_remembers_pending_day_when_user_replies_with_only_time() -> None:
    initial_state = AgentState(
        phase="extras",
        extras_collect_stage="awaiting_details",
        extras_pending_is_variable=False,
        awaiting_user_input=True,
        user_message_count=0,
        messages=[
            HumanMessage(
                content=(
                    "voy los dias sabados al gimnasio de 10 am a 12 pm, "
                    "luego voy al centro comercial de 2 pm a 4 pm y los domingos voy a la iglesia"
                )
            )
        ],
    )

    first_update = collect_extracurricular_details(initial_state)

    follow_up_state = AgentState(
        phase="extras",
        extras_collect_stage=first_update["extras_collect_stage"],
        extras_pending_is_variable=first_update["extras_pending_is_variable"],
        extras_pending_items=first_update["extras_pending_items"],
        extracurricular=first_update["extracurricular"],
        schedule=first_update["schedule"],
        awaiting_user_input=True,
        user_message_count=first_update["user_message_count"],
        last_user_text=first_update["last_user_text"],
        messages=[HumanMessage(content="el horario de la iglesia es de 7 am a 8 am")],
    )

    second_update = collect_extracurricular_details(follow_up_state)

    assert second_update["phase"] == "extras"
    assert second_update["extras_collect_stage"] == "awaiting_more"
    assert second_update["awaiting_user_input"] is True
    assert second_update["extras_pending_items"] == []
    assert second_update["interaction"]["pending_entity_type"] is None
    assert second_update["interaction"]["missing_fields_json"] == []
    assert [item.nombre for item in second_update["extracurricular"]] == [
        "Gimnasio",
        "Centro Comercial",
        "Iglesia",
    ]
    blocks = [block for block in second_update["schedule"]["blocks"] if block.block_type == "extracurricular"]
    assert [(block.title, block.day_of_week, block.start_time, block.end_time) for block in blocks] == [
        ("Gimnasio", "saturday", "10:00", "12:00"),
        ("Centro Comercial", "saturday", "14:00", "16:00"),
        ("Iglesia", "sunday", "07:00", "08:00"),
    ]
