"""Grafo principal del agente de soporte."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from agents.support.nodes.apply_modifications import apply_modifications
from agents.support.nodes.ask_extracurricular import ask_extracurricular
from agents.support.nodes.build_draft_schedule import build_draft_schedule
from agents.support.nodes.collect_extracurricular_details import (
    collect_extracurricular_details,
)
from agents.support.nodes.collect_profile import collect_profile
from agents.support.nodes.confirm_profile import confirm_profile
from agents.support.nodes.generate_tentative_extracurricular import (
    generate_tentative_extracurricular,
)
from agents.support.nodes.parse_schedules_to_events import parse_schedules_to_events
from agents.support.nodes.render_schedule_preview import render_schedule_preview
from agents.support.nodes.request_schedules import request_schedules
from agents.support.nodes.validate_schedule import validate_schedule
from agents.support.nodes.welcome_consent import welcome_consent
from agents.support.nodes.utils import detect_new_input
from agents.support.state import AgentState


def _should_wait(state: AgentState) -> bool:
    messages = state.get("messages", [])
    has_new_input, _, _ = detect_new_input(
        messages,
        state.get("user_message_count", 0),
        state.get("awaiting_user_input", False),
        state.get("last_user_text"),
    )
    return bool(state.get("awaiting_user_input") and not has_new_input)


def _route_welcome(state: AgentState) -> str:
    if _should_wait(state):
        return "end"
    if state.get("phase") == "end":
        return "end"
    if state.get("phase") != "consent":
        return _route_from_phase(state)
    if state.get("consent", {}).get("accepted"):
        return "collect_profile"
    return "welcome_consent"


def _route_from_phase(state: AgentState) -> str:
    phase = state.get("phase")
    if phase == "profile":
        return "collect_profile"
    if phase == "profile_confirm":
        return "confirm_profile"
    if phase == "schedules":
        return "request_schedules"
    if phase == "extras":
        return _route_extras(state)
    if phase == "draft":
        return "build_draft_schedule"
    if phase == "validate":
        preview = state.get("schedule_preview", {})
        if not preview.get("text") and not preview.get("image_path"):
            return "render_schedule_preview"
        return "validate_schedule"
    if phase == "sync":
        return "end"
    return "welcome_consent"


def _route_collect_profile(state: AgentState) -> str:
    if _should_wait(state):
        return "end"
    profile = state.get("student_profile", {})
    required = [
        "nombre",
        "edad",
        "correo",
        "codigo",
        "programa",
        "semestre",
        "promedio",
        "ocupacion",
    ]
    if all(profile.get(field) for field in required):
        return "confirm_profile"
    return "collect_profile"


def _route_confirm_profile(state: AgentState) -> str:
    if _should_wait(state):
        return "end"
    phase = state.get("phase")
    if phase == "profile":
        return "collect_profile"
    if phase == "schedules":
        return "request_schedules"
    return "confirm_profile"


def _route_request_schedules(state: AgentState) -> str:
    if _should_wait(state):
        return "end"
    ocupacion = state.get("student_profile", {}).get("ocupacion")
    raw_inputs = state.get("raw_inputs", {})

    if ocupacion == "ninguna":
        return "end"
    if ocupacion in ("solo_trabajo", "ambos") and not raw_inputs.get(
        "horario_laboral_text"
    ):
        return "request_schedules"
    if ocupacion in ("solo_estudio", "ambos") and not raw_inputs.get(
        "horario_academico_text"
    ):
        return "request_schedules"
    return "parse_schedules_to_events"


def _route_extras(state: AgentState) -> str:
    if _should_wait(state):
        return "end"
    extras_has_any = state.get("extras_has_any")
    if extras_has_any is True:
        return "collect_extracurricular_details"
    if extras_has_any is False:
        return "build_draft_schedule"
    return "ask_extracurricular"


def _route_collect_extracurricular(state: AgentState) -> str:
    if _should_wait(state):
        return "end"
    stage = state.get("extras_collect_stage")
    if stage == "done":
        return "generate_tentative_extracurricular"
    return "collect_extracurricular_details"


def _route_validate(state: AgentState) -> str:
    if _should_wait(state):
        return "end"
    if state.get("events_validated"):
        return "end"
    return "apply_modifications"


def build_agent() -> StateGraph:
    """Construye el grafo de soporte hasta la validacion."""
    graph = StateGraph(AgentState)

    graph.add_node("welcome_consent", welcome_consent)
    graph.add_node("collect_profile", collect_profile)
    graph.add_node("confirm_profile", confirm_profile)
    graph.add_node("request_schedules", request_schedules)
    graph.add_node("parse_schedules_to_events", parse_schedules_to_events)
    graph.add_node("ask_extracurricular", ask_extracurricular)
    graph.add_node("collect_extracurricular_details", collect_extracurricular_details)
    graph.add_node("generate_tentative_extracurricular", generate_tentative_extracurricular)
    graph.add_node("build_draft_schedule", build_draft_schedule)
    graph.add_node("render_schedule_preview", render_schedule_preview)
    graph.add_node("validate_schedule", validate_schedule)
    graph.add_node("apply_modifications", apply_modifications)

    graph.set_entry_point("welcome_consent")

    graph.add_conditional_edges(
        "welcome_consent",
        _route_welcome,
        {
            "welcome_consent": "welcome_consent",
            "collect_profile": "collect_profile",
            "confirm_profile": "confirm_profile",
            "request_schedules": "request_schedules",
            "ask_extracurricular": "ask_extracurricular",
            "collect_extracurricular_details": "collect_extracurricular_details",
            "build_draft_schedule": "build_draft_schedule",
            "render_schedule_preview": "render_schedule_preview",
            "validate_schedule": "validate_schedule",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "collect_profile",
        _route_collect_profile,
        {
            "collect_profile": "collect_profile",
            "confirm_profile": "confirm_profile",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "confirm_profile",
        _route_confirm_profile,
        {
            "confirm_profile": "confirm_profile",
            "collect_profile": "collect_profile",
            "request_schedules": "request_schedules",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "request_schedules",
        _route_request_schedules,
        {
            "request_schedules": "request_schedules",
            "parse_schedules_to_events": "parse_schedules_to_events",
            "end": END,
        },
    )

    graph.add_edge("parse_schedules_to_events", "ask_extracurricular")
    graph.add_conditional_edges(
        "ask_extracurricular",
        _route_extras,
        {
            "ask_extracurricular": "ask_extracurricular",
            "collect_extracurricular_details": "collect_extracurricular_details",
            "build_draft_schedule": "build_draft_schedule",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "collect_extracurricular_details",
        _route_collect_extracurricular,
        {
            "collect_extracurricular_details": "collect_extracurricular_details",
            "generate_tentative_extracurricular": "generate_tentative_extracurricular",
            "end": END,
        },
    )
    graph.add_edge("generate_tentative_extracurricular", "build_draft_schedule")
    graph.add_edge("build_draft_schedule", "render_schedule_preview")
    graph.add_edge("render_schedule_preview", "validate_schedule")
    graph.add_conditional_edges(
        "validate_schedule",
        _route_validate,
        {
            "apply_modifications": "apply_modifications",
            "end": END,
        },
    )
    graph.add_edge("apply_modifications", "render_schedule_preview")

    return graph.compile()


agent = build_agent()
