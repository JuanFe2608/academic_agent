"""Pruebas de gestion conversacional del horario fijo."""

from __future__ import annotations

from types import SimpleNamespace

from langchain_core.messages import HumanMessage

from agents.support.dependencies import (
    set_outlook_fixed_schedule_sync_service,
    set_schedule_service,
)
from agents.support.flows.scheduling.fixed_schedule_management_service import (
    handle_fixed_schedule_management_turn,
)
from agents.support.state import AgentState
from repositories.scheduling.repository import InMemoryScheduleRepository
from services.scheduling import ScheduleService, WeeklyScheduleBlock
from services.scheduling.fixed_schedule_management import parse_fixed_schedule_operation


def _block(
    block_id: str,
    *,
    block_type: str,
    title: str,
    day_of_week: str,
    start_time: str,
    end_time: str,
) -> WeeklyScheduleBlock:
    return WeeklyScheduleBlock(
        block_id=block_id,
        block_type=block_type,
        title=title,
        day_of_week=day_of_week,
        start_time=start_time,
        end_time=end_time,
        source_text=f"{day_of_week} {start_time}-{end_time} {title}",
        user_confirmed=True,
    )


def _state_with_message(text: str, *, blocks: list[WeeklyScheduleBlock]) -> AgentState:
    return AgentState(
        phase="end",
        awaiting_user_input=False,
        user_message_count=0,
        messages=[HumanMessage(content=text)],
        student_profile={
            "persisted_student_id": 15,
            "occupation": "ambos",
        },
        schedule={
            "blocks": blocks,
            "persisted_profile_id": 9,
            "schedule_end_date": "2026-06-30",
        },
        calendar={"calendar_id": "calendar-1"},
    )


def _follow_up_state(previous_state: AgentState, update: dict, user_text: str) -> AgentState:
    payload = previous_state.model_dump(mode="python")
    payload.update(update)
    payload["messages"] = list(previous_state.messages) + [HumanMessage(content=user_text)]
    return AgentState(**payload)


def _assistant_text(update: dict) -> str:
    content = update["messages"][0].content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            str(block.get("text") or "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return str(content)


class _FixedScheduleSyncServiceStub:
    def __init__(self, *, synced: bool = True) -> None:
        self.synced = synced
        self.calls: list[dict[str, object]] = []

    def sync_schedule_profile(
        self,
        *,
        student_id: int | None,
        schedule_profile_id: int | None,
        calendar_state: dict | None = None,
        calendar_id: str | None = None,
    ):
        self.calls.append(
            {
                "student_id": student_id,
                "schedule_profile_id": schedule_profile_id,
                "calendar_id": calendar_id,
            }
        )
        if self.synced:
            return SimpleNamespace(
                synced=True,
                synced_event_map={"calc-1": "outlook:calc-1"},
            )
        return SimpleNamespace(
            synced=False,
            synced_event_map={},
            error_code="microsoft_connection_not_found",
            detail="sin conexion",
        )


def test_parse_fixed_schedule_operation_detects_phase_8_intents() -> None:
    view = parse_fixed_schedule_operation("mostrar mi horario")
    update = parse_fixed_schedule_operation("cambiar mi clase de Calculo a viernes 10:00-12:00")
    delete = parse_fixed_schedule_operation("eliminar trabajo del lunes")

    assert view.intent == "view_fixed_schedule"
    assert update.intent == "update_fixed_schedule"
    assert update.target == "academic"
    assert update.reference_text == "Calculo"
    assert update.update_text == "viernes 10:00-12:00"
    assert delete.intent == "delete_fixed_schedule_item"
    assert delete.target == "work"


def test_fixed_schedule_management_view_summarizes_current_blocks() -> None:
    state = _state_with_message(
        "ver mi horario fijo",
        blocks=[
            _block(
                "calc-1",
                block_type="academic",
                title="Calculo",
                day_of_week="monday",
                start_time="08:00",
                end_time="10:00",
            )
        ],
    )

    update = handle_fixed_schedule_management_turn(state)

    assert update["phase"] == "end"
    assert update["awaiting_user_input"] is False
    assert "Calculo" in _assistant_text(update)
    assert update["interaction"]["active_intent"] == "view_fixed_schedule"
    assert update["interaction"]["confirmation_pending"] is False


def test_fixed_schedule_management_updates_block_after_confirmation() -> None:
    service = ScheduleService(repository=InMemoryScheduleRepository())
    sync_service = _FixedScheduleSyncServiceStub()
    set_schedule_service(service)
    set_outlook_fixed_schedule_sync_service(sync_service)
    try:
        state = _state_with_message(
            "cambiar mi clase de Calculo a viernes 10:00-12:00",
            blocks=[
                _block(
                    "calc-1",
                    block_type="academic",
                    title="Calculo",
                    day_of_week="monday",
                    start_time="08:00",
                    end_time="10:00",
                )
            ],
        )

        first_update = handle_fixed_schedule_management_turn(state)

        assert first_update["phase"] == "fixed_schedule_management"
        assert first_update["awaiting_user_input"] is True
        assert first_update["interaction"]["confirmation_pending"] is True
        assert first_update["interaction"]["last_confirmation_payload"]["operation"] == "update"
        assert "Confirmas el cambio" in _assistant_text(first_update)

        confirmation_state = _follow_up_state(state, first_update, "si")
        final_update = handle_fixed_schedule_management_turn(confirmation_state)

        updated_blocks = final_update["schedule"]["blocks"]
        assert final_update["phase"] == "end"
        assert final_update["awaiting_user_input"] is False
        assert updated_blocks[0].block_id == "calc-1"
        assert updated_blocks[0].day_of_week == "friday"
        assert updated_blocks[0].start_time == "10:00"
        assert updated_blocks[0].end_time == "12:00"
        assert "Viernes 10:00-12:00 Calculo" in final_update["raw_inputs"]["horario_academico_text"]
        assert final_update["events"][0].dia == "Viernes"
        assert final_update["interaction"]["confirmation_pending"] is False
        assert final_update["interaction"]["last_confirmation_payload"] is None
        assert final_update["calendar"]["provider"] == "outlook"
        assert sync_service.calls[0]["student_id"] == 15
        assert sync_service.calls[0]["schedule_profile_id"] == final_update["schedule"]["persisted_profile_id"]
    finally:
        set_schedule_service(None)
        set_outlook_fixed_schedule_sync_service(None)


def test_fixed_schedule_management_deletes_block_after_confirmation() -> None:
    service = ScheduleService(repository=InMemoryScheduleRepository())
    sync_service = _FixedScheduleSyncServiceStub(synced=False)
    set_schedule_service(service)
    set_outlook_fixed_schedule_sync_service(sync_service)
    try:
        state = _state_with_message(
            "eliminar trabajo del lunes",
            blocks=[
                _block(
                    "calc-1",
                    block_type="academic",
                    title="Calculo",
                    day_of_week="monday",
                    start_time="08:00",
                    end_time="10:00",
                ),
                _block(
                    "work-1",
                    block_type="work",
                    title="Trabajo",
                    day_of_week="monday",
                    start_time="14:00",
                    end_time="18:00",
                ),
            ],
        )

        first_update = handle_fixed_schedule_management_turn(state)

        assert first_update["interaction"]["confirmation_pending"] is True
        assert first_update["interaction"]["last_confirmation_payload"]["operation"] == "delete"
        assert "Trabajo" in _assistant_text(first_update)

        confirmation_state = _follow_up_state(state, first_update, "si")
        final_update = handle_fixed_schedule_management_turn(confirmation_state)

        updated_blocks = final_update["schedule"]["blocks"]
        assert [block.title for block in updated_blocks] == ["Calculo"]
        assert final_update["raw_inputs"]["horario_laboral_text"] is None
        assert "No pude reconciliar Outlook" in _assistant_text(final_update)
        assert sync_service.calls
    finally:
        set_schedule_service(None)
        set_outlook_fixed_schedule_sync_service(None)
