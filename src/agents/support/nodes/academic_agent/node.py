"""Nodo único del modo operativo — agente ReAct autónomo.

Arquitectura:
  - Fases de mantenimiento (schedule_renewal, schedule_repair): handlers
    deterministas de renovación/reparación de horario (multi-turno estructurado).
  - Fase running: create_react_agent con 15 tools. El LLM decide qué hacer,
    en qué orden y qué combinar — incluyendo gestión directa del horario fijo
    (add_schedule_block / update_schedule_block / delete_schedule_block).

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
from agents.support.nodes.academic_agent.context import _STATIC_INSTRUCTIONS, build_dynamic_context
from agents.support.nodes.academic_agent.tools import extract_tool_state_updates, make_tools
from agents.support.nodes.renew_fixed_schedule.node import renew_fixed_schedule as _renew_fixed_schedule
from agents.support.nodes.repair_fixed_schedule.node import repair_fixed_schedule as _repair_fixed_schedule
from agents.support.nodes.request_replan.node import request_replan as _request_replan
from agents.support.nodes.utils import append_message, detect_new_input
from agents.support.state import AgentState

_MAX_PERSISTED_MESSAGES: int = 20  # ~10 Human+AI pairs; older messages are trimmed from the checkpoint


def academic_agent(state: AgentState) -> dict:
    """Despacha el turno: mantenimiento determinista o agente ReAct en modo running."""
    conversation = state.conversation_state
    phase = conversation.phase

    # 1. Dispatch basado en fase para sub-flujos de mantenimiento.
    #    Estos flujos son multi-turno con diálogo estructurado (renovación/reparación).
    #    La gestión del horario fijo (add/update/delete de bloques) ya NO usa flujo
    #    determinista — el agente ReAct la maneja directamente con sus tools.
    if phase == "schedule_renewal":
        return _renew_fixed_schedule(state)
    if phase == "schedule_repair":
        return _repair_fixed_schedule(state)

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
    from langchain_core.messages import HumanMessage, SystemMessage
    from langgraph.prebuilt import create_react_agent

    last_images = list(state.last_user_images or [])
    has_image_marker = IMAGE_RECEIVED_MARKER in (last_text or "")

    # 6a. Imagen enviada desde Studio (data URL stripeada) → fallback sin visión.
    if has_image_marker and not last_images:
        return {
            "messages": _capped_messages_update(
                list(state.messages or []),
                "Recibí una imagen 📷. Por ahora puedo ayudarte mejor si me describes qué contiene: "
                "¿es un horario, una actividad, una entrega, un parcial u otro asunto académico?",
            ),
            "last_user_images": [],
            "user_message_count": current_count,
            "last_user_text": last_text,
            "awaiting_user_input": True,
            "phase": "running",
        }

    # 7. Agente ReAct: el LLM razona y decide qué tools invocar.
    llm = maybe_get_llm(temperature=0.0)
    if llm is None:
        return {
            "messages": _capped_messages_update(
                list(state.messages or []),
                "Lo siento, el servicio de IA no está disponible en este momento. Por favor intenta más tarde.",
            ),
            "last_user_images": [],
            "user_message_count": current_count,
            "last_user_text": last_text,
            "awaiting_user_input": True,
            "phase": "running",
        }

    tools = make_tools(state)
    # _STATIC_INSTRUCTIONS es constante — Azure OpenAI lo cachea junto con las tool
    # definitions (~1450 tokens estables). Solo build_dynamic_context se recalcula
    # cada turno (~400 tokens), reduciendo el procesamiento por invocación al LLM.
    react_agent = create_react_agent(model=llm, tools=tools, prompt=_STATIC_INSTRUCTIONS, checkpointer=False)

    # Construir mensaje para el agente: multimodal si hay imágenes reales (WhatsApp).
    human_msg = _build_human_message(last_text, last_images)
    recent_history = _build_recent_history(list(state.messages or []))
    dynamic_msg = SystemMessage(content=build_dynamic_context(state))
    try:
        result = react_agent.invoke({"messages": [dynamic_msg, *recent_history, human_msg]})
    except Exception as exc:
        # Si Azure rechaza la imagen (base64 inválido, formato no soportado, etc.)
        # y había imágenes en el turno, reintentar con solo texto para no bloquear al estudiante.
        if last_images and _is_image_api_error(exc):
            human_msg = _build_human_message(last_text, [])
            result = react_agent.invoke({"messages": [dynamic_msg, *recent_history, human_msg]})
        else:
            raise

    tool_updates = extract_tool_state_updates(result)
    final_message = result["messages"][-1].content

    return_dict: dict = {
        "messages": _capped_messages_update(list(state.messages or []), final_message),
        "last_user_images": [],
        "user_message_count": current_count,
        "last_user_text": last_text,
        "awaiting_user_input": True,
        "phase": "running",
        **tool_updates,
    }

    if "subjects" in tool_updates:
        from agents.support.flows.planning.persistence_support import persist_planning_snapshot_for_update
        return_dict = persist_planning_snapshot_for_update(state, return_dict)

    return return_dict


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

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


def _capped_messages_update(current: list, content: str) -> list:
    """Returns the reducer payload: new AIMessage plus RemoveMessage ops for overflow.

    Keeps at most _MAX_PERSISTED_MESSAGES in state.  Messages without an id (e.g.
    those constructed directly in unit tests) are skipped in the removal list so
    the reducer never receives a RemoveMessage with id=None.
    """
    from langchain_core.messages import AIMessage
    from langchain_core.messages import RemoveMessage

    from utils.message_sanitizer import sanitize_message_content

    new_msg = AIMessage(content=sanitize_message_content(content))
    overflow = len(current) + 1 - _MAX_PERSISTED_MESSAGES
    if overflow <= 0:
        return [new_msg]

    removals = [
        RemoveMessage(id=m.id)
        for m in current[:overflow]
        if getattr(m, "id", None)
    ]
    return removals + [new_msg]


def _is_image_api_error(exc: Exception) -> bool:
    """True si el error de Azure/OpenAI es por imagen inválida o no soportada."""
    err = str(exc).lower()
    return (
        "invalid_base64" in err
        or "invalid base64" in err
        or "image_url" in err
        or "image url" in err
        or "unsupported image" in err
    )


__all__ = ["academic_agent"]
