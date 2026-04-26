"""Grafo principal del agente de soporte."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from agents.support.nodes.entry import entry_node
from agents.support.nodes.build_study_plan import build_study_plan
from agents.support.nodes.collect_priorities import collect_priorities
from agents.support.nodes.collect_study_profile import collect_study_profile
from agents.support.nodes.answer_study_recommendation import answer_study_recommendation
from agents.support.nodes.answer_scope_boundary import answer_scope_boundary
from agents.support.nodes.collect_profile import collect_profile
from agents.support.nodes.collect_schedule import collect_schedule
from agents.support.nodes.guided_academic_support import guided_academic_support
from agents.support.nodes.handle_academic_update import handle_academic_update
from agents.support.nodes.view_weekly_agenda import view_weekly_agenda
from agents.support.nodes.view_tasks import view_tasks
from agents.support.nodes.manage_fixed_schedule import manage_fixed_schedule
from agents.support.nodes.repair_fixed_schedule import repair_fixed_schedule
from agents.support.nodes.renew_fixed_schedule import renew_fixed_schedule
from agents.support.nodes.request_microsoft_oauth import request_microsoft_oauth
from agents.support.nodes.request_replan import request_replan
from agents.support.nodes.sync_study_calendar import sync_study_calendar
from agents.support.nodes.sync_study_todo import sync_study_todo
from agents.support.nodes.running_handler import running_handler
from agents.support.nodes.welcome_consent import welcome_consent
from agents.support.nodes.utils import detect_new_input
from agents.support.flows.scheduling.fixed_schedule_renewal_service import (
    requires_fixed_schedule_renewal,
)
from agents.support.flows.scheduling.fixed_schedule_repair_service import (
    requires_fixed_schedule_repair,
)
from agents.support.onboarding.validators import get_missing_profile_fields
from agents.support.priorities.config import is_post_radar_flow_enabled
from agents.support.state import AgentState
from services.personalization import is_personalization_enabled
from services.sync.microsoft_oauth_flow_service import is_microsoft_oauth_required
from services.conversation.router import (
    route_conversation_input,
    route_name_for_conversation_decision,
)


_SUBFLOW_TO_NODE: dict[str, str] = {
    "replan": "request_replan",
    "calendar_sync": "sync_study_calendar",
    "todo_sync": "sync_study_todo",
    "guided_academic_support": "guided_academic_support",
    "academic_update": "handle_academic_update",
    "study_plan": "build_study_plan",
}


_SCHEDULE_PHASES: frozenset[str] = frozenset({
    "schedules", "extras", "draft", "validate",
    "schedule_edit", "schedule_persist", "schedule_sync",
})


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


def _route_entry(state: AgentState) -> str:
    """Resuelve el siguiente nodo desde el punto de entrada del grafo."""

    conversation = state.conversation_state
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
    if conversation.phase in {"end", "running"}:
        return "running_handler" if _has_new_user_input(state) else "end"
    return _route_from_phase(state)


def _route_running(state: AgentState) -> str:
    """Coordina el modo operativo: renovación, reparación o routing conversacional."""

    if _should_wait(state):
        return "end"
    if requires_fixed_schedule_renewal(state):
        return "renew_fixed_schedule"
    if requires_fixed_schedule_repair(state):
        return "repair_fixed_schedule"
    conversation = state.conversation_state
    if conversation.awaiting_user_input:
        subflow_node = _SUBFLOW_TO_NODE.get(str(state.interaction_state.active_subflow or ""))
        if subflow_node:
            return subflow_node
    decision = route_conversation_input(
        _current_user_text(state),
        interaction=state.interaction_state,
        phase=conversation.phase,
        recent_messages=_recent_user_texts(state),
    )
    route_name = route_name_for_conversation_decision(decision)
    if route_name == "collect_priorities" and not is_post_radar_flow_enabled():
        return "answer_scope_boundary"
    return route_name


def _route_welcome_consent(state: AgentState) -> str:
    """Decide el paso siguiente tras ejecutar el nodo de consentimiento."""

    if _should_wait(state):
        return "end"
    phase = state.conversation_state.phase
    if phase == "end":
        return "end"
    if state.onboarding_state.consent.accepted:
        return "collect_profile"
    return "welcome_consent"


def _route_from_phase(state: AgentState) -> str:
    """Mapea la `phase` persistida al nodo operativo correspondiente."""

    conversation = state.conversation_state
    phase = conversation.phase
    if phase == "consent":
        if state.onboarding_state.consent.accepted:
            return "collect_profile"
        return "welcome_consent"
    if phase == "profile":
        return "collect_profile"
    if phase == "microsoft_oauth":
        return "request_microsoft_oauth"
    if phase in _SCHEDULE_PHASES:
        return "collect_schedule"
    if phase == "schedule_renewal":
        return "renew_fixed_schedule"
    if phase == "schedule_repair":
        return "repair_fixed_schedule"
    if phase == "fixed_schedule_management":
        return "manage_fixed_schedule"
    if phase == "study_profile":
        return "collect_study_profile"
    if phase == "priorities":
        if is_post_radar_flow_enabled():
            return "collect_priorities"
        return "end"
    return "welcome_consent"


def _route_collect_profile(state: AgentState) -> str:
    """Decide si el onboarding continua en perfil o avanza a schedules."""

    conversation = state.conversation_state
    if conversation.user_status == "out_of_scope" or conversation.phase in {"end", "schedules"}:
        return "end"
    if _should_wait(state):
        return "end"
    if _should_gate_profile_with_microsoft_oauth(state):
        return "request_microsoft_oauth"
    return "collect_profile"


def _route_request_microsoft_oauth(state: AgentState) -> str:
    """Mantiene el bloqueo OAuth o retorna al perfil cuando ya se autorizo."""

    if _should_wait(state):
        return "end"
    phase = state.conversation_state.phase
    if phase == "profile":
        return "collect_profile"
    if phase == "microsoft_oauth":
        return "request_microsoft_oauth"
    return "end"



def _route_collect_schedule(state: AgentState) -> str:
    """Mantiene el ciclo de captura de horario y encadena a personalizacion al terminar."""

    if _should_wait(state):
        return "end"
    phase = state.conversation_state.phase
    if phase in _SCHEDULE_PHASES:
        return "collect_schedule"
    if is_personalization_enabled() and phase == "study_profile":
        return "collect_study_profile"
    return "end"


def _route_after_schedule_renewal(state: AgentState) -> str:
    """Continúa o cierra el subflujo de renovación del horario fijo."""

    if _should_wait(state):
        return "end"
    phase = state.conversation_state.phase
    if phase == "schedules":
        return "collect_schedule"
    if phase == "schedule_renewal":
        return "renew_fixed_schedule"
    return "end"


def _route_after_schedule_repair(state: AgentState) -> str:
    """Continúa o cierra el subflujo de reparación del horario fijo."""

    if _should_wait(state):
        return "end"
    phase = state.conversation_state.phase
    if phase == "schedules":
        return "collect_schedule"
    if phase == "schedule_repair":
        return "repair_fixed_schedule"
    return "end"


def _route_after_fixed_schedule_management(state: AgentState) -> str:
    """Mantiene la gestion de horario fijo mientras espera datos o confirmacion."""

    if _should_wait(state):
        return "end"
    if _has_pending_replan(state):
        return "request_replan"
    if state.conversation_state.phase == "fixed_schedule_management":
        return "manage_fixed_schedule"
    return "end"


def _route_collect_study_profile(state: AgentState) -> str:
    """Mantiene el ciclo del Radar hasta que la fase salga de study_profile."""

    if _should_wait(state):
        return "end"
    if state.conversation_state.phase == "study_profile":
        return "collect_study_profile"
    return "end"


def _route_collect_priorities(state: AgentState) -> str:
    """Mantiene la captura semanal hasta que quede esperando input del usuario."""

    if _should_wait(state):
        return "end"
    if state.conversation_state.phase == "priorities" and is_post_radar_flow_enabled():
        return "collect_priorities"
    if state.interaction_state.active_subflow == "study_plan" and is_post_radar_flow_enabled():
        return "build_study_plan"
    return "end"


def _route_build_study_plan(state: AgentState) -> str:
    """Cierra la generación interna del plan semanal."""

    return "end"


def _route_handle_academic_update(state: AgentState) -> str:
    """Cierra actualizaciones puntuales sin activar planning posterior al Radar."""

    if _should_wait(state):
        return "end"
    if _has_pending_replan(state):
        return "request_replan"
    return "end"


def _route_after_replan(state: AgentState) -> str:
    """Mantiene el subflujo de replanificacion mientras espera confirmacion."""

    if _should_wait(state):
        return "end"
    if state.interaction_state.active_subflow == "replan":
        return "request_replan"
    return "end"


def _route_after_study_calendar_sync(state: AgentState) -> str:
    """Mantiene el flujo de calendario mientras espera confirmacion."""

    if _should_wait(state):
        return "end"
    if state.interaction_state.active_subflow == "calendar_sync":
        return "sync_study_calendar"
    return "end"


def _route_after_study_todo_sync(state: AgentState) -> str:
    """Mantiene el flujo de To Do mientras espera confirmacion."""

    if _should_wait(state):
        return "end"
    if state.interaction_state.active_subflow == "todo_sync":
        return "sync_study_todo"
    return "end"


def _should_gate_profile_with_microsoft_oauth(state: AgentState) -> bool:
    """Indica si el perfil llego al punto donde OAuth debe bloquear.

    El disparo requiere que el email este ingresado (pero aun no verificado):
    la verificacion ocurre cuando el estudiante completa el flujo OAuth, no antes.
    """

    if not is_microsoft_oauth_required():
        return False
    if state.onboarding_state.onboarding.microsoft_oauth.status == "authorized":
        return False
    profile = state.onboarding_state.student_profile
    return bool(
        profile.full_name
        and profile.student_code
        and profile.age
        and profile.institutional_email
    )


def _has_block_type(blocks: list, block_type: str) -> bool:
    """Comprueba si una colección de bloques contiene un tipo específico."""

    for block in blocks or []:
        current_type = block.get("block_type") if isinstance(block, dict) else getattr(block, "block_type", None)
        if str(current_type) == block_type:
            return True
    return False


def _has_new_user_input(state: AgentState) -> bool:
    """Detecta si el turno actual trae una entrada nueva del usuario."""

    conversation = state.conversation_state
    last_images = (
        conversation.last_user_images if conversation.phase == "schedules" else None
    )
    has_new_input, _, _ = detect_new_input(
        conversation.messages,
        conversation.user_message_count,
        conversation.awaiting_user_input,
        conversation.last_user_text,
        last_images,
    )
    return has_new_input


def _has_pending_replan(state: AgentState) -> bool:
    """Indica si hay una solicitud o propuesta de replanificacion activa."""

    replan = state.planning_state.replan
    has_plan_base = bool(state.planning_state.study_plan.plan_events)
    return bool(
        ((replan.trigger or replan.change_request) and has_plan_base)
        or (replan.status == "proposed" and replan.active_proposal)
    )


def _current_user_text(state: AgentState) -> str:
    """Devuelve el ultimo texto real del usuario en este turno."""

    conversation = state.conversation_state
    _, last_text, _ = detect_new_input(
        conversation.messages,
        conversation.user_message_count,
        conversation.awaiting_user_input,
        conversation.last_user_text,
    )
    return last_text


def _recent_user_texts(state: AgentState) -> list[str]:
    """Extrae el contenido de los ultimos 2 mensajes del usuario."""

    messages = state.conversation_state.messages or []
    user_texts = []
    for msg in messages:
        content = getattr(msg, "content", None)
        if content and getattr(msg, "type", "") in ("human", "user"):
            text = content if isinstance(content, str) else str(content)
            user_texts.append(text.strip())
    return user_texts[-2:]


def build_agent(*, checkpointer=None) -> StateGraph:
    """Construye el grafo de soporte hasta la validacion."""
    graph = StateGraph(AgentState)

    graph.add_node("__entry__", entry_node)
    graph.add_node("running_handler", running_handler)
    graph.add_node("welcome_consent", welcome_consent)
    graph.add_node("collect_profile", collect_profile)
    graph.add_node("request_microsoft_oauth", request_microsoft_oauth)
    graph.add_node("collect_schedule", collect_schedule)
    graph.add_node("renew_fixed_schedule", renew_fixed_schedule)
    graph.add_node("repair_fixed_schedule", repair_fixed_schedule)
    graph.add_node("manage_fixed_schedule", manage_fixed_schedule)
    graph.add_node("collect_study_profile", collect_study_profile)
    graph.add_node("collect_priorities", collect_priorities)
    graph.add_node("build_study_plan", build_study_plan)
    graph.add_node("handle_academic_update", handle_academic_update)
    graph.add_node("request_replan", request_replan)
    graph.add_node("sync_study_calendar", sync_study_calendar)
    graph.add_node("sync_study_todo", sync_study_todo)
    graph.add_node("guided_academic_support", guided_academic_support)
    graph.add_node("answer_study_recommendation", answer_study_recommendation)
    graph.add_node("answer_scope_boundary", answer_scope_boundary)
    graph.add_node("view_weekly_agenda", view_weekly_agenda)
    graph.add_node("view_tasks", view_tasks)

    graph.set_entry_point("__entry__")

    graph.add_conditional_edges(
        "__entry__",
        _route_entry,
        {
            "welcome_consent": "welcome_consent",
            "collect_profile": "collect_profile",
            "request_microsoft_oauth": "request_microsoft_oauth",
            "collect_schedule": "collect_schedule",
            "renew_fixed_schedule": "renew_fixed_schedule",
            "repair_fixed_schedule": "repair_fixed_schedule",
            "manage_fixed_schedule": "manage_fixed_schedule",
            "collect_study_profile": "collect_study_profile",
            "collect_priorities": "collect_priorities",
            "running_handler": "running_handler",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "running_handler",
        _route_running,
        {
            "renew_fixed_schedule": "renew_fixed_schedule",
            "repair_fixed_schedule": "repair_fixed_schedule",
            "manage_fixed_schedule": "manage_fixed_schedule",
            "handle_academic_update": "handle_academic_update",
            "request_replan": "request_replan",
            "sync_study_calendar": "sync_study_calendar",
            "sync_study_todo": "sync_study_todo",
            "guided_academic_support": "guided_academic_support",
            "answer_study_recommendation": "answer_study_recommendation",
            "answer_scope_boundary": "answer_scope_boundary",
            "view_weekly_agenda": "view_weekly_agenda",
            "view_tasks": "view_tasks",
            "collect_priorities": "collect_priorities",
            "build_study_plan": "build_study_plan",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "welcome_consent",
        _route_welcome_consent,
        {
            "welcome_consent": "welcome_consent",
            "collect_profile": "collect_profile",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "collect_profile",
        _route_collect_profile,
        {
            "collect_profile": "collect_profile",
            "request_microsoft_oauth": "request_microsoft_oauth",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "request_microsoft_oauth",
        _route_request_microsoft_oauth,
        {
            "request_microsoft_oauth": "request_microsoft_oauth",
            "collect_profile": "collect_profile",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "collect_schedule",
        _route_collect_schedule,
        {
            "collect_schedule": "collect_schedule",
            "collect_study_profile": "collect_study_profile",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "renew_fixed_schedule",
        _route_after_schedule_renewal,
        {
            "renew_fixed_schedule": "renew_fixed_schedule",
            "collect_schedule": "collect_schedule",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "repair_fixed_schedule",
        _route_after_schedule_repair,
        {
            "repair_fixed_schedule": "repair_fixed_schedule",
            "collect_schedule": "collect_schedule",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "manage_fixed_schedule",
        _route_after_fixed_schedule_management,
        {
            "manage_fixed_schedule": "manage_fixed_schedule",
            "request_replan": "request_replan",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "collect_study_profile",
        _route_collect_study_profile,
        {
            "collect_study_profile": "collect_study_profile",
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
    graph.add_conditional_edges(
        "handle_academic_update",
        _route_handle_academic_update,
        {
            "build_study_plan": "build_study_plan",
            "request_replan": "request_replan",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "request_replan",
        _route_after_replan,
        {
            "request_replan": "request_replan",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "sync_study_calendar",
        _route_after_study_calendar_sync,
        {
            "sync_study_calendar": "sync_study_calendar",
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "sync_study_todo",
        _route_after_study_todo_sync,
        {
            "sync_study_todo": "sync_study_todo",
            "end": END,
        },
    )
    graph.add_edge("answer_study_recommendation", END)
    graph.add_edge("guided_academic_support", END)
    graph.add_edge("answer_scope_boundary", END)
    graph.add_edge("view_weekly_agenda", END)
    graph.add_edge("view_tasks", END)

    return graph.compile(checkpointer=checkpointer)


agent = build_agent()
