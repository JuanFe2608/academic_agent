"""Factory de herramientas del agente académico.

Todas las tools son closures creados por make_tools(state) que capturan el
AgentState del turno actual, dándoles acceso a los datos del estudiante sin
exponer state como parámetro visible para el LLM.

Patrón de retorno para tools que modifican estado:
    json.dumps({"result": "<texto para el LLM>", "_state_update": {...}})

extract_tool_state_updates() recoge estas actualizaciones después del ciclo
ReAct y las fusiona en el dict de retorno del nodo academic_agent.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from langchain_core.tools import tool

from agents.support.state import AgentState

_DAYS_ES: dict[str, str] = {
    "monday": "Lunes",
    "tuesday": "Martes",
    "wednesday": "Miércoles",
    "thursday": "Jueves",
    "friday": "Viernes",
    "saturday": "Sábado",
    "sunday": "Domingo",
}

_DAYS_ORDER = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

_VALID_PRIORIDAD: frozenset[str] = frozenset({"alta", "media", "baja"})


def make_tools(state: AgentState) -> list:
    """Crea las 13 herramientas del agente con el estado actual capturado en closure."""
    student_id = _get_student_id(state)

    # ------------------------------------------------------------------ RAG --

    @tool
    def search_study_methods(
        query: str,
        technique_id: str | None = None,
        subject: str | None = None,
        activity_type: str | None = None,
    ) -> str:
        """Busca métodos y estrategias de estudio en la base de conocimiento.
        Úsala cuando el estudiante pregunte cómo estudiar para una materia,
        cómo prepararse para un tipo de evaluación, o qué técnica aplicar.
        technique_id: slug de la técnica (p.ej. pomodoro, feynman, cornell).
        subject: nombre de la materia. activity_type: parcial, tarea, quiz, etc."""
        import dataclasses

        from agents.support.dependencies import get_study_recommendation_service
        from schemas.rag import StudyRecommendationQuery
        from services.study_recommendations import (
            AppliedStudyMethodService,
            build_applied_method_request_from_text,
            format_applied_study_method_for_user,
            is_applied_study_method_message,
        )

        service = get_study_recommendation_service()
        try:
            # Path 1: explica una técnica específica por slug
            if technique_id:
                result = service.explain_technique(
                    technique_id,
                    query_text=query or subject or activity_type,
                )
                return result.answer or "No encontré guía para esa técnica."

            # Path 2: método aplicado paso a paso para una actividad concreta
            if is_applied_study_method_message(query) or activity_type:
                profile_dict = {
                    "weakness_tags": list(state.study_profile.weakness_tags or []),
                    "top_techniques": list(state.study_profile.top_techniques or []),
                }
                request = build_applied_method_request_from_text(query, study_profile=profile_dict)
                if subject or activity_type:
                    request = dataclasses.replace(
                        request,
                        subject_name=subject or request.subject_name,
                        activity_type=activity_type or request.activity_type,
                    )
                applied_result = AppliedStudyMethodService(service).apply_to_activity(request)
                if applied_result.applied:
                    return format_applied_study_method_for_user(applied_result)

            # Path 3: búsqueda general con perfil del estudiante
            rag_result = service.answer_query(
                StudyRecommendationQuery(
                    query_text=query,
                    intent="recommend_technique",
                    top_techniques=list(state.study_profile.top_techniques or []),
                    student_signals=list(state.study_profile.weakness_tags or []),
                    subject_name=subject,
                    activity_type=activity_type,
                )
            )
            if rag_result.confidence != "baja":
                return rag_result.answer

            # Path 4: fallback LLM cuando RAG no tiene fuentes suficientes
            return _llm_study_fallback(query) or rag_result.answer or "No encontré información relevante sobre ese método de estudio."
        except Exception as exc:
            return f"No pude buscar métodos de estudio: {exc}"

    @tool
    def get_technique_guide(
        technique_id: str,
        activity_type: str | None = None,
        available_minutes: int | None = None,
    ) -> str:
        """Obtiene una guía paso a paso de cómo aplicar una técnica de estudio
        específica. Úsala cuando el estudiante ya sabe qué técnica usar y necesita
        instrucciones de ejecución.
        technique_id: slug de la técnica (pomodoro, feynman, cornell, spaced_repetition, etc.).
        activity_type: tipo de evaluación a preparar. available_minutes: tiempo disponible."""
        from agents.support.dependencies import get_study_recommendation_service

        service = get_study_recommendation_service()
        try:
            parts = [p for p in [activity_type, f"{available_minutes}min" if available_minutes else ""] if p]
            query_text = " ".join(parts) or None
            result = service.explain_technique(technique_id, query_text=query_text)
            return result.answer or "No encontré guía para esa técnica."
        except Exception as exc:
            return f"No pude obtener la guía: {exc}"

    # -------------------------------------------------------- Actividades ----

    @tool
    def add_academic_activity(
        subject: str,
        activity_type: str,
        title: str,
        due_date: str,
        priority: str = "media",
        difficulty: int = 3,
    ) -> str:
        """Registra una actividad académica nueva del estudiante.
        activity_type: parcial | quiz | tarea | taller | entrega | exposicion | proyecto.
        due_date: fecha límite en formato YYYY-MM-DD.
        priority: alta | media | baja.
        difficulty: escala 1 (fácil) a 5 (muy difícil).
        Úsala cuando el estudiante mencione cualquier evaluación, entrega o compromiso académico."""
        from services.planning.academic_activity_service import (
            apply_confirmed_academic_activity_operation,
            build_activity_from_slots,
            coerce_academic_activities,
        )

        activities = coerce_academic_activities(list(state.academic_activities))
        try:
            new_act = build_activity_from_slots(
                {
                    "activity_type": activity_type,
                    "subject_name": subject,
                    "activity_title": title,
                    "due_date": due_date,
                    "priority_level": priority,
                    "difficulty_level": difficulty,
                },
                source_text=f"{subject} {activity_type} {title}",
                timezone=state.timezone,
            )
            result = apply_confirmed_academic_activity_operation(
                activities,
                {"operation": "create", "activity": new_act.model_dump()},
                timezone=state.timezone,
                reference_date=date.today(),
            )
            state_update: dict[str, Any] = {
                "academic_activities": [a.model_dump() for a in result.activities],
            }
            if result.replan_required:
                state_update["replan"] = {"trigger": "academic_activity"}
            return json.dumps({"result": result.message or f"Actividad '{title}' registrada para el {due_date}.", "_state_update": state_update})
        except Exception as exc:
            return f"No pude registrar la actividad: {exc}"

    @tool
    def edit_academic_activity(
        activity_reference: str,
        subject: str | None = None,
        activity_type: str | None = None,
        title: str | None = None,
        due_date: str | None = None,
        priority: str | None = None,
        difficulty: int | None = None,
    ) -> str:
        """Edita una actividad académica ya registrada del estudiante.
        activity_reference: descripción para identificar la actividad (materia, tipo o título).
        subject: nuevo nombre de materia (opcional).
        activity_type: nuevo tipo — parcial | quiz | tarea | taller | entrega | exposicion | proyecto (opcional).
        title: nuevo título de la actividad (opcional).
        due_date: nueva fecha límite YYYY-MM-DD (opcional).
        priority: nueva prioridad — alta | media | baja (opcional).
        difficulty: nueva dificultad 1-5 (opcional).
        Úsala cuando el estudiante quiera corregir datos de una actividad ya registrada."""
        from services.planning.academic_activity_service import (
            apply_confirmed_academic_activity_operation,
            coerce_academic_activities,
            match_academic_activities,
        )

        activities = coerce_academic_activities(list(state.academic_activities))
        matches = match_academic_activities(activities, text=activity_reference)
        if not matches:
            return f"No encontré ninguna actividad que coincida con '{activity_reference}'."
        if len(matches) > 1:
            lines = [f"Encontré {len(matches)} actividades que podrían ser esa. Especifica cuál:"]
            for a in matches:
                due_str = f" — vence {a.due_date}" if a.due_date else ""
                lines.append(f"  • [{a.activity_type}] {a.subject_name}: {a.activity_title}{due_str}")
            return "\n".join(lines)
        target = matches[0]
        changes: dict[str, Any] = {}
        if subject is not None:
            changes["subject_name"] = subject
        if activity_type is not None:
            changes["activity_type"] = activity_type
        if title is not None:
            changes["activity_title"] = title
        if due_date is not None:
            changes["due_date"] = due_date
        if priority is not None:
            changes["priority_level"] = priority
        if difficulty is not None:
            changes["difficulty_level"] = difficulty
        if not changes:
            return "No indicaste ningún campo a actualizar."
        try:
            result = apply_confirmed_academic_activity_operation(
                activities,
                {"operation": "update", "activity_id": target.activity_id, "changes": changes},
                timezone=state.timezone,
                reference_date=date.today(),
            )
            state_update: dict[str, Any] = {
                "academic_activities": [a.model_dump() for a in result.activities],
            }
            if result.replan_required:
                state_update["replan"] = {"trigger": "academic_activity"}
            return json.dumps({"result": result.message or "Actividad actualizada.", "_state_update": state_update})
        except Exception as exc:
            return f"No pude actualizar la actividad: {exc}"

    @tool
    def delete_academic_activity(activity_reference: str) -> str:
        """Elimina una actividad académica del estudiante.
        activity_reference: descripción para identificar la actividad (materia, tipo o título).
        Úsala cuando el estudiante diga que canceló una actividad, que fue un registro incorrecto,
        o que ya no necesita hacer seguimiento de esa actividad."""
        from services.planning.academic_activity_service import (
            apply_confirmed_academic_activity_operation,
            coerce_academic_activities,
            match_academic_activities,
        )

        activities = coerce_academic_activities(list(state.academic_activities))
        matches = match_academic_activities(activities, text=activity_reference)
        if not matches:
            return f"No encontré ninguna actividad que coincida con '{activity_reference}'."
        if len(matches) > 1:
            lines = [f"Encontré {len(matches)} actividades. Especifica cuál eliminar:"]
            for a in matches:
                due_str = f" — vence {a.due_date}" if a.due_date else ""
                lines.append(f"  • [{a.activity_type}] {a.subject_name}: {a.activity_title}{due_str}")
            return "\n".join(lines)
        target = matches[0]
        try:
            result = apply_confirmed_academic_activity_operation(
                activities,
                {"operation": "delete", "activity_id": target.activity_id},
                timezone=state.timezone,
                reference_date=date.today(),
            )
            state_update: dict[str, Any] = {
                "academic_activities": [a.model_dump() for a in result.activities],
            }
            if result.replan_required:
                state_update["replan"] = {"trigger": "academic_activity"}
            return json.dumps({"result": result.message or "Actividad eliminada.", "_state_update": state_update})
        except Exception as exc:
            return f"No pude eliminar la actividad: {exc}"

    @tool
    def get_pending_activities(days_ahead: int = 7) -> str:
        """Lista actividades académicas pendientes del estudiante en los próximos N días.
        Úsala cuando el estudiante pregunte qué tiene pendiente, cuáles son sus próximas
        entregas o quiera saber para qué prepararse esta semana."""
        from services.planning.academic_activity_service import active_academic_activities

        activities = active_academic_activities(list(state.academic_activities))
        pending = [a for a in activities if a.status == "pending"]
        if not pending:
            return "No tienes actividades académicas pendientes registradas."
        cutoff = date.today() + timedelta(days=days_ahead)
        upcoming = [
            a for a in pending
            if not a.due_date or date.fromisoformat(a.due_date) <= cutoff
        ]
        if not upcoming:
            return f"No tienes actividades con fecha límite en los próximos {days_ahead} días."
        lines = [f"Tienes {len(upcoming)} actividades pendientes:"]
        for a in sorted(upcoming, key=lambda x: x.due_date or "9999"):
            due_str = f" — vence {a.due_date}" if a.due_date else ""
            pri_str = f" [{a.priority_level}]" if a.priority_level else ""
            lines.append(f"  • [{a.activity_type}] {a.subject_name}: {a.activity_title}{due_str}{pri_str}")
        return "\n".join(lines)

    # -------------------------------------------------------- Plan de estudio -

    @tool
    def get_weekly_plan(week_offset: int = 0) -> str:
        """Obtiene el plan de estudio semanal del estudiante.
        week_offset=0 para la semana actual.
        Úsala cuando el estudiante pida ver su plan, su agenda de estudio o
        cómo tiene distribuida la semana."""
        events = list(state.study_plan.plan_events or [])
        if not events:
            return (
                "No tienes plan de estudio generado aún. "
                "Puedo generarlo si me indicas tus prioridades y horario disponible."
            )
        by_day: dict[str, list[str]] = {}
        for ev in events:
            day_key = getattr(ev, "dia", "monday")
            day_label = _DAYS_ES.get(day_key, day_key)
            by_day.setdefault(day_label, []).append(f"  • {ev.inicio}–{ev.fin}: {ev.titulo}")
        lines = ["Tu plan de estudio esta semana:"]
        for day_key in _DAYS_ORDER:
            day_label = _DAYS_ES[day_key]
            if day_label in by_day:
                lines.append(f"\n{day_label}:")
                lines.extend(by_day[day_label])
        return "\n".join(lines)

    @tool
    def update_study_plan(reason: str) -> str:
        """Genera una nueva propuesta de plan de estudio basada en el motivo indicado.
        Úsala cuando el estudiante pida reorganizar su semana, actualizar el plan
        por una actividad nueva, o ajustar el plan por cambio de horario.
        reason: descripción del motivo del cambio (ej: 'parcial de Cálculo el viernes')."""
        from agents.support.dependencies import get_study_replanning_service

        if not state.study_plan.plan_events:
            return (
                "No tienes plan generado aún. "
                "Primero necesito que completes el flujo de prioridades para generarlo."
            )
        service = get_study_replanning_service()
        try:
            result = service.propose_replan(
                student_id=student_id,
                current_study_plan=state.study_plan,
                schedule_blocks=list(state.schedule.blocks),
                subjects=list(state.subjects),
                academic_activities=list(state.academic_activities),
                study_profile=state.study_profile,
                constraints=state.constraints,
                timezone=state.timezone,
                replan_state=state.replan,
                explicit_request_text=reason,
            )
            if result.proposed:
                return json.dumps({
                    "result": result.prompt_text or result.summary_text or "Nueva propuesta de plan lista.",
                    "_state_update": {
                        "replan": {
                            "trigger": "user_request",
                            "status": "proposed",
                            "request": result.request_payload,
                            "active_proposal": result.proposal_payload,
                            "pending_prompt": result.prompt_text,
                        },
                    },
                })
            return result.summary_text or "No fue necesario cambiar el plan."
        except Exception as exc:
            return f"No pude generar la propuesta de replanificación: {exc}"

    # --------------------------------------------------------- Prioridades ---

    @tool
    def update_priorities(subjects_with_priorities: list[dict]) -> str:
        """Actualiza las prioridades de materias para esta semana.
        subjects_with_priorities: lista de objetos con campos:
          nombre (str), prioridad (alta|media|baja), urgencia (opcional: alta|media|baja).
        Úsala cuando el estudiante quiera ajustar qué materias son más importantes
        o urgentes esta semana."""
        subjects = list(state.subjects)
        if not subjects:
            return "No tienes materias configuradas aún."
        updated = []
        changed = 0
        for s in subjects:
            nombre = getattr(s, "nombre", "")
            match_data = next(
                (x for x in subjects_with_priorities if x.get("nombre", "").lower() == nombre.lower()),
                None,
            )
            if match_data:
                patch: dict[str, Any] = {}
                if "prioridad" in match_data:
                    val = match_data["prioridad"]
                    if val not in _VALID_PRIORIDAD:
                        return f"Prioridad inválida: '{val}'. Valores aceptados: alta, media, baja."
                    patch["prioridad"] = val
                if "urgencia" in match_data:
                    val = match_data["urgencia"]
                    if val is not None and val not in _VALID_PRIORIDAD:
                        return f"Urgencia inválida: '{val}'. Valores aceptados: alta, media, baja."
                    patch["urgencia"] = val
                updated.append(s.model_copy(update=patch) if patch else s)
                changed += 1
            else:
                updated.append(s)
        if not changed:
            return "No encontré las materias especificadas en tu perfil. Verifica los nombres."
        return json.dumps({
            "result": f"Prioridades actualizadas para {changed} materia(s).",
            "_state_update": {"subjects": [s.model_dump() for s in updated]},
        })

    # --------------------------------------------------------- Horario -------

    @tool
    def get_schedule() -> str:
        """Obtiene el horario fijo de clases y actividades del estudiante.
        Úsala cuando el estudiante pregunte cuándo tiene clases, su horario semanal,
        cuándo tiene tiempo libre, o qué días tiene actividades comprometidas."""
        blocks = list(state.schedule.blocks or [])
        if not blocks:
            return "No tienes horario registrado."
        active = [b for b in blocks if getattr(b, "is_active", True)]
        if not active:
            return "No tienes bloques activos en tu horario."
        by_day: dict[str, list[str]] = {}
        for b in active:
            by_day.setdefault(b.day_of_week, []).append(
                f"  • {b.start_time}–{b.end_time}: {b.title} [{b.block_type}]"
            )
        lines = ["Tu horario fijo:"]
        for day_key in _DAYS_ORDER:
            if day_key in by_day:
                lines.append(f"\n{_DAYS_ES[day_key]}:")
                lines.extend(by_day[day_key])
        return "\n".join(lines)

    @tool
    def manage_schedule_change(change_type: str, details: str = "") -> str:
        """Gestiona cambios al horario fijo del estudiante.
        change_type: 'renewal' (nuevo semestre, renovar todo el horario),
                     'repair' (resolver conflictos detectados),
                     'edit' (modificar bloques específicos).
        details: descripción adicional opcional del cambio.
        Úsala cuando el estudiante quiera actualizar, renovar o corregir su horario."""
        phase_map = {
            "renewal": "schedule_renewal",
            "repair": "schedule_repair",
            "edit": "fixed_schedule_management",
        }
        if change_type not in phase_map:
            return f"Tipo de cambio no válido. Opciones: {', '.join(phase_map)}."
        new_phase = phase_map[change_type]
        label = {"renewal": "renovación", "repair": "reparación", "edit": "edición"}[change_type]
        return json.dumps({
            "result": f"Iniciando {label} del horario fijo.{' ' + details if details else ''}",
            "_state_update": {
                "phase": new_phase,
                "awaiting_user_input": False,
            },
        })

    # ------------------------------------------------- Integración externa ---

    @tool
    def sync_plan_to_calendar() -> str:
        """Sincroniza el plan de estudio con Outlook Calendar del estudiante.
        Úsala cuando el estudiante pida sincronizar su plan de estudio con su
        calendario de Outlook o agregar sesiones de estudio al calendario."""
        from agents.support.dependencies import get_outlook_calendar_sync_service

        service = get_outlook_calendar_sync_service()
        calendar_id = state.calendar.calendar_id
        try:
            result = service.sync_student_calendar(
                student_id=student_id,
                calendar_id=calendar_id,
            )
            if result.synced:
                return (
                    f"Sincronización completada: {result.upserted_count} sesiones "
                    f"creadas/actualizadas, {result.deleted_count} eliminadas."
                )
            return f"No se pudo sincronizar: {result.detail or result.error_code or 'error desconocido'}"
        except Exception as exc:
            return f"Error al sincronizar con Outlook: {exc}"

    @tool
    def sync_tasks_to_todo() -> str:
        """Sincroniza actividades pendientes con Microsoft To Do.
        Úsala cuando el estudiante pida agregar sus actividades académicas
        a Microsoft To Do o sincronizar tareas pendientes."""
        from agents.support.dependencies import get_microsoft_todo_sync_service

        service = get_microsoft_todo_sync_service()
        task_list_id = state.calendar.todo_task_list_id
        try:
            result = service.sync_actionable_sessions(
                student_id=student_id,
                task_list_id=task_list_id,
            )
            if result.synced:
                return f"Tareas sincronizadas: {result.upserted_count} creadas/actualizadas."
            return f"No se pudo sincronizar las tareas: {result.detail or result.error_code or 'error desconocido'}"
        except Exception as exc:
            return f"Error al sincronizar con To Do: {exc}"

    return [
        search_study_methods,
        get_technique_guide,
        add_academic_activity,
        edit_academic_activity,
        delete_academic_activity,
        get_pending_activities,
        get_weekly_plan,
        update_study_plan,
        update_priorities,
        get_schedule,
        manage_schedule_change,
        sync_plan_to_calendar,
        sync_tasks_to_todo,
    ]


def extract_tool_state_updates(result: dict) -> dict:
    """Extrae y fusiona los _state_update de todos los ToolMessages del ciclo ReAct.

    Las tools que modifican estado retornan JSON con la clave _state_update.
    Esta función recorre los mensajes del agente, parsea los ToolMessages y
    fusiona los updates (last-write-wins por clave).
    """
    from langchain_core.messages import ToolMessage

    merged: dict = {}
    for msg in result.get("messages", []):
        if not isinstance(msg, ToolMessage):
            continue
        try:
            data = json.loads(msg.content)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        if not isinstance(data, dict) or "_state_update" not in data:
            continue
        update = data["_state_update"]
        if isinstance(update, dict):
            merged.update(update)
    return merged


def _llm_study_fallback(query: str) -> str | None:
    """Responde con LLM cuando el RAG no tiene fuentes suficientes para la consulta."""
    from integrations.ai._llm_impl import maybe_get_llm
    from langchain_core.messages import HumanMessage, SystemMessage

    llm = maybe_get_llm(temperature=0.3)
    if not llm:
        return None
    try:
        response = llm.bind(max_tokens=400).invoke([
            SystemMessage(content=(
                "Eres Lara, asistente académica universitaria. "
                "Explica técnicas y métodos de estudio de forma clara y concisa. "
                "No resuelvas ejercicios ni tareas directamente. "
                "Si la pregunta pide resolver algo concreto, indica al estudiante que consulte a su docente."
            )),
            HumanMessage(content=str(query).strip()),
        ])
        content = getattr(response, "content", "") or ""
        return str(content).strip() or None
    except Exception:
        return None


def _get_student_id(state: AgentState) -> int | None:
    profile = state.student_profile
    if hasattr(profile, "persisted_student_id"):
        return profile.persisted_student_id
    d = profile.model_dump() if hasattr(profile, "model_dump") else {}
    return d.get("persisted_student_id")


__all__ = ["extract_tool_state_updates", "make_tools"]
