"""Nodo único del modo operativo — agente ReAct autónomo.

Arquitectura:
  - Fases de mantenimiento (schedule_renewal, schedule_repair): handlers
    deterministas de renovación/reparación de horario (multi-turno estructurado).
  - Fase running: create_react_agent con tools especializadas. El LLM decide qué hacer,
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
from langchain_core.runnables import RunnableConfig

_MAX_PERSISTED_MESSAGES: int = 20  # ~10 Human+AI pairs; older messages are trimmed from the checkpoint


def academic_agent(state: AgentState, config: RunnableConfig | None = None) -> dict:
    """Despacha el turno: mantenimiento determinista o agente ReAct en modo running."""
    whatsapp_recipient_id: str | None = (
        str(((config or {}).get("configurable") or {}).get("thread_id") or "").strip() or None
    )
    state, hydration_update = _hydrate_react_runtime_state(state)
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
    from langchain_core.messages import HumanMessage, SystemMessage
    from langgraph.prebuilt import create_react_agent
    from services.ai_runtime import maybe_get_llm

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
    final_message_content = _empty_react_response_fallback(
        result["messages"][-1].content,
        tool_updates=tool_updates,
    )
    final_message = _final_message_content_with_schedule_preview(
        state,
        final_message_content,
        tool_updates,
    )

    return_dict: dict = {
        "messages": _capped_messages_update(list(state.messages or []), final_message),
        "last_user_images": [],
        "user_message_count": current_count,
        "last_user_text": last_text,
        "awaiting_user_input": True,
        "phase": "running",
        **hydration_update,
        **tool_updates,
    }

    if "subjects" in tool_updates:
        from agents.support.flows.planning.persistence_support import persist_planning_snapshot_for_update
        return_dict = persist_planning_snapshot_for_update(state, return_dict)

    if "academic_activities" in tool_updates:
        _persist_activities_after_tool_update(state, return_dict)
        todo_update = _sync_academic_activities_to_todo_after_tool_update(state, return_dict)
        if todo_update:
            if "operational_note" in todo_update:
                _append_operational_note(return_dict, str(todo_update["operational_note"]))
            if "academic_activities" in todo_update:
                pre_todo_snapshot = list(return_dict.get("academic_activities") or [])
                # Merge por activity_id: actualiza solo los campos de los registros
                # devueltos por el sync (p.ej. todo_task_id) sin descartar actividades
                # que el servicio no incluyó en synced_activities (lista parcial).
                todo_by_id: dict[str, dict] = {}
                for raw in todo_update["academic_activities"]:
                    act_id = raw.get("activity_id") if isinstance(raw, dict) else getattr(raw, "activity_id", None)
                    if act_id:
                        todo_by_id[str(act_id)] = raw if isinstance(raw, dict) else raw.model_dump()
                merged_activities = []
                for raw in pre_todo_snapshot:
                    act_id = raw.get("activity_id") if isinstance(raw, dict) else getattr(raw, "activity_id", None)
                    merged_activities.append(
                        todo_by_id.get(str(act_id), raw) if act_id else raw
                    )
                return_dict["academic_activities"] = merged_activities
                _persist_todo_task_id_updates(state, return_dict, pre_todo_snapshot)
        reminder_update = _sync_activity_reminders_after_tool_update(state, return_dict, whatsapp_recipient_id=whatsapp_recipient_id)
        if reminder_update:
            return_dict["reminders"] = reminder_update

    # La materialización y sincronización del plan con Outlook Calendar se hace ÚNICAMENTE
    # cuando el estudiante confirma explícitamente las sesiones propuestas (via sync_plan_to_calendar).
    # No auto-sincronizar aquí evita que el plan se guarde en Outlook sin confirmación del estudiante.

    return return_dict


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _hydrate_react_runtime_state(state: AgentState) -> tuple[AgentState, dict]:
    """Carga datos durables críticos antes de construir contexto/tools ReAct."""

    student_id = getattr(state.student_profile, "persisted_student_id", None)
    if not student_id:
        return state, {}

    update: dict[str, object] = {}

    try:
        from agents.support.dependencies import get_academic_activity_persistence_service
        from services.planning.academic_activity_service import coerce_academic_activities

        result = get_academic_activity_persistence_service().list_activities(
            student_id=int(student_id),
            include_deleted=False,
        )
        if result.loaded and result.activities:
            merged_activities = _merge_academic_activities(
                durable=result.activities,
                local=coerce_academic_activities(list(state.academic_activities or [])),
            )
            update["academic_activities"] = [
                activity.model_dump(mode="python") for activity in merged_activities
            ]
    except Exception:
        pass

    needs_planning = (
        not list(state.subjects or [])
        or not list(state.study_plan.plan_events or [])
        or not getattr(state.study_plan, "persisted_profile_id", None)
    )
    if needs_planning:
        try:
            from agents.support.dependencies import get_study_planning_persistence_service

            result = get_study_planning_persistence_service().load_current_snapshot(
                student_id=int(student_id)
            )
            if result.loaded:
                if result.subjects and (
                    not list(state.subjects or [])
                    or _should_replace_versioned_payload(
                        local_id=getattr(state.priorities, "persisted_profile_id", None),
                        local_version=getattr(state.priorities, "version_number", None),
                        durable_id=result.priority_profile_id,
                        durable_version=result.priority_version_number,
                    )
                ):
                    update["subjects"] = [
                        subject.model_dump(mode="python") for subject in result.subjects
                    ]
                if result.study_plan is not None and (
                    _should_replace_versioned_payload(
                        local_id=getattr(state.study_plan, "persisted_profile_id", None),
                        local_version=getattr(state.study_plan, "version_number", None),
                        durable_id=result.study_plan_profile_id,
                        durable_version=result.study_plan_version_number,
                    )
                ):
                    update["study_plan"] = result.study_plan.model_dump(mode="python")
                if result.priorities_state is not None and not getattr(
                    state.priorities,
                    "persisted_profile_id",
                    None,
                ):
                    update["priorities"] = result.priorities_state.model_dump(mode="python")
        except Exception:
            pass

    if not update:
        return state, {}
    try:
        hydrated = AgentState(**{**state.model_dump(mode="python"), **update})
    except Exception:
        return state, {}
    return hydrated, update


def _merge_academic_activities(*, durable: list, local: list) -> list:
    """Une actividades persistidas y locales; BD gana si ya conoce la actividad."""

    merged = {}
    for activity in local:
        activity_id = getattr(activity, "activity_id", None)
        if activity_id:
            merged.setdefault(activity_id, activity)
    for activity in durable:
        activity_id = getattr(activity, "activity_id", None)
        if activity_id:
            merged[activity_id] = activity
    return list(merged.values())


def _should_replace_versioned_payload(
    *,
    local_id: int | None,
    local_version: int | None,
    durable_id: int | None,
    durable_version: int | None,
) -> bool:
    if durable_id is None:
        return False
    if local_id is None:
        return True
    if int(local_id) != int(durable_id):
        return True
    if durable_version is not None and local_version is not None:
        return int(durable_version) > int(local_version)
    return False


def _final_message_content_with_schedule_preview(
    state: AgentState,
    final_message: object,
    tool_updates: dict,
) -> object:
    """Adjunta imagen renderizada cuando el ReAct modificó el horario fijo."""

    if "schedule" not in tool_updates:
        return final_message
    try:
        from agents.support.scheduling.render import build_rendered_schedule_message_content
        from services.scheduling.models import ensure_weekly_block

        schedule = tool_updates.get("schedule") or {}
        raw_blocks = schedule.get("blocks", []) if isinstance(schedule, dict) else []
        blocks = []
        for raw_block in raw_blocks:
            block = ensure_weekly_block(raw_block)
            if getattr(block, "is_active", True):
                blocks.append(block)
        if not blocks:
            return final_message
        content, _ = build_rendered_schedule_message_content(
            str(final_message or ""),
            blocks,
            timezone_name=str(state.timezone or "America/Bogota"),
        )
        return content
    except Exception:
        return final_message


def _empty_react_response_fallback(
    final_message: object,
    *,
    tool_updates: dict | None = None,
) -> object:
    """Evita dejar al estudiante sin respuesta si el ReAct retorna contenido vacío."""

    if not _is_empty_message_content(final_message):
        return final_message
    if tool_updates:
        return (
            "Listo. Procesé tu solicitud, pero no pude generar una explicación clara. "
            "¿Qué quieres revisar ahora?"
        )
    return (
        "Tuve un problema generando la respuesta. "
        "¿Me puedes repetir tu solicitud o darme un poco más de detalle?"
    )


def _is_empty_message_content(content: object) -> bool:
    if content is None:
        return True
    if isinstance(content, str):
        return not content.strip()
    if isinstance(content, list):
        for item in content:
            if isinstance(item, str) and item.strip():
                return False
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    return False
                if item.get("type") in {"image_url", "image"}:
                    return False
        return True
    return False


def _sanitize_microsoft_sync_error(detail: str | None) -> str:
    """Convierte un error técnico de Microsoft en un mensaje genérico para el usuario.

    Oculta AADSTS codes, Correlation IDs y trazas de stack que no son relevantes
    para el estudiante y pueden generar confusión o alarma innecesaria.
    """
    import re

    if not detail:
        return "error de conexión con Microsoft"
    if re.search(r"AADSTS\d+", detail):
        return "error de autenticación con Microsoft"
    if re.search(r"(CorrelationId|TraceId|Timestamp|trace_id|correlation_id)", detail, re.IGNORECASE):
        return "error de conexión con Microsoft"
    # Truncar mensajes muy largos para no exponer detalles técnicos
    if len(detail) > 120:
        return "error de conexión con Microsoft"
    return detail


def _append_operational_note(update: dict, note: str) -> None:
    """Agrega una nota breve al último mensaje del turno sin rehacer el ReAct."""

    if not note.strip():
        return
    from langchain_core.messages import AIMessage
    from utils.message_sanitizer import sanitize_message_content

    messages = list(update.get("messages") or [])
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if not isinstance(message, AIMessage):
            continue
        content = message.content
        if isinstance(content, str):
            new_content = f"{content}\n\n{note}"
        elif isinstance(content, list):
            new_content = list(content)
            for block in new_content:
                if isinstance(block, dict) and block.get("type") == "text":
                    block["text"] = f"{block.get('text') or ''}\n\n{note}".strip()
                    break
            else:
                new_content.insert(0, {"type": "text", "text": note})
        else:
            new_content = note
        messages[index] = message.model_copy(update={"content": sanitize_message_content(new_content)})
        update["messages"] = messages
        return
    messages.append(AIMessage(content=sanitize_message_content(note)))
    update["messages"] = messages


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
    from langchain_core.messages import HumanMessage
    from services.ai_runtime import load_image_as_data_url
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


def _persist_todo_task_id_updates(
    state: AgentState,
    update: dict,
    pre_sync_snapshot: list,
) -> None:
    """Persiste cambios derivados de la sincronización con To Do.

    Evita reescribir toda la lista después de una persistencia previa y guarda
    solo los campos que To Do puede cambiar: id externo, estado completado,
    título o fecha importada con confirmación.
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

    pre_sync_values: dict[str, tuple[str | None, str | None, str | None, str | None]] = {}
    for raw in pre_sync_snapshot:
        try:
            act = AcademicActivity.model_validate(raw) if isinstance(raw, dict) else raw
            pre_sync_values[act.activity_id] = (
                getattr(act, "todo_task_id", None),
                getattr(act, "status", None),
                getattr(act, "activity_title", None),
                getattr(act, "due_date", None),
            )
        except Exception:
            pass

    persisted_list: list[dict] = []
    for raw in raw_list:
        try:
            act = AcademicActivity.model_validate(raw) if isinstance(raw, dict) else raw
        except Exception:
            persisted_list.append(raw if isinstance(raw, dict) else raw.model_dump())
            continue

        current_values = (
            getattr(act, "todo_task_id", None),
            getattr(act, "status", None),
            getattr(act, "activity_title", None),
            getattr(act, "due_date", None),
        )
        pre_values = pre_sync_values.get(act.activity_id)

        if pre_values == current_values:
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
    *,
    whatsapp_recipient_id: str | None = None,
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
            whatsapp_recipient_id=whatsapp_recipient_id,
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


def _sync_academic_activities_to_todo_after_tool_update(
    state: AgentState,
    update: dict,
) -> dict[str, object] | None:
    """Sincroniza To Do después de cambios ReAct en actividades académicas."""

    student_id = getattr(state.student_profile, "persisted_student_id", None)
    raw_activities = update.get("academic_activities")
    if not student_id or not raw_activities:
        return None

    try:
        from agents.support.dependencies import get_microsoft_todo_sync_service
        from services.planning.academic_activity_service import coerce_academic_activities

        service = get_microsoft_todo_sync_service()
        calendar_state = update.get("calendar", state.calendar)
        task_list_id = (
            calendar_state.get("todo_task_list_id")
            if isinstance(calendar_state, dict)
            else getattr(calendar_state, "todo_task_list_id", None)
        )
        activities = coerce_academic_activities(list(raw_activities))
        result = service.sync_academic_activities_to_todo(
            student_id=int(student_id),
            task_list_id=task_list_id,
            activities=activities,
        )
    except Exception:
        return None

    if getattr(result, "requires_confirmation", False):
        update_payload: dict[str, object] = {
            "operational_note": (
                "Nota operativa: detecté cambios manuales en Microsoft To Do. "
                "No los sobrescribí. Pregunta al estudiante si quiere importarlos "
                "al asistente o restaurar To Do con la información del asistente."
            )
        }
        if getattr(result, "synced_activities", None):
            update_payload["academic_activities"] = [
                activity.model_dump(mode="python")
                for activity in result.synced_activities
            ]
        return update_payload

    if not getattr(result, "synced", False):
        raw_detail = getattr(result, "detail", None) or getattr(result, "error_code", None)
        safe_detail = _sanitize_microsoft_sync_error(raw_detail)
        return {
            "operational_note": (
                "Nota operativa: guardé la actividad localmente, "
                f"pero no pude sincronizar Microsoft To Do ({safe_detail})."
            )
        }
    if not getattr(result, "synced_activities", None):
        return None

    return {
        "academic_activities": [
            activity.model_dump(mode="python")
            for activity in result.synced_activities
        ]
    }


def _materialize_and_sync_study_plan_after_tool_update(
    state: AgentState,
    update: dict,
) -> dict[str, object] | None:
    """Materializa sesiones y sincroniza Outlook si el estudiante tiene Microsoft activo."""

    student_id = getattr(state.student_profile, "persisted_student_id", None)
    if not student_id:
        return None

    calendar_state = update.get("calendar", state.calendar)
    calendar_data = (
        dict(calendar_state)
        if isinstance(calendar_state, dict)
        else calendar_state.model_dump(mode="python")
        if hasattr(calendar_state, "model_dump")
        else {}
    )
    microsoft_likely_connected = bool(
        calendar_data.get("authorized")
        or calendar_data.get("provider") == "outlook"
        or calendar_data.get("calendar_id")
    )
    if not microsoft_likely_connected:
        return None

    try:
        from agents.support.dependencies import (
            get_outlook_calendar_sync_service,
            get_study_plan_materialization_service,
        )
        from services.planning import ensure_study_plan_state, update_study_plan_state

        study_plan = ensure_study_plan_state(update.get("study_plan", state.study_plan))
        if not study_plan.plan_events or not study_plan.persisted_profile_id:
            return None

        materialization = get_study_plan_materialization_service().materialize_plan_instances(
            student_id=int(student_id),
            study_plan_profile_id=study_plan.persisted_profile_id,
            study_plan=study_plan,
            timezone=str(update.get("timezone") or state.timezone or "America/Bogota"),
        )
        merged: dict[str, object] = {}
        if materialization.materialized:
            merged["study_plan"] = update_study_plan_state(
                study_plan,
                materialized_instance_count=materialization.materialized_instance_count,
                superseded_instance_count=materialization.superseded_instance_count,
                materialized_horizon_days=materialization.horizon_days,
                materialized_through_date=materialization.materialized_through_date,
                materialization_error=None,
            )
        else:
            merged["study_plan"] = update_study_plan_state(
                study_plan,
                materialization_error=materialization.error_code or "study_plan_materialization_error",
                materialized_horizon_days=materialization.horizon_days,
                materialized_through_date=materialization.materialized_through_date,
            )
            raw_mat_detail = materialization.detail or materialization.error_code
            safe_mat_detail = _sanitize_microsoft_sync_error(raw_mat_detail)
            merged["operational_note"] = (
                "Nota operativa: guardé el plan localmente, "
                f"pero no pude preparar las sesiones fechadas para Outlook ({safe_mat_detail})."
            )
            return merged

        sync = get_outlook_calendar_sync_service().sync_student_calendar(
            student_id=int(student_id),
            calendar_state=calendar_data,
            calendar_id=calendar_data.get("calendar_id"),
            study_plan_profile_id=study_plan.persisted_profile_id,
        )
        if sync.synced:
            merged["calendar"] = {
                **calendar_data,
                "provider": "outlook",
                "authorized": True,
                "synced_event_map": dict(sync.synced_event_map),
            }
        else:
            raw_sync_detail = sync.detail or sync.error_code
            safe_sync_detail = _sanitize_microsoft_sync_error(raw_sync_detail)
            merged["operational_note"] = (
                "Nota operativa: guardé el plan localmente, "
                f"pero no pude sincronizar las sesiones en Outlook Calendar ({safe_sync_detail})."
            )
        return merged
    except Exception:
        return None


__all__ = ["academic_agent"]
