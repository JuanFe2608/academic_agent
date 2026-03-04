"""Pruebas de espera para evitar loops sin entrada nueva."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from agents.support.agent import _should_wait
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
