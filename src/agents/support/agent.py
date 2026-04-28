"""Grafo principal del agente de soporte.

Fase 2 — 8 nodos:
  __entry__ → welcome_consent → collect_profile → (request_microsoft_oauth)
            → collect_schedule → collect_study_profile → collect_priorities
            → academic_agent

Todos los nodos del modo running y los sub-flujos de mantenimiento del horario
quedan absorbidos dentro de academic_agent. build_study_plan es un paso interno
de collect_priorities.
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from agents.support.nodes.academic_agent import academic_agent
from agents.support.nodes.collect_priorities import collect_priorities
from agents.support.nodes.collect_profile import collect_profile
from agents.support.nodes.collect_schedule import collect_schedule
from agents.support.nodes.collect_study_profile import collect_study_profile
from agents.support.nodes.entry import entry_node
from agents.support.nodes.request_microsoft_oauth import request_microsoft_oauth
from agents.support.nodes.welcome_consent import welcome_consent
from agents.support.nodes.utils import detect_new_input
from agents.support.onboarding.validators import get_missing_profile_fields
from agents.support.priorities.config import is_post_radar_flow_enabled
from agents.support.state import AgentState
from services.personalization import is_personalization_enabled
from services.sync.microsoft_oauth_flow_service import is_microsoft_oauth_required


_SCHEDULE_PHASES: frozenset[str] = frozenset({
    "schedules", "extras", "draft", "validate",
    "schedule_edit", "schedule_persist", "schedule_sync",
})

_ACADEMIC_AGENT_PHASES: frozenset[str] = frozenset({
    "running", "end",
    "schedule_renewal", "schedule_repair", "fixed_schedule_management",
})


# ---------------------------------------------------------------------------
# Helpers de routing
# ---------------------------------------------------------------------------

def _should_wait(state: AgentState) -> bool:
    """True cuando el grafo debe detenerse hasta recibir nueva entrada del usuario."""
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
    return bool(conversation.awaiting_user_input and not has_new_input)


def _has_new_user_input(state: AgentState) -> bool:
    """True cuando el turno actual trae una entrada nueva del usuario."""
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


# ---------------------------------------------------------------------------
# Funciones de routing de aristas condicionales
# ---------------------------------------------------------------------------

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
    if conversation.phase in _ACADEMIC_AGENT_PHASES:
        return "academic_agent" if _has_new_user_input(state) else "end"
    return _route_from_phase(state)


def _route_from_phase(state: AgentState) -> str:
    """Mapea la `phase` persistida al nodo operativo correspondiente."""
    phase = state.conversation_state.phase
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
    if phase in _ACADEMIC_AGENT_PHASES:
        return "academic_agent"
    if phase == "study_profile":
        return "collect_study_profile"
    if phase == "priorities":
        if is_post_radar_flow_enabled():
            return "collect_priorities"
        return "end"
    return "welcome_consent"


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


def _route_collect_profile(state: AgentState) -> str:
    """Decide si el onboarding continúa en perfil o avanza a schedules."""
    conversation = state.conversation_state
    if conversation.user_status == "out_of_scope" or conversation.phase == "end":
        return "end"
    if conversation.phase in _SCHEDULE_PHASES:
        return "collect_schedule"
    if _should_wait(state):
        return "end"
    if _should_gate_profile_with_microsoft_oauth(state):
        return "request_microsoft_oauth"
    return "collect_profile"


def _route_request_microsoft_oauth(state: AgentState) -> str:
    """Mantiene el bloqueo OAuth o retorna al perfil cuando ya se autorizó."""
    if _should_wait(state):
        return "end"
    phase = state.conversation_state.phase
    if phase == "profile":
        return "collect_profile"
    if phase == "microsoft_oauth":
        return "request_microsoft_oauth"
    return "end"


def _route_collect_schedule(state: AgentState) -> str:
    """Mantiene el ciclo de captura de horario y encadena a personalización al terminar."""
    if _should_wait(state):
        return "end"
    phase = state.conversation_state.phase
    if phase in _SCHEDULE_PHASES:
        return "collect_schedule"
    if is_personalization_enabled() and phase == "study_profile":
        return "collect_study_profile"
    return "end"


def _route_collect_study_profile(state: AgentState) -> str:
    """Mantiene el ciclo del Radar hasta que la fase salga de study_profile."""
    if _should_wait(state):
        return "end"
    if state.conversation_state.phase == "study_profile":
        return "collect_study_profile"
    return "end"


def _route_collect_priorities(state: AgentState) -> str:
    """Mantiene la captura semanal mientras siga en fase priorities."""
    if _should_wait(state):
        return "end"
    if state.conversation_state.phase == "priorities" and is_post_radar_flow_enabled():
        return "collect_priorities"
    return "end"


def _route_academic_agent(state: AgentState) -> str:
    """Mantiene el bucle del agente o redirige a collect_schedule tras renovación."""
    if _should_wait(state):
        return "end"
    phase = state.conversation_state.phase
    # Renovación/reparación completada y redirige a captura de nuevo horario
    if phase in _SCHEDULE_PHASES:
        return "collect_schedule"
    # Fases de mantenimiento sin espera — continuar proactivamente
    if phase in {"schedule_renewal", "schedule_repair", "fixed_schedule_management"}:
        return "academic_agent"
    return "end"


# ---------------------------------------------------------------------------
# Helper de condición de OAuth
# ---------------------------------------------------------------------------

def _should_gate_profile_with_microsoft_oauth(state: AgentState) -> bool:
    """True cuando el perfil llegó al punto donde OAuth debe bloquear."""
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
        current_type = (
            block.get("block_type") if isinstance(block, dict)
            else getattr(block, "block_type", None)
        )
        if str(current_type) == block_type:
            return True
    return False


# ---------------------------------------------------------------------------
# Construcción del grafo
# ---------------------------------------------------------------------------

def build_agent(*, checkpointer=None) -> StateGraph:
    """Construye el grafo con 8 nodos."""
    graph = StateGraph(AgentState)

    graph.add_node("__entry__", entry_node)
    graph.add_node("welcome_consent", welcome_consent)
    graph.add_node("collect_profile", collect_profile)
    graph.add_node("request_microsoft_oauth", request_microsoft_oauth)
    graph.add_node("collect_schedule", collect_schedule)
    graph.add_node("collect_study_profile", collect_study_profile)
    graph.add_node("collect_priorities", collect_priorities)
    graph.add_node("academic_agent", academic_agent)

    graph.set_entry_point("__entry__")

    graph.add_conditional_edges(
        "__entry__",
        _route_entry,
        {
            "welcome_consent": "welcome_consent",
            "collect_profile": "collect_profile",
            "request_microsoft_oauth": "request_microsoft_oauth",
            "collect_schedule": "collect_schedule",
            "collect_study_profile": "collect_study_profile",
            "collect_priorities": "collect_priorities",
            "academic_agent": "academic_agent",
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
            "collect_schedule": "collect_schedule",
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
            "end": END,
        },
    )
    graph.add_conditional_edges(
        "academic_agent",
        _route_academic_agent,
        {
            "academic_agent": "academic_agent",
            "collect_schedule": "collect_schedule",
            "end": END,
        },
    )

    return graph.compile(checkpointer=checkpointer)


agent = build_agent()
