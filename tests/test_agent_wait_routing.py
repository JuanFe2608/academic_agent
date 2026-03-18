"""Pruebas de espera y ruteo del flujo actualizado."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from agents.support.agent import _route_after_schedule_edit, _route_validate, _should_wait
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


def test_route_after_schedule_edit_returns_end_when_waiting() -> None:
    state = AgentState(
        phase="validate",
        awaiting_user_input=True,
    )

    assert _route_after_schedule_edit(state) == "end"


def test_route_after_schedule_edit_returns_to_validate_when_node_requests_it() -> None:
    state = AgentState(
        phase="validate",
        awaiting_user_input=False,
    )

    assert _route_after_schedule_edit(state) == "validate_schedule"


def test_route_after_schedule_edit_returns_draft_when_rebuild_is_needed() -> None:
    state = AgentState(
        phase="draft",
        awaiting_user_input=False,
    )

    assert _route_after_schedule_edit(state) == "build_draft_schedule"


def test_route_validate_goes_to_schedule_edit_when_requested() -> None:
    state = AgentState(phase="schedule_edit", awaiting_user_input=False)

    assert _route_validate(state) == "apply_schedule_correction"
