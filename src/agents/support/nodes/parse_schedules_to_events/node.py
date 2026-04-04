"""Nodo LangGraph para parsear y normalizar horarios fijos."""

from __future__ import annotations

from agents.support.nodes.request_schedules.prompt import (
    PROMPT_LABORAL,
    PROMPT_MORE_ACADEMIC,
    PROMPT_MORE_WORK,
)
from agents.support.flows.scheduling.schedule_parsing_service import (
    ScheduleParsingPrompts,
    handle_schedule_parsing_turn,
)
from agents.support.state import AgentState


def parse_schedules_to_events(state: AgentState) -> dict:
    """Delegates fixed-schedule parsing to the scheduling application service."""

    prompts = ScheduleParsingPrompts(
        academic_text_required="Necesito tu horario académico por escrito para poder interpretarlo.",
        work_text_required="Necesito tu horario laboral por escrito para poder interpretarlo.",
        work_request=PROMPT_LABORAL,
        more_academic=PROMPT_MORE_ACADEMIC,
        more_work=PROMPT_MORE_WORK,
    )
    return handle_schedule_parsing_turn(state, prompts=prompts)
