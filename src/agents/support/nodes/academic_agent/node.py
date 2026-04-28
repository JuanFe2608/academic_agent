"""Nodo único del modo operativo — agente ReAct autónomo (Fase 3/4).

Arquitectura:
  - Fases de mantenimiento (schedule_renewal, schedule_repair,
    fixed_schedule_management): handlers deterministas sin cambios.
  - Fase running: create_react_agent con 11 tools y contexto completo
    del estudiante. El LLM decide qué hacer, en qué orden y qué combinar.

Fases siguientes:
  Fase 5 — RAG como tool de primera clase (search_study_methods ya wired).
"""

from __future__ import annotations

from agents.support.flows.scheduling.fixed_schedule_renewal_service import (
    requires_fixed_schedule_renewal,
)
from agents.support.flows.scheduling.fixed_schedule_repair_service import (
    requires_fixed_schedule_repair,
)
from agents.support.nodes.academic_agent.context import build_agent_context
from agents.support.nodes.academic_agent.tools import extract_tool_state_updates, make_tools
from agents.support.nodes.manage_fixed_schedule.node import manage_fixed_schedule as _manage_fixed_schedule
from agents.support.nodes.renew_fixed_schedule.node import renew_fixed_schedule as _renew_fixed_schedule
from agents.support.nodes.repair_fixed_schedule.node import repair_fixed_schedule as _repair_fixed_schedule
from agents.support.nodes.request_replan.node import request_replan as _request_replan
from agents.support.nodes.utils import append_message, detect_new_input, get_last_user_images
from agents.support.state import AgentState


def academic_agent(state: AgentState) -> dict:
    """Despacha el turno: mantenimiento determinista o agente ReAct en modo running."""
    conversation = state.conversation_state
    phase = conversation.phase

    # 1. Dispatch basado en fase para sub-flujos de mantenimiento.
    #    Estos flujos son multi-turno con diálogo estructurado.
    if phase == "schedule_renewal":
        return _renew_fixed_schedule(state)
    if phase == "schedule_repair":
        return _repair_fixed_schedule(state)
    if phase == "fixed_schedule_management":
        return _dispatch_and_maybe_chain_replan(state, _manage_fixed_schedule)

    # 2. Guard: esperar nuevo input del usuario antes de procesar.
    if _should_wait(state):
        return {}

    # 3. Triggers proactivos de mantenimiento.
    if requires_fixed_schedule_renewal(state):
        return _renew_fixed_schedule(state)
    if requires_fixed_schedule_repair(state):
        return _repair_fixed_schedule(state)

    # 4. Replan activo iniciado por update_study_plan en turno anterior.
    #    Cuando la tool propone un plan (status="proposed"), el siguiente
    #    mensaje del usuario se redirige aquí para confirmación o rechazo.
    replan = state.replan
    if replan.trigger and replan.status == "proposed":
        return _request_replan(state)

    # 5. Obtener nuevo input del usuario.
    has_new_input, last_text, current_count = detect_new_input(
        conversation.messages,
        conversation.user_message_count,
        conversation.awaiting_user_input,
        conversation.last_user_text,
    )
    if not has_new_input:
        return {"awaiting_user_input": True}

    # 6. Detectar imágenes en el último mensaje del usuario.
    #    - data URLs (Studio) → ya fueron reemplazadas por IMAGE_RECEIVED_MARKER en el reducer.
    #    - Rutas locales (WhatsApp) → sobreviven al reducer y se procesan aquí con visión.
    from utils.media_artifacts import IMAGE_RECEIVED_MARKER
    from integrations.ai._llm_impl import maybe_get_llm
    from langchain_core.messages import HumanMessage
    from langgraph.prebuilt import create_react_agent

    last_images = get_last_user_images(list(state.messages or []))
    has_image_marker = IMAGE_RECEIVED_MARKER in (last_text or "")

    # 6a. Imagen enviada desde Studio (data URL stripeada) → fallback sin visión.
    if has_image_marker and not last_images:
        return {
            "messages": append_message(
                list(state.messages or []),
                "assistant",
                "Recibí una imagen 📷. Por ahora puedo ayudarte mejor si me describes qué contiene: "
                "¿es un horario, una actividad, una entrega, un parcial u otro asunto académico?",
            ),
            "user_message_count": current_count,
            "last_user_text": last_text,
            "awaiting_user_input": True,
            "phase": "running",
        }

    # 7. Agente ReAct: el LLM razona y decide qué tools invocar.
    llm = maybe_get_llm(temperature=0.0)
    if llm is None:
        return {
            "messages": append_message(
                list(state.messages or []),
                "assistant",
                "Lo siento, el servicio de IA no está disponible en este momento. Por favor intenta más tarde.",
            ),
            "user_message_count": current_count,
            "last_user_text": last_text,
            "awaiting_user_input": True,
            "phase": "running",
        }

    tools = make_tools(state)
    system_context = build_agent_context(state)
    react_agent = create_react_agent(model=llm, tools=tools, prompt=system_context, checkpointer=False)

    # Construir mensaje para el agente: multimodal si hay imágenes reales (WhatsApp).
    human_msg = _build_human_message(last_text, last_images)
    recent_history = _build_recent_history(list(state.messages or []))
    result = react_agent.invoke({"messages": [*recent_history, human_msg]})

    tool_updates = extract_tool_state_updates(result)
    final_message = result["messages"][-1].content

    return_dict: dict = {
        "messages": append_message(list(state.messages or []), "assistant", final_message),
        "user_message_count": current_count,
        "last_user_text": last_text,
        "awaiting_user_input": True,
        "phase": "running",
        **tool_updates,
    }

    return return_dict


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _dispatch_and_maybe_chain_replan(state: AgentState, handler) -> dict:
    """Ejecuta handler determinista y encadena replan si el resultado lo activa."""
    result = handler(state)
    return _maybe_chain_replan(state, result)


def _maybe_chain_replan(state: AgentState, result: dict) -> dict:
    """Si el resultado no espera input y hay un replan pendiente, lo encadena."""
    if result.get("awaiting_user_input", True):
        return result
    if _pending_replan_in(state, result):
        merged = state.model_copy(
            update={k: v for k, v in result.items() if k in state.model_fields}
        )
        replan_result = _request_replan(merged)
        return {**result, **replan_result}
    return result


def _pending_replan_in(state: AgentState, update: dict) -> bool:
    """Verifica si el update activa un candidato de replanificación."""
    replan_raw = update.get("replan")
    if replan_raw is None:
        repl = state.planning_state.replan
        trigger = repl.trigger
        change_req = repl.change_request
        status = repl.status
        proposal = repl.active_proposal
    else:
        rd = dict(replan_raw) if isinstance(replan_raw, dict) else {}
        trigger = rd.get("trigger")
        change_req = rd.get("change_request")
        status = rd.get("status")
        proposal = rd.get("active_proposal")

    plan_raw = update.get("study_plan") or {}
    plan_events = (
        dict(plan_raw).get("plan_events") if isinstance(plan_raw, dict) else None
    )
    if plan_events is None:
        plan_events = state.planning_state.study_plan.plan_events
    has_plan = bool(plan_events)

    return bool(
        ((trigger or change_req) and has_plan)
        or (status == "proposed" and proposal)
    )


def _should_wait(state: AgentState) -> bool:
    """True cuando el grafo debe detenerse esperando nuevo input del usuario."""
    conversation = state.conversation_state
    has_new, _, _ = detect_new_input(
        conversation.messages,
        conversation.user_message_count,
        conversation.awaiting_user_input,
        conversation.last_user_text,
    )
    return bool(conversation.awaiting_user_input and not has_new)


def _build_recent_history(messages: list, max_pairs: int = 5) -> list:
    """Extrae los últimos N pares Human/AI del historial para dar contexto al ReAct agent.

    Solo incluye HumanMessage y AIMessage — descarta ToolMessages y SystemMessages.
    Elimina contenido de imagen de mensajes anteriores para no inflar el contexto de tokens.
    El último HumanMessage se excluye porque ya se pasa por separado como human_msg.
    """
    from langchain_core.messages import AIMessage, HumanMessage
    from utils.media_artifacts import IMAGE_RECEIVED_MARKER

    conversation: list = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            content = msg.content
            if isinstance(content, list):
                text = " ".join(
                    p.get("text", "")
                    for p in content
                    if isinstance(p, dict) and p.get("type") == "text"
                ).strip()
                if text:
                    conversation.append(HumanMessage(content=text))
            elif isinstance(content, str):
                clean = content.replace(IMAGE_RECEIVED_MARKER, "").strip()
                if clean:
                    conversation.append(HumanMessage(content=clean))
        elif isinstance(msg, AIMessage):
            text = str(msg.content or "").strip()
            if text:
                conversation.append(msg)

    # El último HumanMessage es el turno actual — ya se pasa como human_msg.
    if conversation and isinstance(conversation[-1], HumanMessage):
        conversation = conversation[:-1]

    return conversation[-(max_pairs * 2):]


def _build_human_message(text: str, image_paths: list[str]):
    """Construye HumanMessage: texto plano si no hay imágenes, multimodal si las hay."""
    from integrations.ai._llm_impl import load_image_as_data_url
    from langchain_core.messages import HumanMessage
    from utils.media_artifacts import IMAGE_RECEIVED_MARKER

    if not image_paths:
        return HumanMessage(content=text or "")

    content: list[dict] = []
    clean_text = (text or "").replace(IMAGE_RECEIVED_MARKER, "").strip()
    if clean_text:
        content.append({"type": "text", "text": clean_text})

    for path in image_paths:
        data_url = load_image_as_data_url(path)
        if data_url:
            content.append({"type": "image_url", "image_url": {"url": data_url}})

    if not content:
        content.append({
            "type": "text",
            "text": "El estudiante envió una imagen sin texto. Analízala y ofrece apoyo académico relevante.",
        })

    return HumanMessage(content=content)


__all__ = ["academic_agent"]
