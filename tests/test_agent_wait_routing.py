"""Pruebas de espera para evitar loops sin entrada nueva."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from agents.support.agent import _route_after_apply_modifications, _route_validate, _should_wait
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


def test_route_after_apply_modifications_returns_to_validate_when_waiting() -> None:
    state = AgentState(
        phase="validate",
        awaiting_user_input=True,
    )

    assert _route_after_apply_modifications(state) == "validate_schedule"


def test_route_after_apply_modifications_rerenders_preview_after_change() -> None:
    state = AgentState(
        phase="validate",
        awaiting_user_input=False,
    )

    assert _route_after_apply_modifications(state) == "render_schedule_preview"


def test_route_validate_rerenders_preview_when_returning_to_main_menu() -> None:
    state = AgentState(
        phase="validate",
        awaiting_user_input=False,
        replan={"return_to_menu": True},
    )

    assert _route_validate(state) == "render_schedule_preview"
