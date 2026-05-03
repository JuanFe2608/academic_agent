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
from zoneinfo import ZoneInfoNotFoundError
from typing import Any

from langchain_core.tools import tool

from agents.support.nodes.academic_agent.context import (
    current_datetime,
    format_current_datetime_for_student,
)
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


def _local_today(timezone_name: str = "America/Bogota") -> date:
    try:
        return current_datetime(str(timezone_name or "America/Bogota")).date()
    except ZoneInfoNotFoundError:
        return current_datetime("America/Bogota").date()


def _compute_urgency_from_due_date(
    due_date: str | None,
    *,
    reference_date: date | None = None,
) -> str:
    """Calcula prioridad interna desde la fecha límite. No exponer al LLM."""
    if not due_date:
        return "baja"
    try:
        today = reference_date or _local_today()
        delta = (date.fromisoformat(due_date) - today).days
        if delta <= 2:
            return "alta"
        if delta <= 7:
            return "media"
        return "baja"
    except ValueError:
        return "baja"


def make_tools(state: AgentState) -> list:
    """Crea las herramientas del agente con el estado actual capturado en closure."""
    student_id = _get_student_id(state)
    timezone_name = str(state.timezone or "America/Bogota")

    def _today() -> date:
        return _local_today(timezone_name)

    # Accumulator: tracks in-cycle mutations to academic_activities so that tools
    # called later in the same ReAct turn see the result of earlier tools.
    # Example: add_academic_activity → sync_tasks_to_todo must see the new activity.
    _cycle_updates: dict[str, Any] = {}

    def _current_activities() -> list:
        raw = _cycle_updates.get("academic_activities")
        if raw is not None:
            return list(raw)
        local = list(state.academic_activities)
        if local:
            return local
        if not student_id:
            return local
        try:
            from agents.support.dependencies import get_academic_activity_persistence_service

            result = get_academic_activity_persistence_service().list_activities(
                student_id=int(student_id),
                include_deleted=False,
            )
            if result.loaded:
                return list(result.activities)
        except Exception:
            pass
        return local

    # ------------------------------------------------------------------ RAG --

    @tool
    def get_current_datetime() -> str:
        """Devuelve la fecha y hora actual oficial del agente en Bogotá/Colombia.
        Úsala cuando el estudiante pregunte qué día es hoy, la fecha actual,
        la hora actual, o cuando necesites resolver fechas relativas antes de agendar."""

        now = current_datetime(timezone_name)
        return (
            f"Hoy en Bogotá/Colombia es {format_current_datetime_for_student(now)}. "
            f"Fecha ISO: {now.date().isoformat()}. Zona horaria: {timezone_name}."
        )

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
        is_priority: bool = False,
        difficulty: int = 3,
    ) -> str:
        """Registra una actividad académica nueva del estudiante.
        activity_type: parcial | quiz | tarea | taller | entrega | exposicion | proyecto.
        due_date: fecha límite en formato YYYY-MM-DD.
        is_priority: True si el estudiante quiere marcarla como prioritaria (⭐ en To Do), False por defecto.
          Pregunta al estudiante UNA sola vez "¿Quieres marcarla como prioritaria?" antes de llamar esta tool.
        difficulty: escala 1 (fácil) a 5 (muy difícil).
        Úsala cuando el estudiante mencione cualquier evaluación, entrega o compromiso académico."""
        from services.planning.academic_activity_service import (
            apply_confirmed_academic_activity_operation,
            build_activity_from_slots,
            coerce_academic_activities,
        )

        guard = _validate_academic_activity_tool_input(
            state,
            subject=subject,
            activity_type=activity_type,
            title=title,
        )
        if guard:
            return guard

        # Urgencia interna: si el estudiante la marcó como prioritaria → alta;
        # si no, se calcula automáticamente por cercanía de la fecha.
        today = _today()
        priority_level = (
            "alta"
            if is_priority
            else _compute_urgency_from_due_date(due_date, reference_date=today)
        )

        activities = coerce_academic_activities(_current_activities())
        try:
            new_act = build_activity_from_slots(
                {
                    "activity_type": activity_type,
                    "subject_name": subject,
                    "activity_title": title,
                    "due_date": due_date,
                    "priority_level": priority_level,
                    "difficulty_level": difficulty,
                },
                source_text=f"{subject} {activity_type} {title}",
                timezone=state.timezone,
            )
            result = apply_confirmed_academic_activity_operation(
                activities,
                {"operation": "create", "activity": new_act.model_dump()},
                timezone=state.timezone,
                reference_date=today,
            )
            star_note = " ⭐ Marcada como prioritaria." if is_priority else ""
            msg = (result.message or f"Actividad '{title}' registrada para el {due_date}.") + star_note
            state_update: dict[str, Any] = {
                "academic_activities": [a.model_dump() for a in result.activities],
            }
            if result.replan_required:
                state_update["replan"] = {"trigger": "academic_activity"}
            _cycle_updates["academic_activities"] = state_update["academic_activities"]
            return json.dumps({"result": msg, "_state_update": state_update})
        except Exception as exc:
            return f"No pude registrar la actividad: {exc}"

    @tool
    def edit_academic_activity(
        activity_reference: str,
        subject: str | None = None,
        activity_type: str | None = None,
        title: str | None = None,
        due_date: str | None = None,
        is_priority: bool | None = None,
        difficulty: int | None = None,
    ) -> str:
        """Edita una actividad académica ya registrada del estudiante.
        activity_reference: descripción para identificar la actividad (materia, tipo o título).
        subject: nuevo nombre de materia (opcional).
        activity_type: nuevo tipo — parcial | quiz | tarea | taller | entrega | exposicion | proyecto (opcional).
        title: nuevo título de la actividad (opcional).
        due_date: nueva fecha límite YYYY-MM-DD (opcional).
        is_priority: True para marcarla como prioritaria ⭐, False para quitarle la prioridad (opcional).
        difficulty: nueva dificultad 1-5 (opcional).
        Úsala cuando el estudiante quiera corregir datos de una actividad ya registrada."""
        from services.planning.academic_activity_service import (
            apply_confirmed_academic_activity_operation,
            coerce_academic_activities,
            match_academic_activities,
        )

        activities = coerce_academic_activities(_current_activities())
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
        if is_priority is not None:
            # Recompute priority_level: starred → alta; unstarred → recalculate from due_date
            effective_due = due_date or getattr(target, "due_date", None)
            changes["priority_level"] = (
                "alta"
                if is_priority
                else _compute_urgency_from_due_date(
                    effective_due,
                    reference_date=_today(),
                )
            )
        if difficulty is not None:
            changes["difficulty_level"] = difficulty
        if not changes:
            return "No indicaste ningún campo a actualizar."
        try:
            result = apply_confirmed_academic_activity_operation(
                activities,
                {"operation": "update", "activity_id": target.activity_id, "changes": changes},
                timezone=state.timezone,
                reference_date=_today(),
            )
            state_update: dict[str, Any] = {
                "academic_activities": [a.model_dump() for a in result.activities],
            }
            if result.replan_required:
                state_update["replan"] = {"trigger": "academic_activity"}
            _cycle_updates["academic_activities"] = state_update["academic_activities"]
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

        activities = coerce_academic_activities(_current_activities())
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
                reference_date=_today(),
            )
            state_update: dict[str, Any] = {
                "academic_activities": [a.model_dump() for a in result.activities],
            }
            if result.replan_required:
                state_update["replan"] = {"trigger": "academic_activity"}
            _cycle_updates["academic_activities"] = state_update["academic_activities"]
            return json.dumps({"result": result.message or "Actividad eliminada.", "_state_update": state_update})
        except Exception as exc:
            return f"No pude eliminar la actividad: {exc}"

    @tool
    def get_pending_activities(days_ahead: int = 7) -> str:
        """Lista actividades académicas pendientes del estudiante.
        Úsala cuando el estudiante pregunte qué tiene pendiente, cuáles son sus próximas
        entregas o quiera saber para qué prepararse. Siempre muestra también pendientes
        más lejanos; days_ahead solo separa próximos vs. más adelante."""
        from services.planning.academic_activity_service import active_academic_activities

        activities = active_academic_activities(_current_activities())
        pending = [a for a in activities if a.status == "pending"]
        if not pending:
            return "No tienes actividades académicas pendientes registradas."
        today = _today()
        cutoff = today + timedelta(days=max(0, int(days_ahead or 7)))

        def _due_date(activity) -> date | None:
            if not activity.due_date:
                return None
            try:
                return date.fromisoformat(activity.due_date)
            except ValueError:
                return None

        dated = [(a, _due_date(a)) for a in pending]
        upcoming = [(a, d) for a, d in dated if d is None or d <= cutoff]
        later = [(a, d) for a, d in dated if d is not None and d > cutoff]
        lines = [f"Tienes {len(pending)} actividad(es) académica(s) pendiente(s):"]
        if upcoming:
            lines.append(f"\nPróximos {days_ahead} días:")
            for a, d in sorted(upcoming, key=lambda item: item[1] or date.max):
                lines.append(_format_pending_activity_line(a, today=today, due=d))
        if later:
            lines.append("\nMás adelante:")
            for a, d in sorted(later, key=lambda item: item[1] or date.max):
                lines.append(_format_pending_activity_line(a, today=today, due=d))
        return "\n".join(lines)

    @tool
    def mark_activity_done(activity_reference: str) -> str:
        """Marca una actividad académica como completada.
        activity_reference: descripción para identificar la actividad (materia, tipo o título).
        Úsala cuando el estudiante diga que ya entregó, presentó o completó una actividad."""
        from services.planning.academic_activity_service import (
            apply_confirmed_academic_activity_operation,
            coerce_academic_activities,
            match_academic_activities,
        )

        activities = coerce_academic_activities(_current_activities())
        matches = match_academic_activities(activities, text=activity_reference)
        if not matches:
            return f"No encontré ninguna actividad que coincida con '{activity_reference}'."
        if len(matches) > 1:
            lines = [f"Encontré {len(matches)} actividades. Especifica cuál completar:"]
            for a in matches:
                due_str = f" — vence {a.due_date}" if a.due_date else ""
                lines.append(f"  • [{a.activity_type}] {a.subject_name}: {a.activity_title}{due_str}")
            return "\n".join(lines)
        target = matches[0]
        try:
            result = apply_confirmed_academic_activity_operation(
                activities,
                {"operation": "update", "activity_id": target.activity_id, "changes": {"status": "completed"}},
                timezone=state.timezone,
                reference_date=_today(),
            )
            state_update: dict[str, Any] = {
                "academic_activities": [a.model_dump() for a in result.activities],
            }
            _cycle_updates["academic_activities"] = state_update["academic_activities"]
            act_title = target.activity_title or target.activity_type
            return json.dumps({
                "result": result.message or f"✅ '{act_title}' marcada como completada.",
                "_state_update": state_update,
            })
        except Exception as exc:
            return f"No pude marcar la actividad como completada: {exc}"

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
        """Genera o actualiza el plan semanal de sesiones de estudio y lo aplica directamente.
        Úsala proactivamente: SIEMPRE después de add_academic_activity para reflejar
        la nueva actividad en el calendario de estudio, cuando el estudiante pida
        reorganizar su semana, o cuando cambie el horario fijo.
        reason: motivo del cambio (ej: 'parcial de Filosofía el viernes')."""
        from agents.support.dependencies import get_study_replanning_service

        service = get_study_replanning_service()
        try:
            result = service.propose_replan(
                student_id=student_id,
                current_study_plan=state.study_plan,
                schedule_blocks=list(state.schedule.blocks),
                subjects=list(state.subjects),
                academic_activities=_current_activities(),
                study_profile=state.study_profile,
                constraints=state.constraints,
                timezone=state.timezone,
                replan_state=state.replan,
                explicit_request_text=reason,
            )
            if result.proposed:
                proposal = result.proposal_payload or {}
                study_plan_update = dict(proposal.get("study_plan") or {})
                new_plan_events = list(study_plan_update.get("plan_events") or [])
                new_subjects = list(proposal.get("subjects") or [])

                # Formatear plan para que el LLM lo presente de forma natural
                by_day: dict[str, list[str]] = {}
                for ev in new_plan_events[:20]:
                    if isinstance(ev, dict):
                        day_key = ev.get("dia", "")
                        titulo = ev.get("titulo", "Sesión")
                        inicio = ev.get("inicio", "—")
                        fin = ev.get("fin", "—")
                    else:
                        day_key = getattr(ev, "dia", "")
                        titulo = getattr(ev, "titulo", "Sesión")
                        inicio = getattr(ev, "inicio", "—")
                        fin = getattr(ev, "fin", "—")
                    day_label = _DAYS_ES.get(day_key, day_key)
                    by_day.setdefault(day_label, []).append(f"  • {inicio}–{fin}: {titulo}")

                summary = result.summary_text or f"{len(new_plan_events)} sesión(es) planificadas"
                plan_lines = [f"Plan de estudio generado — {summary}:"]
                for day_key in _DAYS_ORDER:
                    day_label = _DAYS_ES[day_key]
                    if day_label in by_day:
                        plan_lines.append(f"\n{day_label}:")
                        plan_lines.extend(by_day[day_label])
                extra = len(new_plan_events) - 20
                if extra > 0:
                    plan_lines.append(f"\n  ... y {extra} sesión(es) más")

                state_update: dict[str, object] = {
                    "study_plan": study_plan_update,
                    "replan": {"status": "applied", "trigger": "user_request"},
                }
                if new_subjects:
                    state_update["subjects"] = new_subjects

                return json.dumps({
                    "result": "\n".join(plan_lines),
                    "_state_update": state_update,
                })

            # Sin cambios: el plan actual ya es óptimo — formatearlo para que el LLM lo presente
            current_events = list(state.study_plan.plan_events or [])
            if result.no_changes and current_events:
                by_day_curr: dict[str, list[str]] = {}
                for ev in current_events[:20]:
                    day_key = getattr(ev, "dia", "")
                    day_label = _DAYS_ES.get(day_key, day_key)
                    titulo = getattr(ev, "titulo", "Sesión")
                    inicio = getattr(ev, "inicio", "—")
                    fin = getattr(ev, "fin", "—")
                    by_day_curr.setdefault(day_label, []).append(f"  • {inicio}–{fin}: {titulo}")
                plan_lines_curr = ["Plan de estudio actual (ya incorpora todas tus actividades):"]
                for day_key in _DAYS_ORDER:
                    day_label = _DAYS_ES[day_key]
                    if day_label in by_day_curr:
                        plan_lines_curr.append(f"\n{day_label}:")
                        plan_lines_curr.extend(by_day_curr[day_label])
                return "\n".join(plan_lines_curr)
            return result.prompt_text or result.summary_text or "No fue necesario cambiar el plan."
        except Exception as exc:
            return f"No pude generar la propuesta de replanificación: {exc}"

    # ------------------------------------------------- Restricciones --------

    @tool
    def update_constraints(
        study_session_min: int | None = None,
        study_session_max: int | None = None,
        max_study_per_day_min: int | None = None,
        preferred_study_start: str | None = None,
        preferred_study_end: str | None = None,
        sleep_start: str | None = None,
        sleep_end: str | None = None,
    ) -> str:
        """Actualiza las restricciones de planificación del estudiante.
        study_session_min: duración mínima de sesión en minutos (ej: 25).
        study_session_max: duración máxima de sesión en minutos (ej: 90).
        max_study_per_day_min: máximo total de minutos de estudio por día (ej: 180).
        preferred_study_start: hora de inicio preferida para estudiar, formato HH:MM (ej: '08:00').
        preferred_study_end: hora de fin preferida para estudiar, formato HH:MM (ej: '14:00').
        sleep_start: hora a la que se acuesta, formato HH:MM (ej: '23:00').
        sleep_end: hora a la que se levanta, formato HH:MM (ej: '06:00').
        Úsala cuando el estudiante mencione: cuánto puede concentrarse seguido, cuándo prefiere estudiar,
        cuánto puede estudiar al día, su hora de dormir/levantarse, o restricciones de horario.
        Ejemplos: 'solo puedo estudiar de 8am a 2pm', 'máximo 45 minutos seguidos', 'duermo a las 11pm'."""
        from schemas.planning import Constraints

        current = state.constraints
        changes: dict[str, Any] = {}

        if study_session_min is not None:
            if not (10 <= study_session_min <= 120):
                return f"Sesión mínima inválida: {study_session_min}. Debe estar entre 10 y 120 minutos."
            changes["study_session_min"] = study_session_min
        if study_session_max is not None:
            if not (15 <= study_session_max <= 240):
                return f"Sesión máxima inválida: {study_session_max}. Debe estar entre 15 y 240 minutos."
            changes["study_session_max"] = study_session_max
        if max_study_per_day_min is not None:
            if not (30 <= max_study_per_day_min <= 720):
                return f"Máximo diario inválido: {max_study_per_day_min}. Debe estar entre 30 y 720 minutos."
            changes["max_study_per_day_min"] = max_study_per_day_min
        if preferred_study_start is not None:
            try:
                changes["preferred_study_start"] = _normalize_time(preferred_study_start)
            except Exception:
                return f"Hora de inicio inválida: '{preferred_study_start}'. Usa formato HH:MM."
        if preferred_study_end is not None:
            try:
                changes["preferred_study_end"] = _normalize_time(preferred_study_end)
            except Exception:
                return f"Hora de fin inválida: '{preferred_study_end}'. Usa formato HH:MM."
        if sleep_start is not None:
            try:
                changes["sleep_start"] = _normalize_time(sleep_start)
            except Exception:
                return f"Hora de sueño inválida: '{sleep_start}'. Usa formato HH:MM."
        if sleep_end is not None:
            try:
                changes["sleep_end"] = _normalize_time(sleep_end)
            except Exception:
                return f"Hora de despertar inválida: '{sleep_end}'. Usa formato HH:MM."

        if not changes:
            return "No indicaste ningún límite a actualizar."

        new_min = changes.get("study_session_min", current.study_session_min)
        new_max = changes.get("study_session_max", current.study_session_max)
        if new_min > new_max:
            return f"La sesión mínima ({new_min} min) no puede ser mayor que la máxima ({new_max} min)."

        pref_s = changes.get("preferred_study_start", current.preferred_study_start)
        pref_e = changes.get("preferred_study_end", current.preferred_study_end)
        if pref_s and pref_e:
            try:
                ps_min = int(pref_s.split(":")[0]) * 60 + int(pref_s.split(":")[1])
                pe_min = int(pref_e.split(":")[0]) * 60 + int(pref_e.split(":")[1])
                if ps_min >= pe_min:
                    return f"El horario preferido de inicio ({pref_s}) debe ser anterior al de fin ({pref_e})."
            except Exception:
                pass

        updated = current.model_copy(update=changes)
        msg_parts: list[str] = []
        if "study_session_min" in changes or "study_session_max" in changes:
            msg_parts.append(f"sesiones de {updated.study_session_min}–{updated.study_session_max} min")
        if "max_study_per_day_min" in changes:
            msg_parts.append(f"máximo {updated.max_study_per_day_min} min/día")
        if "preferred_study_start" in changes or "preferred_study_end" in changes:
            msg_parts.append(
                f"horario preferido {updated.preferred_study_start or '—'}–{updated.preferred_study_end or '—'}"
            )
        if "sleep_start" in changes or "sleep_end" in changes:
            msg_parts.append(f"sueño {updated.sleep_end}–{updated.sleep_start}")

        msg = "✅ Restricciones de planificación actualizadas: " + ", ".join(msg_parts) + "."
        state_update: dict[str, Any] = {"constraints": updated.model_dump()}
        if state.study_plan.plan_events:
            state_update["replan"] = {"trigger": "user_request"}

        return json.dumps({"result": msg, "_state_update": state_update})

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
    def get_schedule(filter_type: str | None = None) -> str:
        """Obtiene el horario fijo del estudiante: clases, trabajo y actividades extracurriculares.
        filter_type: filtra por tipo — 'academic' (clases/materias), 'work' (trabajo/laboral),
        'extracurricular' (deportes, actividades personales). Si es None, muestra todo.
        Úsala cuando el estudiante pregunte por su horario, sus clases, su trabajo, sus actividades,
        cuándo tiene tiempo libre, o qué días tiene compromisos fijos."""
        _TYPE_LABELS = {
            "academic": "Académico 📚",
            "work": "Laboral 💼",
            "extracurricular": "Extracurricular 🏃",
        }
        blocks = _load_current_schedule_blocks(state)
        if not blocks:
            return "No tienes horario fijo registrado."
        active = [b for b in blocks if getattr(b, "is_active", True)]
        if not active:
            return "No tienes bloques activos en tu horario."

        # Aplicar filtro de tipo si se especificó
        type_norm = (filter_type or "").strip().lower()
        if type_norm in {"academic", "work", "extracurricular"}:
            active = [b for b in active if getattr(b, "block_type", "") == type_norm]
            if not active:
                label = _TYPE_LABELS.get(type_norm, type_norm)
                return f"No tienes bloques de tipo {label} en tu horario."

        # Agrupar por tipo y luego por día
        by_type: dict[str, dict[str, list[str]]] = {}
        for b in active:
            btype = getattr(b, "block_type", "academic")
            day_key = getattr(b, "day_of_week", "monday")
            by_type.setdefault(btype, {}).setdefault(day_key, []).append(
                f"    • {b.start_time}–{b.end_time}: {b.title}"
            )

        # Orden de tipos para mostrar: academic → work → extracurricular
        type_order = ["academic", "work", "extracurricular"]
        lines = ["**Tu horario fijo:**"]
        for btype in type_order:
            if btype not in by_type:
                continue
            lines.append(f"\n**{_TYPE_LABELS[btype]}**")
            day_map = by_type[btype]
            for day_key in _DAYS_ORDER:
                if day_key in day_map:
                    lines.append(f"  {_DAYS_ES[day_key]}:")
                    lines.extend(day_map[day_key])
        return "\n".join(lines)

    @tool
    def add_schedule_block(
        title: str,
        day: str,
        start_time: str,
        end_time: str,
        block_type: str = "academic",
    ) -> str:
        """Agrega un bloque al horario fijo del estudiante y sincroniza con Outlook.
        title: nombre de la clase/materia/actividad.
        day: día en inglés — monday | tuesday | wednesday | thursday | friday | saturday | sunday.
        start_time: hora de inicio en formato HH:MM (ej: '09:00').
        end_time: hora de fin en formato HH:MM (ej: '11:00').
        block_type: academic (clase/materia) | work (trabajo) | extracurricular (deporte/personal).
        Úsala cuando el estudiante quiera agregar una clase, trabajo o actividad al horario semanal.
        Extrae día y horas del mensaje del usuario — NO pidas datos que ya mencionó."""
        import uuid
        from services.scheduling.models import WeeklyScheduleBlock

        valid_days = {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}
        valid_types = {"academic", "work", "extracurricular"}
        day_norm = day.strip().lower()
        type_norm = block_type.strip().lower()
        if day_norm not in valid_days:
            return f"Día inválido: '{day}'. Acepta: monday, tuesday, wednesday, thursday, friday, saturday, sunday."
        if type_norm not in valid_types:
            return f"Tipo inválido: '{block_type}'. Acepta: academic, work, extracurricular."

        try:
            blocks = _load_current_schedule_blocks(state)
            _start = _normalize_time(start_time)
            _end = _normalize_time(end_time)
            _day_label = _DAYS_ES.get(day_norm, day_norm)
            _source_text = (
                f"{_day_label} {_start}-{_end}"
                if type_norm == "work"
                else f"{_day_label} {_start}-{_end} {title.strip()}"
            ).strip()
            new_block = WeeklyScheduleBlock(
                block_id=str(uuid.uuid4()),
                block_type=type_norm,
                title=title.strip(),
                day_of_week=day_norm,
                start_time=_start,
                end_time=_end,
                frequency="weekly",
                timezone=str(state.timezone or "America/Bogota"),
                source_text=_source_text,
                is_active=True,
                user_confirmed=True,
            )
            updated_blocks = blocks + [new_block]
            msg, state_update = _apply_and_persist_schedule(state, updated_blocks, "actualizado")
            return json.dumps(
                {"result": f"✅ Bloque '{title}' agregado al horario. {msg}", "_state_update": state_update},
                default=_json_default,
            )
        except Exception as exc:
            return f"Error inesperado al agregar el bloque '{title}': {exc}"

    @tool
    def update_schedule_block(
        block_reference: str,
        title: str | None = None,
        day: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        block_type: str | None = None,
    ) -> str:
        """Modifica un bloque existente del horario fijo y sincroniza con Outlook.
        block_reference: descripción para identificar el bloque (nombre, día, o combinación).
        Pasa solo los campos que cambian: day en inglés, start_time/end_time en HH:MM.
        Úsala cuando el estudiante quiera cambiar horario, día o nombre de una clase ya registrada."""
        from services.scheduling.fixed_schedule_management import match_fixed_schedule_blocks

        try:
            blocks = _load_current_schedule_blocks(state)
            if not blocks:
                return "No tienes bloques registrados en el horario fijo."
            result = match_fixed_schedule_blocks(blocks, block_reference)
            if not result.matches:
                lines = ["No encontré bloque con esa descripción. Bloques actuales:"]
                for b in blocks:
                    lines.append(f"  • {_DAYS_ES.get(b.day_of_week, b.day_of_week)} {b.start_time}–{b.end_time}: {b.title} [{b.block_type}]")
                return "\n".join(lines)
            if len(result.matches) > 1:
                lines = [f"Encontré {len(result.matches)} bloques similares. Especifica cuál:"]
                for b in result.matches:
                    lines.append(f"  • {_DAYS_ES.get(b.day_of_week, b.day_of_week)} {b.start_time}–{b.end_time}: {b.title}")
                return "\n".join(lines)

            target = result.matches[0]
            updates: dict[str, Any] = {}
            if title is not None:
                updates["title"] = title.strip()
            if day is not None:
                d = day.strip().lower()
                if d not in {"monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"}:
                    return f"Día inválido: '{day}'."
                updates["day_of_week"] = d
            if start_time is not None:
                updates["start_time"] = _normalize_time(start_time)
            if end_time is not None:
                updates["end_time"] = _normalize_time(end_time)
            if block_type is not None:
                t = block_type.strip().lower()
                if t not in {"academic", "work", "extracurricular"}:
                    return f"Tipo inválido: '{block_type}'."
                updates["block_type"] = t
            if not updates:
                return "No indicaste ningún campo a cambiar."

            updated_target = target.model_copy(update=updates)
            updated_blocks = [updated_target if b.block_id == target.block_id else b for b in blocks]
            msg, state_update = _apply_and_persist_schedule(state, updated_blocks, "actualizado")
            return json.dumps(
                {"result": f"✅ Bloque '{target.title}' modificado. {msg}", "_state_update": state_update},
                default=_json_default,
            )
        except Exception as exc:
            return f"Error inesperado al modificar el bloque '{block_reference}': {exc}"

    @tool
    def delete_schedule_block(block_reference: str) -> str:
        """Elimina un bloque del horario fijo y sincroniza con Outlook.
        block_reference: descripción del bloque a eliminar (nombre, día, o combinación).
        Úsala cuando el estudiante quiera quitar una clase, trabajo o actividad del horario semanal."""
        from services.scheduling.fixed_schedule_management import match_fixed_schedule_blocks

        try:
            blocks = _load_current_schedule_blocks(state)
            if not blocks:
                return "No tienes bloques registrados en el horario fijo."
            result = match_fixed_schedule_blocks(blocks, block_reference)
            if not result.matches:
                lines = ["No encontré bloque con esa descripción. Bloques actuales:"]
                for b in blocks:
                    lines.append(f"  • {_DAYS_ES.get(b.day_of_week, b.day_of_week)} {b.start_time}–{b.end_time}: {b.title} [{b.block_type}]")
                return "\n".join(lines)
            if len(result.matches) > 1:
                lines = [f"Encontré {len(result.matches)} bloques similares. Especifica cuál eliminar:"]
                for b in result.matches:
                    lines.append(f"  • {_DAYS_ES.get(b.day_of_week, b.day_of_week)} {b.start_time}–{b.end_time}: {b.title}")
                return "\n".join(lines)

            target = result.matches[0]
            updated_blocks = [b for b in blocks if b.block_id != target.block_id]
            msg, state_update = _apply_and_persist_schedule(state, updated_blocks, "actualizado")
            return json.dumps(
                {"result": f"✅ Bloque '{target.title}' eliminado del horario. {msg}", "_state_update": state_update},
                default=_json_default,
            )
        except Exception as exc:
            return f"Error inesperado al eliminar el bloque '{block_reference}': {exc}"

    # ------------------------------------------------- Integración externa ---

    @tool
    def sync_plan_to_calendar() -> str:
        """Sincroniza el plan de estudio con Outlook Calendar del estudiante.
        Úsala cuando el estudiante pida sincronizar su plan de estudio con su
        calendario de Outlook o agregar sesiones de estudio al calendario."""
        from agents.support.dependencies import (
            get_outlook_calendar_sync_service,
            get_study_plan_materialization_service,
        )

        service = get_outlook_calendar_sync_service()
        calendar_id = state.calendar.calendar_id
        try:
            plan = state.study_plan
            if plan.plan_events and plan.persisted_profile_id:
                materialized = get_study_plan_materialization_service().materialize_plan_instances(
                    student_id=student_id,
                    study_plan_profile_id=plan.persisted_profile_id,
                    study_plan=plan,
                    timezone=str(state.timezone or "America/Bogota"),
                )
                if not materialized.materialized:
                    return (
                        "No pude dejar listas las sesiones fechadas para Outlook: "
                        f"{materialized.detail or materialized.error_code or 'error desconocido'}"
                    )
            result = service.sync_student_calendar(
                student_id=student_id,
                calendar_state=state.calendar,
                calendar_id=calendar_id,
                study_plan_profile_id=state.study_plan.persisted_profile_id,
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
        """Sincroniza actividades académicas con Microsoft To Do.
        Las actividades con prioridad alta aparecen con ⭐ en To Do.
        Actividades completadas se marcan como completadas y eliminadas se retiran de To Do.
        Úsala proactivamente después de registrar o modificar actividades,
        o cuando el estudiante pida ver sus tareas en Microsoft To Do."""
        from agents.support.dependencies import get_microsoft_todo_sync_service
        from services.planning.academic_activity_service import (
            coerce_academic_activities,
        )

        service = get_microsoft_todo_sync_service()
        task_list_id = state.calendar.todo_task_list_id
        activities = coerce_academic_activities(_current_activities())
        try:
            result = service.sync_academic_activities_to_todo(
                student_id=student_id,
                task_list_id=task_list_id,
                activities=activities,
            )
            if result.synced:
                msg = f"✅ {result.upserted_count} actividad(es) sincronizada(s) en Microsoft To Do."
                if getattr(result, "deleted_count", 0):
                    msg += f" {result.deleted_count} tarea(s) eliminada(s)."
                if result.synced_activities:
                    updated_all = {a.activity_id: a for a in result.synced_activities}
                    merged = [
                        updated_all.get(a.activity_id, a).model_dump()
                        for a in activities
                    ]
                    _cycle_updates["academic_activities"] = merged
                    return json.dumps({"result": msg, "_state_update": {"academic_activities": merged}})
                return msg
            return f"No se pudo sincronizar: {result.detail or result.error_code or 'error desconocido'}"
        except Exception as exc:
            return f"Error al sincronizar con To Do: {exc}"

    return [
        get_current_datetime,
        search_study_methods,
        get_technique_guide,
        add_academic_activity,
        edit_academic_activity,
        delete_academic_activity,
        mark_activity_done,
        get_pending_activities,
        get_weekly_plan,
        update_study_plan,
        update_constraints,
        get_schedule,
        add_schedule_block,
        update_schedule_block,
        delete_schedule_block,
        sync_plan_to_calendar,
        sync_tasks_to_todo,
    ]


def _load_current_schedule_blocks(state: AgentState) -> list:
    """Carga bloques del horario fijo desde el estado o la DB como fallback."""
    from services.scheduling.models import ensure_weekly_block

    blocks = list(state.schedule.blocks or [])
    if blocks:
        return [ensure_weekly_block(b) for b in blocks]
    student_id = _get_student_id(state)
    if not student_id:
        return []
    try:
        from agents.support.dependencies import get_schedule_service
        result = get_schedule_service().list_current_schedule_blocks(student_id=student_id)
        if result.found and result.blocks:
            return [_block_from_persisted_record(r) for r in result.blocks]
    except Exception:
        pass
    return []


def _block_from_persisted_record(record: object):
    from services.scheduling.models import WeeklyScheduleBlock
    return WeeklyScheduleBlock(
        block_id=str(getattr(record, "source_block_id", "")),
        block_type=str(getattr(record, "block_type", "academic")),
        title=str(getattr(record, "title", "")),
        day_of_week=str(getattr(record, "day_of_week", "monday")),
        start_time=str(getattr(record, "start_time", "00:00")),
        end_time=str(getattr(record, "end_time", "00:00")),
        frequency=str(getattr(record, "frequency", "weekly")),
        timezone=str(getattr(record, "timezone", "America/Bogota")),
        source_text=str(getattr(record, "source_text", "")),
        is_active=bool(getattr(record, "is_active", True)),
        user_confirmed=bool(getattr(record, "confirmed_by_user", True)),
        has_conflict=bool(getattr(record, "has_conflict", False)),
        conflict_accepted=bool(getattr(record, "conflict_accepted", False)),
        metadata={"persisted_block_id": getattr(record, "id", None)},
    )


def _apply_and_persist_schedule(
    state: AgentState,
    updated_blocks: list,
    success_label: str,
) -> tuple[str, dict]:
    """Persiste cambios al horario fijo y sincroniza con Outlook. Retorna (msg, state_update).

    Siempre retorna un state_update con los bloques actualizados en memoria, incluso si la
    persistencia en DB o la sincronización con Outlook fallan (fallo parcial = advertencia).
    Nunca lanza excepciones — todos los errores se capturan y se incluyen en el mensaje.
    """
    from agents.support.dependencies import (
        get_outlook_fixed_schedule_sync_service,
        get_schedule_service,
    )
    from agents.support.scheduling.conflicts import detect_schedule_conflicts
    from agents.support.scheduling.formatter import build_schedule_summary
    from agents.support.scheduling.state_helpers import (
        ensure_schedule_flow_state,
        update_schedule_flow_state,
    )
    from services.scheduling.block_operations import current_section_blocks
    from services.scheduling.extracurricular_state import build_extracurricular_items_from_blocks
    from services.scheduling.models import ensure_weekly_block
    from services.scheduling.raw_input_sync import sync_schedule_blocks_to_raw_inputs

    # --- 1. Normalizar bloques y detectar conflictos ---
    try:
        schedule_state = ensure_schedule_flow_state(state.schedule)
        normalized = [
            ensure_weekly_block(b).model_copy(update={"user_confirmed": True})
            for b in updated_blocks
        ]
        normalized, conflicts = detect_schedule_conflicts(normalized)
        summary_text = build_schedule_summary(normalized)
    except Exception as exc:
        return f"Error preparando los bloques del horario: {exc}", {}

    student_id = _get_student_id(state)
    profile = state.student_profile
    occupation = str(getattr(profile, "occupation", None) or "")
    tz = str(state.timezone or "America/Bogota")

    sched_end = None
    if schedule_state.schedule_end_date:
        try:
            from datetime import date as _date
            sched_end = _date.fromisoformat(schedule_state.schedule_end_date)
        except ValueError:
            pass

    # --- 2. Persistir en DB (fallo → advertencia, no bloqueo) ---
    persist_note = ""
    schedule_profile_id = getattr(schedule_state, "persisted_profile_id", None)
    new_sched_end_iso = schedule_state.schedule_end_date

    try:
        persist_result = get_schedule_service().persist_schedule(
            student_id=student_id,
            occupation=occupation,
            timezone=tz,
            summary_text=summary_text,
            blocks=normalized,
            conflicts=conflicts,
            conflicts_accepted=bool(schedule_state.conflicts_accepted),
            schedule_end_date=sched_end,
        )
        if persist_result.persisted:
            schedule_profile_id = persist_result.schedule_profile_id
            if getattr(persist_result, "schedule_end_date", None):
                new_sched_end_iso = persist_result.schedule_end_date.isoformat()
        else:
            detail = persist_result.detail or persist_result.error_code or "desconocido"
            persist_note = f" ⚠️ No se guardó en BD: {detail}."
    except Exception as exc:
        persist_note = f" ⚠️ Error al guardar en BD: {exc}."

    # --- 3. Construir schedule_update con los bloques en memoria ---
    try:
        schedule_update = update_schedule_flow_state(
            schedule_state,
            blocks=normalized,
            conflicts=conflicts,
            summary_text=summary_text,
            review_stage="idle",
            persisted_profile_id=schedule_profile_id,
            persistence_error=persist_note.strip() if persist_note else None,
            schedule_end_date=new_sched_end_iso,
        )
        if "blocks" in schedule_update:
            schedule_update["blocks"] = [
                b.model_dump(mode="python") if hasattr(b, "model_dump") else dict(b)
                for b in schedule_update["blocks"]
            ]
        if "conflicts" in schedule_update:
            schedule_update["conflicts"] = [
                c.model_dump(mode="python") if hasattr(c, "model_dump") else dict(c)
                for c in schedule_update["conflicts"]
            ]
    except Exception as exc:
        return f"Error construyendo el estado del horario: {exc}", {}

    # --- 4. Sincronizar con Outlook (fallo → advertencia, no bloqueo) ---
    cal = state.calendar
    base_cal = cal.model_dump(mode="python") if hasattr(cal, "model_dump") else dict(cal)
    cal_dict = dict(base_cal)
    sync_note = ""

    if schedule_profile_id:
        try:
            sync_result = get_outlook_fixed_schedule_sync_service().sync_schedule_profile(
                student_id=student_id,
                schedule_profile_id=schedule_profile_id,
                calendar_state=base_cal,
                calendar_id=base_cal.get("calendar_id"),
            )
            if getattr(sync_result, "synced", False):
                sync_note = " Outlook sincronizado ✅"
                cal_dict = {
                    **base_cal,
                    "provider": "outlook",
                    "authorized": True,
                    "synced_event_map": dict(getattr(sync_result, "synced_event_map", {})),
                }
            else:
                err = getattr(sync_result, "detail", None) or getattr(sync_result, "error_code", None) or "desconocido"
                sync_note = f" ⚠️ Outlook no sincronizado: {err}."
                cal_dict = {**base_cal, "synced_event_map": dict(getattr(sync_result, "synced_event_map", {}))}
        except Exception as exc:
            sync_note = f" ⚠️ Error Outlook: {exc}."
    else:
        sync_note = " ⚠️ Outlook no sincronizado (horario no persistido en BD)."

    # --- 5. Efectos secundarios: raw_inputs y extracurriculares ---
    try:
        raw_inputs = sync_schedule_blocks_to_raw_inputs(
            state.raw_inputs, "academic", current_section_blocks(normalized, "academic")
        )
        raw_inputs = sync_schedule_blocks_to_raw_inputs(
            raw_inputs, "work", current_section_blocks(normalized, "work")
        )
        extracurricular = build_extracurricular_items_from_blocks(
            current_section_blocks(normalized, "extracurricular")
        )
        raw_inputs_dict = raw_inputs.model_dump(mode="python") if hasattr(raw_inputs, "model_dump") else dict(raw_inputs)
        extracurricular_list = [
            e.model_dump(mode="python") if hasattr(e, "model_dump") else dict(e)
            for e in extracurricular
        ]
    except Exception:
        raw_inputs_src = state.raw_inputs
        raw_inputs_dict = raw_inputs_src.model_dump(mode="python") if hasattr(raw_inputs_src, "model_dump") else {}
        extracurricular_list = [
            e.model_dump(mode="python") if hasattr(e, "model_dump") else dict(e)
            for e in list(state.extracurricular or [])
        ]

    state_update: dict[str, Any] = {
        "schedule": schedule_update,
        "calendar": cal_dict,
        "raw_inputs": raw_inputs_dict,
        "extracurricular": extracurricular_list,
    }

    # --- 6. Activar replan si hay plan de estudio vigente ---
    plan_events = list(state.study_plan.plan_events or [])
    if plan_events and schedule_profile_id:
        state_update["replan"] = {
            "trigger": "fixed_schedule_change",
            "status": "pending",
            "change_request": {
                "trigger": "fixed_schedule_change",
                "source": "schedule_tools",
                "operation": "schedule_change",
                "schedule_profile_id": schedule_profile_id,
                "reason": f"Horario {success_label}",
            },
        }

    return f"Horario {success_label}.{persist_note}{sync_note}", state_update


def _normalize_time(t: str) -> str:
    """Normaliza hora a HH:MM. Acepta '9', '9:00', '09:00', '9.00', '9h'."""
    raw = str(t or "").strip().replace(".", ":").replace(" ", "").rstrip("h")
    if ":" not in raw:
        try:
            return f"{int(raw):02d}:00"
        except ValueError:
            return raw
    parts = raw.split(":")
    try:
        return f"{int(parts[0]):02d}:{int(parts[1]):02d}"
    except (ValueError, IndexError):
        return raw


def _format_pending_activity_line(activity: Any, *, today: date, due: date | None) -> str:
    due_str = ""
    if due is not None:
        delta = (due - today).days
        if delta < 0:
            due_str = f" — venció hace {abs(delta)} día(s), el {due.isoformat()}"
        elif delta == 0:
            due_str = f" — vence hoy, {due.isoformat()}"
        elif delta == 1:
            due_str = f" — vence mañana, {due.isoformat()}"
        else:
            due_str = f" — vence {due.isoformat()} (faltan {delta} días)"
    elif getattr(activity, "due_date", None):
        due_str = f" — vence {activity.due_date}"
    pri_str = f" [{activity.priority_level}]" if getattr(activity, "priority_level", None) else ""
    title = getattr(activity, "activity_title", None) or getattr(activity, "activity_type", "actividad")
    return f"  • [{activity.activity_type}] {activity.subject_name}: {title}{due_str}{pri_str}"


def _validate_academic_activity_tool_input(
    state: AgentState,
    *,
    subject: str,
    activity_type: str,
    title: str,
) -> str | None:
    valid_types = {
        "parcial",
        "quiz",
        "tarea",
        "taller",
        "entrega",
        "exposicion",
        "proyecto",
        "estudio_pendiente",
    }
    normalized_type = _normalize_text_key(activity_type)
    if normalized_type not in valid_types:
        return (
            f"Tipo de actividad inválido: '{activity_type}'. "
            "Usa parcial, quiz, tarea, taller, entrega, exposicion o proyecto."
        )

    if _looks_like_non_academic_activity(state, subject=subject, title=title):
        return (
            "Esto parece una actividad laboral o extracurricular, no una actividad académica puntual. "
            "Para trabajo, hobbies o extracurriculares usa add_schedule_block con block_type='work' "
            "o block_type='extracurricular'. No la sincronices con Microsoft To Do ni generes sesiones de estudio."
        )
    return None


def _looks_like_non_academic_activity(
    state: AgentState,
    *,
    subject: str,
    title: str,
) -> bool:
    subject_key = _normalize_text_key(subject)
    if subject_key and subject_key in _known_academic_subject_keys(state):
        return False

    combined = _normalize_text_key(f"{subject} {title}")
    if not combined:
        return False

    work_markers = {
        "trabajo",
        "laboral",
        "turno",
        "oficina",
        "empleo",
        "empresa",
        "jornada",
        "practica laboral",
    }
    extracurricular_markers = {
        "extracurricular",
        "gimnasio",
        "gym",
        "deporte",
        "entrenamiento",
        "futbol",
        "crochet",
        "hobby",
        "musica",
    }
    academic_markers = {
        "parcial",
        "quiz",
        "tarea",
        "taller",
        "entrega",
        "exposicion",
        "proyecto",
        "materia",
        "clase",
        "curso",
        "universidad",
    }

    has_non_academic_marker = any(marker in combined for marker in work_markers | extracurricular_markers)
    has_explicit_academic_marker = any(marker in combined for marker in academic_markers)
    return bool(has_non_academic_marker and not has_explicit_academic_marker)


def _known_academic_subject_keys(state: AgentState) -> set[str]:
    keys = {
        _normalize_text_key(getattr(subject, "nombre", ""))
        for subject in list(state.subjects or [])
        if _normalize_text_key(getattr(subject, "nombre", ""))
    }
    for block in list(state.schedule.blocks or []):
        block_type = getattr(block, "block_type", "")
        title = getattr(block, "title", "")
        if block_type == "academic" and str(title or "").strip():
            keys.add(_normalize_text_key(title))
    return keys


def _normalize_text_key(value: object) -> str:
    import unicodedata

    text = str(value or "").strip().lower()
    text = (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    return " ".join(text.split())


def _json_default(obj: Any) -> Any:
    """Serializador JSON fallback para objetos Pydantic, date/datetime, etc."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return str(obj)


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
