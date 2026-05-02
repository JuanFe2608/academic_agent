"""Nodo LangGraph para capturar el horario fijo del estudiante.

El nodo conserva únicamente la coordinación mínima del turno conversacional:
lee el estado, detecta nueva entrada y delega la lógica de negocio al servicio
de aplicación de scheduling.
"""

from __future__ import annotations

from agents.support.nodes.utils import detect_new_input, get_last_user_images
from agents.support.flows.scheduling.schedule_capture_service import (
    ScheduleCapturePrompts,
    handle_schedule_capture_turn,
)
from agents.support.state import AgentState
from utils.media_artifacts import IMAGE_RECEIVED_MARKER

from .prompt import (
    PROMPT_ACADEMICO,
    PROMPT_LABORAL,
    PROMPT_MORE_ACADEMIC,
    PROMPT_MORE_WORK,
    PROMPT_NINGUNA,
    PROMPT_OCCUPATION,
)


def request_schedules(state: AgentState) -> dict:
    """Procesa un turno de captura de horario delegando al servicio del dominio."""

    messages = state.get("messages", [])
    has_new_input, last_text, current_count = detect_new_input(
        messages,
        state.get("user_message_count", 0),
        state.get("awaiting_user_input", False),
        state.get("last_user_text"),
        state.get("last_user_images", []),
    )
    last_images = get_last_user_images(messages)
    if (
        not last_images
        and has_new_input
        and IMAGE_RECEIVED_MARKER in str(last_text or "")
    ):
        last_images = [
            str(image).strip()
            for image in state.get("last_user_images", [])
            if str(image or "").strip()
        ]
    prompts = ScheduleCapturePrompts(
        occupation=PROMPT_OCCUPATION,
        academic=PROMPT_ACADEMICO,
        work=PROMPT_LABORAL,
        none=PROMPT_NINGUNA,
        more_academic=PROMPT_MORE_ACADEMIC,
        more_work=PROMPT_MORE_WORK,
    )
    update = handle_schedule_capture_turn(
        state,
        has_new_input=has_new_input,
        last_text=last_text,
        last_images=last_images,
        current_count=current_count,
        prompts=prompts,
    )
    return update
