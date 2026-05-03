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
    if tool_updates:
        from services.planning import reconcile_react_tool_updates
        tool_updates = reconcile_react_tool_updates(state, tool_updates)
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

    if "academic_activities" in tool_updates:
        _persist_activities_after_tool_update(state, return_dict)
        reminder_update = _sync_activity_reminders_after_tool_update(state, return_dict)
        if reminder_update:
            return_dict["reminders"] = reminder_update

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
            text = _text_only_message_content(msg.content, image_marker=IMAGE_RECEIVED_MARKER)
            if text:
                conversation.append(HumanMessage(content=text))
        elif isinstance(msg, AIMessage):
            text = _text_only_message_content(msg.content, image_marker=IMAGE_RECEIVED_MARKER)
            if text:
                conversation.append(AIMessage(content=text))

    # El último HumanMessage es el turno actual — ya se pasa como human_msg.
    if conversation and isinstance(conversation[-1], HumanMessage):
        conversation = conversation[:-1]

    return conversation[-(max_pairs * 2):]


def _text_only_message_content(content: object, *, image_marker: str) -> str:
    """Extrae solo texto de contenido multimodal antes de reenviarlo al LLM."""

    if isinstance(content, str):
        return content.replace(image_marker, "").strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                clean_item = item.replace(image_marker, "").strip()
                if clean_item:
                    parts.append(clean_item)
            elif isinstance(item, dict) and item.get("type") == "text":
                clean_item = str(item.get("text") or "").replace(image_marker, "").strip()
                if clean_item:
                    parts.append(clean_item)
        return " ".join(parts).strip()
    return ""


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


_ACTIVITY_COMPARE_FIELDS = (
    "subject_name",
    "activity_type",
    "activity_title",
    "due_date",
    "due_time",
    "estimated_effort_minutes",
    "priority_level",
    "difficulty_level",
    "status",
    "todo_task_id",
)


def _activity_snapshot_equal(a, b) -> bool:
    return all(getattr(a, f, None) == getattr(b, f, None) for f in _ACTIVITY_COMPARE_FIELDS)


def _persist_activities_after_tool_update(state: AgentState, update: dict) -> None:
    """Persiste a DB las actividades que el ciclo ReAct creó o modificó.

    Compara el snapshot anterior (estado entrante) con la lista actualizada para
    persistir solo las actividades nuevas o con cambios, evitando writes innecesarios.
    Actualiza update["academic_activities"] in-place con los IDs de persistencia.
    """
    student_id = getattr(state.student_profile, "persisted_student_id", None)
    if not student_id:
        return

    raw_list = update.get("academic_activities")
    if not raw_list:
        return

    from agents.support.dependencies import get_academic_activity_persistence_service
    from schemas.planning import AcademicActivity

    try:
        service = get_academic_activity_persistence_service()
    except Exception:
        return

    current_by_id: dict[str, AcademicActivity] = {
        a.activity_id: a
        for a in (state.academic_activities or [])
        if hasattr(a, "activity_id")
    }

    persisted_list: list[dict] = []
    for raw in raw_list:
        try:
            act = AcademicActivity.model_validate(raw) if isinstance(raw, dict) else raw
        except Exception:
            persisted_list.append(raw if isinstance(raw, dict) else raw.model_dump())
            continue

        current = current_by_id.get(act.activity_id)
        if current is not None and _activity_snapshot_equal(current, act):
            persisted_list.append(act.model_dump())
            continue

        try:
            result = service.upsert_activity(student_id=int(student_id), activity=act)
        except Exception:
            persisted_list.append(act.model_dump())
            continue

        if result.persisted and result.activity is not None:
            persisted_list.append(result.activity.model_dump())
        else:
            persisted_list.append(act.model_dump())

    update["academic_activities"] = persisted_list


def _sync_activity_reminders_after_tool_update(
    state: AgentState,
    update: dict,
) -> dict[str, object] | None:
    """Agenda recordatorios durables cuando ReAct cambia actividades académicas."""

    student_id = getattr(state.student_profile, "persisted_student_id", None)
    if not student_id:
        return None

    try:
        from agents.support.dependencies import get_reminders_service
        from services.reminders import update_reminders_state

        current_reminders = update.get("reminders", state.reminders)
        service = get_reminders_service()
        result = service.sync_reminders_for_academic_activities(
            student_id=int(student_id),
            activities=list(update.get("academic_activities", state.academic_activities)),
            reminders_state=current_reminders,
            timezone=str(update.get("timezone") or state.timezone or "America/Bogota"),
        )
    except Exception as exc:
        from services.reminders import update_reminders_state

        return update_reminders_state(
            update.get("reminders", state.reminders),
            last_dispatch_error=f"academic_activity_reminders_service_unavailable:{exc}",
        )

    if not result.synced:
        return update_reminders_state(
            current_reminders,
            last_dispatch_error=result.error_code or "academic_activity_reminders_sync_error",
        )

    return update_reminders_state(
        current_reminders,
        persisted_policy_ids=result.persisted_policy_ids,
        policy_count=result.policy_count,
        schedulable_instance_count=result.schedulable_instance_count,
        created_dispatch_count=result.created_dispatch_count,
        canceled_dispatch_count=result.canceled_dispatch_count,
        last_dispatch_error=None,
        last_sync_at=result.synced_at,
    )


__all__ = ["academic_agent"]
