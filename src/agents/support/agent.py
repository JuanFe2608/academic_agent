"""Grafo principal del agente de soporte."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from agents.support.nodes.build_study_plan import build_study_plan
from agents.support.nodes.collect_priorities import collect_priorities
from agents.support.nodes.collect_study_profile import collect_study_profile
from agents.support.nodes.collect_study_profile_tiebreaker import (
    collect_study_profile_tiebreaker,
)
from agents.support.nodes.apply_schedule_correction import apply_schedule_correction
from agents.support.nodes.ask_extracurricular import ask_extracurricular
from agents.support.nodes.build_draft_schedule import build_draft_schedule
from agents.support.nodes.collect_extracurricular_details import (
    collect_extracurricular_details,
)
from agents.support.nodes.collect_profile import collect_profile
from agents.support.nodes.confirm_profile import confirm_profile
from agents.support.nodes.persist_profile import persist_profile
from agents.support.nodes.persist_study_profile import persist_study_profile
from agents.support.nodes.parse_schedules_to_events import parse_schedules_to_events
from agents.support.nodes.persist_schedule import persist_schedule
from agents.support.nodes.render_schedule_preview import render_schedule_preview
from agents.support.nodes.request_schedules import request_schedules
from agents.support.nodes.send_email_verification import send_email_verification
from agents.support.nodes.validate_schedule import validate_schedule
from agents.support.nodes.verify_email_code import verify_email_code
from agents.support.nodes.welcome_consent import welcome_consent
from agents.support.nodes.utils import detect_new_input
from agents.support.onboarding.validators import (
    get_missing_profile_fields,
    profile_requires_email_verification,
)
from agents.support.state import AgentState
from services.personalization import is_personalization_enabled


def _should_wait(state: AgentState) -> bool:
    """Indica si el grafo debe detenerse hasta recibir nueva entrada."""

    conversation = state.conversation_state
    messages = conversation.messages
    last_images = (
        conversation.last_user_images if conversation.phase == "schedules" else None
    )
    has_new_input, _, _ = detect_new_input(
        messages,
        conversation.user_message_count,
        conversation.awaiting_user_input,
        conversation.last_user_text,
        last_images,
    )
    return bool(conversation.awaiting_user_input and not has_new_input)


def _route_welcome(state: AgentState) -> str:
    """Resuelve el siguiente nodo cuando el flujo parte desde bienvenida."""

    conversation = state.conversation_state
    onboarding = state.onboarding_state
    if conversation.user_status == "out_of_scope":
        has_new_input, _, _ = detect_new_input(
            conversation.messages,
            conversation.user_message_count,
            conversation.awaiting_user_input,
            conversation.last_user_text,
        )
        return "welcome_consent" if has_new_input else "end"
    if _should_wait(state):
        return "end"
    if conversation.phase == "end":
        return "end"
    if conversation.phase != "consent":
        return _route_from_phase(state)
    if onboarding.consent.accepted:
        return "collect_profile"
    return "welcome_consent"


def _route_from_phase(state: AgentState) -> str:
    """Mapea la `phase` persistida al nodo operativo correspondiente."""

    conversation = state.conversation_state
    scheduling = state.scheduling_state
    planning = state.planning_state
    phase = conversation.phase
    if phase == "profile":
        return "collect_profile"
    if phase == "email_verification_send":
        return "send_email_verification"
    if phase == "email_verification":
        return "verify_email_code"
    if phase == "profile_confirm":
        return "confirm_profile"
    if phase == "profile_persist":
        return "persist_profile"
    if phase == "schedules":
        return "request_schedules"
    if phase == "extras":
        return _route_extras(state)
    if phase == "draft":
        return "build_draft_schedule"
    if phase == "validate":
        preview = scheduling.schedule_preview
        if not preview.text and not preview.image_path:
            return "render_schedule_preview"
        return "validate_schedule"
    if phase == "schedule_edit":
        return "apply_schedule_correction"
    if phase == "schedule_persist":
        return "persist_schedule"
    if phase == "sync":
        if is_personalization_enabled():
            if planning.study_profile.status != "completed":
                return "collect_study_profile"
        return "end"
    if phase == "study_profile":
        return "collect_study_profile"
    if phase == "study_profile_tiebreaker":
        return "collect_study_profile_tiebreaker"
    if phase == "study_profile_persist":
        return "persist_study_profile"
    if phase == "priorities":
        return "collect_priorities"
    if phase == "study_plan":
        return "build_study_plan"
    return "welcome_consent"


def _route_collect_profile(state: AgentState) -> str:
    """Decide si el onboarding continúa, verifica correo o confirma perfil."""

    conversation = state.conversation_state
    onboarding = state.onboarding_state
    if conversation.user_status == "out_of_scope" or conversation.phase == "end":
        return "end"
    if _should_wait(state):
        return "end"
    profile = onboarding.student_profile
    if profile_requires_email_verification(profile.model_dump(mode="python")):
        return "send_email_verification"
    if not get_missing_profile_fields(profile.model_dump(mode="python")):
        return "confirm_profile"
    return "collect_profile"


def _route_send_email_verification(state: AgentState) -> str:
    """Mantiene o avanza el subflujo de envío del código de correo."""

    if _should_wait(state):
        return "end"
    phase = state.conversation_state.phase
    if phase == "profile":
        return "collect_profile"
    return "verify_email_code"


def _route_verify_email_code(state: AgentState) -> str:
    """Mantiene o reencamina la validación del código institucional."""

    if _should_wait(state):
        return "end"
    phase = state.conversation_state.phase
    if phase == "email_verification_send":
        return "send_email_verification"
    if phase == "profile":
        return "collect_profile"
    return "verify_email_code"


def _route_confirm_profile(state: AgentState) -> str:
    """Controla la confirmación final del perfil antes de persistirlo."""

    if _should_wait(state):
        return "end"
    phase = state.conversation_state.phase
    if phase == "profile":
        return "collect_profile"
    if phase == "profile_persist":
        return "persist_profile"
    if phase == "schedules":
        return "request_schedules"
    return "confirm_profile"


def _route_persist_profile(state: AgentState) -> str:
    """Encadena persistencia de perfil con captura de horarios o correcciones."""

    if _should_wait(state):
        return "end"
    phase = state.conversation_state.phase
    if phase == "profile":
        return "collect_profile"
    if phase == "profile_confirm":
        return "confirm_profile"
    if phase == "email_verification":
        return "verify_email_code"
    if phase == "schedules":
        return "request_schedules"
    return "persist_profile"


def _route_request_schedules(state: AgentState) -> str:
    """Determina si aún falta captura o si ya puede parsearse el horario."""

    if _should_wait(state):
        return "end"
    onboarding = state.onboarding_state
    scheduling = state.scheduling_state
    conversation = state.conversation_state
    occupation = onboarding.student_profile.occupation
    raw_inputs = scheduling.raw_inputs
    academic_pending_items = scheduling.academic_pending_items
    work_pending_items = scheduling.work_pending_items
    schedule_state = scheduling.schedule
    capture_target = schedule_state.capture_target
    capture_stage = schedule_state.capture_stage or "idle"

    if not occupation:
        return "request_schedules"

    if occupation == "ninguna":
        return "end"

    if academic_pending_items or work_pending_items:
        return "request_schedules"

    if capture_target in {"academic", "work"} and not conversation.awaiting_user_input:
        return "parse_schedules_to_events"

    if (
        not conversation.awaiting_user_input
        and (
            raw_inputs.horario_academico_text
            or raw_inputs.horario_laboral_text
        )
    ):
        if occupation == "ambos" and not raw_inputs.horario_academico_text:
            return "request_schedules"
        return "parse_schedules_to_events"

    if conversation.phase == "extras":
        return "ask_extracurricular"

    if capture_stage == "idle":
        return "request_schedules"

    return "request_schedules"


def _route_extras(state: AgentState) -> str:
    """Resuelve el paso siguiente para actividades extracurriculares."""

    if _should_wait(state):
        return "end"
    extras_has_any = state.scheduling_state.extras_has_any
    if extras_has_any is True:
        return "collect_extracurricular_details"
    if extras_has_any is False:
        return "build_draft_schedule"
    return "ask_extracurricular"


def _route_collect_extracurricular(state: AgentState) -> str:
    """Mantiene la recolección de extras hasta completar pendientes."""

    if _should_wait(state):
        return "end"
    stage = state.scheduling_state.extras_collect_stage
    if stage == "done":
        return "build_draft_schedule"
    return "collect_extracurricular_details"


def _route_after_parse_schedules(state: AgentState) -> str:
    """Encadena el parseo exitoso hacia el bloque de extras o finaliza."""

    if _should_wait(state):
        return "end"
    if state.conversation_state.phase == "extras":
        return "ask_extracurricular"
    return "end"


def _route_validate(state: AgentState) -> str:
    """Decide si el usuario acepta, corrige o persiste el horario."""

    if _should_wait(state):
        return "end"
    phase = state.conversation_state.phase
    if phase == "schedule_edit":
        return "apply_schedule_correction"
    if phase == "schedule_persist":
        return "persist_schedule"
    return "end"


def _route_after_schedule_edit(state: AgentState) -> str:
    """Devuelve al borrador o a validación tras aplicar una corrección."""

    if _should_wait(state):
        return "end"
    if state.conversation_state.phase == "validate":
        return "validate_schedule"
    return "build_draft_schedule"


def _route_after_persist_schedule(state: AgentState) -> str:
    """Activa personalización opcional después de guardar el horario."""

    if _should_wait(state):
        return "end"
    conversation = state.conversation_state
    planning = state.planning_state
    if not is_personalization_enabled():
        return "end"
    if conversation.phase == "study_profile_persist":
        return "persist_study_profile"
    if conversation.phase == "study_profile":
        return "collect_study_profile"
    if conversation.phase == "sync" and planning.study_profile.status != "completed":
        return "collect_study_profile"
    return "end"


def _route_collect_study_profile(state: AgentState) -> str:
    """Controla la transición entre radar principal, desempate y persistencia."""

    if _should_wait(state):
        return "end"
    phase = state.conversation_state.phase
    if phase == "study_profile_tiebreaker":
        return "collect_study_profile_tiebreaker"
    if phase == "study_profile_persist":
        return "persist_study_profile"
    if phase == "end":
        return "end"
    return "collect_study_profile"


def _route_collect_study_profile_tiebreaker(state: AgentState) -> str:
    """Gestiona el subflujo de desempate del perfil de estudio."""

    if _should_wait(state):
        return "end"
    phase = state.conversation_state.phase
    if phase == "study_profile":
        return "collect_study_profile"
    if phase == "study_profile_persist":
        return "persist_study_profile"
    if phase == "end":
        return "end"
    return "collect_study_profile_tiebreaker"


def _route_persist_study_profile(state: AgentState) -> str:
    """Finaliza o reintenta la persistencia del perfil de personalización."""

    if _should_wait(state):
        return "end"
    phase = state.conversation_state.phase
    if phase == "study_profile_tiebreaker":
        return "collect_study_profile_tiebreaker"
    if phase == "study_profile":
        return "collect_study_profile"
    if phase == "priorities":
        return "collect_priorities"
    if phase == "study_plan":
        return "build_study_plan"
    return "end"


def _route_collect_priorities(state: AgentState) -> str:
    """Coordina la captura de prioridades y el recálculo del plan."""

    if _should_wait(state):
        return "end"
    phase = state.conversation_state.phase
    if phase == "study_plan":
        return "build_study_plan"
    if phase == "end":
        return "end"
    return "collect_priorities"


def _route_build_study_plan(state: AgentState) -> str:
    """Finaliza el subflujo de plan semanal o vuelve a prioridades si aplica."""

    if _should_wait(state):
        return "end"
    if state.conversation_state.phase == "priorities":
        return "collect_priorities"
    return "end"


def _has_block_type(blocks: list, block_type: str) -> bool:
    """Comprueba si una colección de bloques contiene un tipo específico."""

    for block in blocks or []:
        current_type = block.get("block_type") if isinstance(block, dict) else getattr(block, "block_type", None)
        if str(current_type) == block_type:
            return True
    return False


def build_agent() -> StateGraph:
    """Construye el grafo de soporte hasta la validacion."""
    graph = StateGraph(AgentState)

    graph.add_node("welcome_consent", welcome_consent)
    graph.add_node("collect_profile", collect_profile)
    graph.add_node("send_email_verification", send_email_verification)
    graph.add_node("verify_email_code", verify_email_code)
    graph.add_node("confirm_profile", confirm_profile)
    graph.add_node("persist_profile", persist_profile)
    graph.add_node("request_schedules", request_schedules)
    graph.add_node("parse_schedules_to_events", parse_schedules_to_events)
    graph.add_node("ask_extracurricular", ask_extracurricular)
    graph.add_node("collect_extracurricular_details", collect_extracurricular_details)
    graph.add_node("build_draft_schedule", build_draft_schedule)
    graph.add_node("render_schedule_preview", render_schedule_preview)
    graph.add_node("validate_schedule", validate_schedule)
    graph.add_node("apply_schedule_correction", apply_schedule_correction)
    graph.add_node("persist_schedule", persist_schedule)
    graph.add_node("collect_study_profile", collect_study_profile)
    graph.add_node("collect_study_profile_tiebreaker", collect_study_profile_tiebreaker)
    graph.add_node("persist_study_profile", persist_study_profile)
    graph.add_node("collect_priorities", collect_priorities)
    graph.add_node("build_study_plan", build_study_plan)

    graph.set_entry_point("welcome_consent")

    graph.add_conditional_edges(
        "welcome_consent",
        _route_welcome,
        {
            "welcome_consent": "welcome_consent",
            "collect_profile": "collect_profile",
            "send_email_verification": "send_email_verification",
            "verify_email_code": "verify_email_code",
            "confirm_profile": "confirm_profile",
            "persist_profile": "persist_profile",
            "request_schedules": "request_schedules",
            "ask_extracurricular": "ask_extracurricular",
            "collect_extracurricular_details": "collect_extracurricular_details",
            "build_draft_schedule": "build_draft_schedule",
            "render_schedule_preview": "render_schedule_preview",
            "validate_schedule": "validate_schedule",
            "apply_schedule_correction": "apply_schedule_correction",
            "persist_schedule": "persist_schedule",
            "collect_study_profile": "collect_study_profile",
            "collect_study_profile_tiebreaker": "collect_study_profile_tiebreaker",
            "persist_study_profile": "persist_study_profile",
            "collect_priorities": "collect_priorities",
            "build_study_plan": "build_study_plan",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "collect_profile",
        _route_collect_profile,
        {
            "collect_profile": "collect_profile",
            "send_email_verification": "send_email_verification",
            "confirm_profile": "confirm_profile",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "send_email_verification",
        _route_send_email_verification,
        {
            "collect_profile": "collect_profile",
            "verify_email_code": "verify_email_code",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "verify_email_code",
        _route_verify_email_code,
        {
            "send_email_verification": "send_email_verification",
            "collect_profile": "collect_profile",
            "verify_email_code": "verify_email_code",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "confirm_profile",
        _route_confirm_profile,
        {
            "confirm_profile": "confirm_profile",
            "collect_profile": "collect_profile",
            "persist_profile": "persist_profile",
            "request_schedules": "request_schedules",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "persist_profile",
        _route_persist_profile,
        {
            "persist_profile": "persist_profile",
            "collect_profile": "collect_profile",
            "verify_email_code": "verify_email_code",
            "confirm_profile": "confirm_profile",
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

    graph.add_conditional_edges(
        "parse_schedules_to_events",
        _route_after_parse_schedules,
        {
            "ask_extracurricular": "ask_extracurricular",
            "end": END,
        },
    )
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
            "build_draft_schedule": "build_draft_schedule",
            "end": END,
        },
    )
    graph.add_edge("build_draft_schedule", "render_schedule_preview")
    graph.add_edge("render_schedule_preview", "validate_schedule")
    graph.add_conditional_edges(
        "validate_schedule",
        _route_validate,
        {
            "apply_schedule_correction": "apply_schedule_correction",
            "persist_schedule": "persist_schedule",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "apply_schedule_correction",
        _route_after_schedule_edit,
        {
            "validate_schedule": "validate_schedule",
            "build_draft_schedule": "build_draft_schedule",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "persist_schedule",
        _route_after_persist_schedule,
        {
            "collect_study_profile": "collect_study_profile",
            "collect_study_profile_tiebreaker": "collect_study_profile_tiebreaker",
            "persist_study_profile": "persist_study_profile",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "collect_study_profile",
        _route_collect_study_profile,
        {
            "collect_study_profile": "collect_study_profile",
            "collect_study_profile_tiebreaker": "collect_study_profile_tiebreaker",
            "persist_study_profile": "persist_study_profile",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "collect_study_profile_tiebreaker",
        _route_collect_study_profile_tiebreaker,
        {
            "collect_study_profile": "collect_study_profile",
            "collect_study_profile_tiebreaker": "collect_study_profile_tiebreaker",
            "persist_study_profile": "persist_study_profile",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "persist_study_profile",
        _route_persist_study_profile,
        {
            "collect_study_profile": "collect_study_profile",
            "collect_study_profile_tiebreaker": "collect_study_profile_tiebreaker",
            "collect_priorities": "collect_priorities",
            "build_study_plan": "build_study_plan",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "collect_priorities",
        _route_collect_priorities,
        {
            "collect_priorities": "collect_priorities",
            "build_study_plan": "build_study_plan",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "build_study_plan",
        _route_build_study_plan,
        {
            "collect_priorities": "collect_priorities",
            "end": END,
        },
    )

    return graph.compile()


agent = build_agent()
