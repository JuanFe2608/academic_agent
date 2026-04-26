"""Pruebas de espera y ruteo del flujo actualizado."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

import agents.support.agent as agent_module
from agents.support.agent import (
    _route_after_fixed_schedule_management,
    _route_after_schedule_repair,
    _route_collect_profile,
    _route_collect_schedule,
    _route_entry,
    _route_running,
    _should_wait,
)
from agents.support.state import AgentState


def test_should_wait_in_extras_with_stale_image_message() -> None:
    """En fase extras no debe tratar una imagen vieja como entrada nueva."""
    state = AgentState(
        phase="extras",
        awaiting_user_input=True,
        user_message_count=1,
        last_user_text="",
        messages=[
            HumanMessage(
                content=[{"type": "input_image", "image_url": {"url": "data:image/png;base64,abc"}}]
            )
        ],
    )

    assert _should_wait(state) is True


def test_route_collect_schedule_returns_end_when_waiting() -> None:
    state = AgentState(
        phase="validate",
        awaiting_user_input=True,
    )

    assert _route_collect_schedule(state) == "end"


def test_route_collect_schedule_continues_on_validate_phase() -> None:
    state = AgentState(
        phase="validate",
        awaiting_user_input=False,
    )

    assert _route_collect_schedule(state) == "collect_schedule"


def test_route_collect_schedule_continues_on_draft_phase() -> None:
    state = AgentState(
        phase="draft",
        awaiting_user_input=False,
    )

    assert _route_collect_schedule(state) == "collect_schedule"


def test_route_collect_schedule_continues_on_schedule_edit_phase() -> None:
    state = AgentState(phase="schedule_edit", awaiting_user_input=False)

    assert _route_collect_schedule(state) == "collect_schedule"


def test_route_collect_schedule_continues_on_schedules_phase() -> None:
    state = AgentState(phase="schedules", awaiting_user_input=False)

    assert _route_collect_schedule(state) == "collect_schedule"


def test_route_collect_profile_stops_when_user_is_out_of_scope() -> None:
    state = AgentState(
        phase="end",
        user_status="out_of_scope",
        awaiting_user_input=False,
        student_profile={"full_name": "Ana Maria Perez"},
    )

    assert _route_collect_profile(state) == "end"


def test_route_collect_schedule_stops_when_waiting_for_clarification() -> None:
    state = AgentState(
        phase="schedules",
        awaiting_user_input=True,
        academic_pending_items=[
            {
                "schedule_type": "academic",
                "title": "DATA SCIENCE FUNDAMENTALS",
                "days": ["Lunes"],
                "missing_fields": ["aclarar AM o PM en el horario"],
                "raw_text": "Lunes 6-7 DATA SCIENCE FUNDAMENTALS",
            }
        ],
    )

    assert _route_collect_schedule(state) == "end"


def test_route_collect_schedule_continues_on_extras_phase() -> None:
    state = AgentState(
        phase="extras",
        awaiting_user_input=False,
    )

    assert _route_collect_schedule(state) == "collect_schedule"


def test_route_entry_reopens_with_schedule_renewal_when_expired_and_user_writes(
    monkeypatch,
) -> None:
    monkeypatch.setattr(agent_module, "requires_fixed_schedule_renewal", lambda _state: True)
    state = AgentState(
        phase="end",
        awaiting_user_input=False,
        user_message_count=0,
        messages=[HumanMessage(content="hola")],
        student_profile={"persisted_student_id": 1},
    )

    assert _route_entry(state) == "running_handler"
    assert _route_running(state) == "renew_fixed_schedule"


def test_route_entry_reopens_with_schedule_repair_when_drift_pending(
    monkeypatch,
) -> None:
    monkeypatch.setattr(agent_module, "requires_fixed_schedule_renewal", lambda _state: False)
    monkeypatch.setattr(agent_module, "requires_fixed_schedule_repair", lambda _state: True)
    state = AgentState(
        phase="end",
        awaiting_user_input=False,
        user_message_count=0,
        messages=[HumanMessage(content="hola")],
        student_profile={"persisted_student_id": 1},
    )

    assert _route_entry(state) == "running_handler"
    assert _route_running(state) == "repair_fixed_schedule"


def test_route_entry_routes_prioritization_request_when_post_radar_flag_enabled(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ACADEMIC_AGENT_ENABLE_POST_RADAR_FLOW", "1")
    monkeypatch.setattr(agent_module, "requires_fixed_schedule_renewal", lambda _state: False)
    monkeypatch.setattr(agent_module, "requires_fixed_schedule_repair", lambda _state: False)
    state = AgentState(
        phase="end",
        awaiting_user_input=False,
        user_message_count=0,
        messages=[HumanMessage(content="quiero priorizar mis materias")],
    )

    assert _route_entry(state) == "running_handler"
    assert _route_running(state) == "collect_priorities"


def test_route_entry_blocks_prioritization_request_without_post_radar_flag(
    monkeypatch,
) -> None:
    monkeypatch.delenv("ACADEMIC_AGENT_ENABLE_POST_RADAR_FLOW", raising=False)
    monkeypatch.setattr(agent_module, "requires_fixed_schedule_renewal", lambda _state: False)
    monkeypatch.setattr(agent_module, "requires_fixed_schedule_repair", lambda _state: False)
    state = AgentState(
        phase="end",
        awaiting_user_input=False,
        user_message_count=0,
        messages=[HumanMessage(content="quiero priorizar mis materias")],
    )

    assert _route_entry(state) == "running_handler"
    assert _route_running(state) == "answer_scope_boundary"


def test_route_after_schedule_repair_can_restart_schedule_capture() -> None:
    state = AgentState(phase="schedules", awaiting_user_input=False)

    assert _route_after_schedule_repair(state) == "collect_schedule"


def test_route_after_fixed_schedule_management_waits_for_confirmation() -> None:
    waiting = AgentState(phase="fixed_schedule_management", awaiting_user_input=True)
    continuing = AgentState(phase="fixed_schedule_management", awaiting_user_input=False)

    assert _route_after_fixed_schedule_management(waiting) == "end"
    assert _route_after_fixed_schedule_management(continuing) == "manage_fixed_schedule"
